"""Live luminance sampling and non-destructive QGIS renderer engine.

The portrait renderer is a plain ``QgsCategorizedSymbolRenderer`` on ``$id``
whose four tone categories hold the sampled feature ids and whose catch-all
category draws the Paper tone. Nothing in it calls back into Python, so the
map renders at native speed in QGIS' parallel render threads, a saved project
shows the same portrait without the plugin, and an exported QML is complete.
"""
from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QImage, QImageReader, qAlpha, qBlue, qGray, qGreen, qRed
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsCoordinateTransform,
    QgsCsException,
    QgsFeatureRenderer,
    QgsFeatureRequest,
    QgsFillSymbol,
    QgsGeometry,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPointXY,
    QgsProject,
    QgsReadWriteContext,
    QgsRectangle,
    QgsRendererCategory,
    QgsSimpleLineSymbolLayer,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .presets import PRESETS
from .profile import (
    TONE_LABELS,
    adjust_luminance,
    blend_edge,
    fit_bounds_to_aspect,
    group_by_tone,
    map_to_normalized,
    quantile_limits,
)


STYLED_PROPERTY = "zero2urbanportrait/styled"
ORIGINAL_RENDERER_PROPERTY = "zero2urbanportrait/original_renderer"
PROJECT_SCOPE = "zero2urbanportrait"
ORIGINAL_BACKGROUND_KEY = "original_background"


@dataclass
class RenderOptions:
    preset: str = "Ink Portrait"
    sampling: str = "Balanced"
    gamma: float = 1.0
    invert: bool = False
    auto_contrast: bool = True
    edge_amount: float = 0.0
    max_features: int = 10000
    opacity: float = 1.0
    paint_background: bool = True


def renderer_to_xml(renderer) -> str:
    """Serialize a feature renderer so it can live in a layer property."""
    document = QDomDocument("renderer")
    element = renderer.save(document, QgsReadWriteContext())
    document.appendChild(element)
    return document.toString()


def renderer_from_xml(xml: str):
    """Rebuild a renderer stored by :func:`renderer_to_xml`, or ``None``."""
    if not xml:
        return None
    document = QDomDocument()
    document.setContent(str(xml))
    element = document.documentElement()
    if element.isNull():
        return None
    return QgsFeatureRenderer.load(element, QgsReadWriteContext())


class ImageProfile:
    """A downsampled image with fast luminance and edge sampling."""

    def __init__(self, image: QImage, path: str):
        if image.isNull():
            raise ValueError("The selected image could not be decoded.")
        self.source_width = image.width()
        self.source_height = image.height()
        self.aspect_ratio = self.source_width / self.source_height
        if image.width() > 1800 or image.height() > 1800:
            image = image.scaled(1800, 1800, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        self.image = image.convertToFormat(QImage.Format.Format_ARGB32)
        self.path = path
        self.low, self.high = self._contrast_limits()

    @classmethod
    def load(cls, path: str) -> "ImageProfile":
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            raise ValueError(reader.errorString() or "Unsupported image format")
        return cls(image, path)

    def _contrast_limits(self) -> tuple[int, int]:
        histogram = [0] * 256
        step_x = max(1, self.image.width() // 300)
        step_y = max(1, self.image.height() // 300)
        for y in range(0, self.image.height(), step_y):
            for x in range(0, self.image.width(), step_x):
                pixel = self.image.pixel(x, y)
                if qAlpha(pixel) > 8:
                    histogram[qGray(pixel)] += 1
        return quantile_limits(histogram, 0.01)

    def sample(self, u: float, v: float, options: RenderOptions) -> int:
        """Return the final 0-255 tone at (u, v): contrast, gamma, invert, edges."""
        x = min(self.image.width() - 1, max(0, int(round(u * (self.image.width() - 1)))))
        y = min(self.image.height() - 1, max(0, int(round(v * (self.image.height() - 1)))))
        pixel = self.image.pixel(x, y)
        if qAlpha(pixel) <= 8:
            return 255
        luminance = qGray(qRed(pixel), qGreen(pixel), qBlue(pixel))
        low, high = (self.low, self.high) if options.auto_contrast else (0, 255)
        luminance = adjust_luminance(luminance, low, high, options.gamma, options.invert)
        if options.edge_amount > 0.0:
            edge = self._edge_strength(x, y)
            luminance = blend_edge(luminance, edge, options.edge_amount)
        return luminance

    def _edge_strength(self, x: int, y: int) -> int:
        x0, x1 = max(0, x - 1), min(self.image.width() - 1, x + 1)
        y0, y1 = max(0, y - 1), min(self.image.height() - 1, y + 1)
        left = qGray(self.image.pixel(x0, y))
        right = qGray(self.image.pixel(x1, y))
        top = qGray(self.image.pixel(x, y0))
        bottom = qGray(self.image.pixel(x, y1))
        return min(255, abs(right - left) + abs(bottom - top))


class PortraitEngine(QObject):
    """Samples selected vector layers and owns reversible renderers."""

    progress = pyqtSignal(int, int)
    message = pyqtSignal(str)

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.profile: ImageProfile | None = None
        self.frame_container: QgsRectangle | None = None
        self.bounds: QgsRectangle | None = None
        self.options = RenderOptions()
        self._original_renderers: dict[str, object] = {}
        self._styled_layers: set[str] = set()
        self._samples: dict[str, dict[int, int]] = {}

    # ------------------------------------------------------------ state
    @property
    def styled_layer_ids(self) -> set[str]:
        return set(self._styled_layers)

    def has_portrait(self) -> bool:
        return bool(self._styled_layers)

    @staticmethod
    def background_painted() -> bool:
        """True while the map background carries a preset paper colour."""
        saved, has_saved = QgsProject.instance().readEntry(PROJECT_SCOPE, ORIGINAL_BACKGROUND_KEY, "")
        return bool(has_saved and saved)

    def reset(self) -> None:
        """Forget every layer, image, and frame (the project was replaced)."""
        self.profile = None
        self.frame_container = None
        self.bounds = None
        self._original_renderers.clear()
        self._styled_layers.clear()
        self._samples.clear()

    def adopt_project_layers(self) -> int:
        """Re-attach portrait layers saved in the current project.

        Their saved renderer already draws the portrait; adopting them makes
        live updates, restyling, and *Restore original styles* work again.
        """
        adopted = 0
        for layer in QgsProject.instance().mapLayers().values():
            if not isinstance(layer, QgsVectorLayer) or not layer.customProperty(STYLED_PROPERTY, False):
                continue
            if layer.id() in self._styled_layers:
                continue
            original = None
            with suppress(Exception):
                original = renderer_from_xml(layer.customProperty(ORIGINAL_RENDERER_PROPERTY, ""))
            if original is not None:
                self._original_renderers[layer.id()] = original
            self._styled_layers.add(layer.id())
            adopted += 1
        return adopted

    # ------------------------------------------------------------ image and frame
    def set_image(self, path: str) -> None:
        self.profile = ImageProfile.load(path)
        if self.frame_container is not None:
            self.set_bounds(self.frame_container)
        self.message.emit(
            f"Image loaded: {Path(path).name} "
            f"({self.profile.source_width} x {self.profile.source_height})"
        )

    def set_bounds(self, rectangle: QgsRectangle) -> None:
        if rectangle.isEmpty() or rectangle.width() <= 0 or rectangle.height() <= 0:
            raise ValueError("Image frame must have a positive width and height.")
        self.frame_container = QgsRectangle(rectangle)
        if self.profile is None:
            self.bounds = QgsRectangle(rectangle)
            return
        fitted = fit_bounds_to_aspect(
            (rectangle.xMinimum(), rectangle.yMinimum(), rectangle.xMaximum(), rectangle.yMaximum()),
            self.profile.aspect_ratio,
        )
        self.bounds = QgsRectangle(*fitted)

    # ------------------------------------------------------------ styling
    def apply(self, layers: list[QgsVectorLayer]) -> tuple[int, int]:
        if self.profile is None:
            raise ValueError("Choose a portrait image first.")
        if self.bounds is None:
            self.set_bounds(self.canvas.extent())
        total_sampled = 0
        total_visible = 0
        styled = 0
        for layer in layers:
            if not layer.isValid() or not layer.isSpatial() or layer.renderer() is None:
                continue
            if layer.id() not in self._original_renderers:
                original = layer.renderer().clone()
                self._original_renderers[layer.id()] = original
                with suppress(Exception):
                    layer.setCustomProperty(ORIGINAL_RENDERER_PROPERTY, renderer_to_xml(original))
            sampled, visible = self._sample_layer(layer)
            total_sampled += sampled
            total_visible += visible
            layer.setRenderer(self._build_renderer(layer))
            layer.setCustomProperty(STYLED_PROPERTY, True)
            layer.triggerRepaint()
            self._styled_layers.add(layer.id())
            styled += 1
        if styled == 0:
            raise ValueError("None of the selected layers has geometry to style.")
        self._apply_background()
        self.canvas.refresh()
        self.message.emit(
            f"Styled {styled} layer(s); sampled {total_sampled} of {total_visible} visible features."
        )
        return total_sampled, total_visible

    def refresh(self) -> tuple[int, int]:
        """Resample every styled layer for the current view and frame."""
        if self.profile is None or self.bounds is None:
            return 0, 0
        total_sampled = 0
        total_visible = 0
        for layer in self._live_layers():
            sampled, visible = self._sample_layer(layer)
            total_sampled += sampled
            total_visible += visible
            layer.setRenderer(self._build_renderer(layer))
            layer.triggerRepaint()
        self.canvas.refresh()
        self.message.emit(f"Live update: {total_sampled} sampled feature(s).")
        return total_sampled, total_visible

    def restyle(self) -> None:
        """Re-apply the preset to the existing samples without resampling."""
        for layer in self._live_layers():
            if layer.id() in self._samples:
                layer.setRenderer(self._build_renderer(layer))
                layer.triggerRepaint()
        if self._styled_layers or self.background_painted():
            self._apply_background()
        self.canvas.refresh()

    def restore(self, layer_ids: set[str] | None = None) -> int:
        targets = set(self._styled_layers) if layer_ids is None else set(layer_ids)
        restored = 0
        project = QgsProject.instance()
        for layer_id in targets:
            layer = project.mapLayer(layer_id)
            renderer = self._original_renderers.get(layer_id)
            if isinstance(layer, QgsVectorLayer) and renderer is not None:
                layer.setRenderer(renderer.clone())
                layer.removeCustomProperty(STYLED_PROPERTY)
                layer.removeCustomProperty(ORIGINAL_RENDERER_PROPERTY)
                layer.triggerRepaint()
                restored += 1
            self._styled_layers.discard(layer_id)
            self._original_renderers.pop(layer_id, None)
            self._samples.pop(layer_id, None)
        if not self._styled_layers:
            self._restore_background()
        self.canvas.refresh()
        self.message.emit(f"Restored {restored} original renderer(s).")
        return restored

    def dispose(self) -> None:
        self.restore()

    def _live_layers(self) -> list[QgsVectorLayer]:
        project = QgsProject.instance()
        layers = []
        for layer_id in tuple(self._styled_layers):
            layer = project.mapLayer(layer_id)
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                layers.append(layer)
            else:
                self._styled_layers.discard(layer_id)
                self._original_renderers.pop(layer_id, None)
                self._samples.pop(layer_id, None)
        return layers

    # ------------------------------------------------------------ paper colour
    def _apply_background(self) -> None:
        if not self.options.paint_background:
            self._restore_background()
            return
        preset = PRESETS.get(self.options.preset, PRESETS["Ink Portrait"])
        project = QgsProject.instance()
        saved, has_saved = project.readEntry(PROJECT_SCOPE, ORIGINAL_BACKGROUND_KEY, "")
        if not (has_saved and saved):
            project.writeEntry(PROJECT_SCOPE, ORIGINAL_BACKGROUND_KEY,
                               self.canvas.canvasColor().name(QColor.NameFormat.HexArgb))
        self._set_background(QColor(preset["background"]))

    def _restore_background(self) -> None:
        project = QgsProject.instance()
        saved, has_saved = project.readEntry(PROJECT_SCOPE, ORIGINAL_BACKGROUND_KEY, "")
        if has_saved and saved and QColor(saved).isValid():
            self._set_background(QColor(saved))
        project.removeEntry(PROJECT_SCOPE, ORIGINAL_BACKGROUND_KEY)

    def _set_background(self, color: QColor) -> None:
        with suppress(AttributeError):
            QgsProject.instance().setBackgroundColor(color)
        self.canvas.setCanvasColor(color)

    # ------------------------------------------------------------ sampling
    def _sample_layer(self, layer: QgsVectorLayer) -> tuple[int, int]:
        if self.profile is None or self.bounds is None:
            raise RuntimeError("Portrait image and geographic frame are required.")
        project = QgsProject.instance()
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        to_layer = QgsCoordinateTransform(canvas_crs, layer.crs(), project)
        to_canvas = QgsCoordinateTransform(layer.crs(), canvas_crs, project)
        request = QgsFeatureRequest().setNoAttributes()
        # A view that cannot be expressed in the layer CRS (e.g. a polar view
        # of a global layer) samples everything and lets the frame decide.
        with suppress(QgsCsException):
            request.setFilterRect(to_layer.transformBoundingBox(self.canvas.extent()))
        limit = max(100, int(self.options.max_features))
        bounds_tuple = (self.bounds.xMinimum(), self.bounds.yMinimum(),
                        self.bounds.xMaximum(), self.bounds.yMaximum())
        geometry_type = layer.geometryType()
        values: dict[int, int] = {}
        visible = 0
        for feature in layer.getFeatures(request):
            visible += 1
            if len(values) >= limit:
                continue
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            geometry = QgsGeometry(geometry)
            try:
                geometry.transform(to_canvas)
            except QgsCsException:
                continue
            luminances = []
            for point in self._sample_points(geometry, geometry_type):
                normalized = map_to_normalized(point.x(), point.y(), bounds_tuple)
                if normalized is not None:
                    luminances.append(self.profile.sample(normalized.u, normalized.v, self.options))
            if luminances:
                values[int(feature.id())] = int(round(sum(luminances) / len(luminances)))
        self._samples[layer.id()] = values
        self.progress.emit(len(values), visible)
        return len(values), visible

    def _sample_points(self, geometry: QgsGeometry, geometry_type: int) -> list[QgsPointXY]:
        mode = self.options.sampling
        if geometry_type == QgsWkbTypes.GeometryType.PointGeometry:
            return [geometry.centroid().asPoint()]
        if geometry_type == QgsWkbTypes.GeometryType.LineGeometry:
            length = geometry.length()
            fractions = (0.5,) if mode == "Fast" else ((0.2, 0.5, 0.8) if mode == "Balanced" else (0.1, 0.3, 0.5, 0.7, 0.9))
            if length > 0:
                return [geometry.interpolate(length * fraction).asPoint() for fraction in fractions]
        representative = geometry.pointOnSurface()
        points = [representative.asPoint() if not representative.isEmpty() else geometry.centroid().asPoint()]
        if geometry_type == QgsWkbTypes.GeometryType.PolygonGeometry and mode != "Fast":
            centroid = geometry.centroid()
            if not centroid.isEmpty():
                points.append(centroid.asPoint())
        return points

    # ------------------------------------------------------------ renderer
    def _build_renderer(self, layer: QgsVectorLayer) -> QgsCategorizedSymbolRenderer:
        preset = PRESETS.get(self.options.preset, PRESETS["Ink Portrait"])
        groups = group_by_tone(self._samples.get(layer.id(), {}))
        opacity = max(0.0, min(1.0, self.options.opacity))
        renderer = QgsCategorizedSymbolRenderer("$id", [])
        for index in range(5):
            symbol = self._make_symbol(layer.geometryType(), preset, index)
            symbol.setOpacity(opacity)
            # Category value: the feature ids of this tone, or "" for the
            # catch-all Paper class that also covers unsampled features.
            value = groups[index] if index < 4 else ""
            render = not (index == 4 and preset["hide_highlights"])
            label = TONE_LABELS[index] if index < 4 else "Paper and unsampled"
            renderer.addCategory(QgsRendererCategory(value, symbol, label, render))
        return renderer

    @staticmethod
    def _make_symbol(geometry_type: int, preset: dict, index: int):
        color = QColor(preset["colors"][index])
        width = float(preset["widths"][index])
        if geometry_type == QgsWkbTypes.GeometryType.LineGeometry:
            symbol = QgsLineSymbol.createSimple({
                "line_color": color.name(), "line_width": str(width),
                "capstyle": "round", "joinstyle": "round",
            })
            if index < 3:
                underlay = QgsSimpleLineSymbolLayer.create({
                    "line_color": QColor(color).darker(250).name(),
                    "line_width": str(width + 0.35), "line_style": "solid",
                    "capstyle": "round", "joinstyle": "round",
                })
                if underlay is not None:
                    symbol.insertSymbolLayer(0, underlay)
            return symbol
        if geometry_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            fill = QColor(color)
            fill.setAlpha(225 if index < 3 else 150)
            return QgsFillSymbol.createSimple({
                "color": fill.name(QColor.NameFormat.HexArgb),
                "outline_color": QColor(color).darker(145).name(),
                "outline_width": str(max(0.08, width * 0.22)),
            })
        return QgsMarkerSymbol.createSimple({
            "name": "circle", "color": color.name(),
            "outline_color": QColor(color).darker(180).name(),
            "size": str(max(0.4, width * 1.8)),
        })

    # ------------------------------------------------------------ halftone
    def generate_halftone(self, grid_size: int = 60, pattern: str = "Square"):
        """Add a variable-radius halftone layer for the current portrait and frame."""
        if self.profile is None:
            raise ValueError("Load an image first.")
        if self.bounds is None:
            self.set_bounds(self.canvas.extent())
        from .stipple import generate_stipple_layer
        preset = PRESETS.get(self.options.preset, PRESETS["Ink Portrait"])
        bounds_tuple = (
            self.bounds.xMinimum(), self.bounds.yMinimum(),
            self.bounds.xMaximum(), self.bounds.yMaximum()
        )
        layer = generate_stipple_layer(
            bounds=bounds_tuple,
            crs=self.canvas.mapSettings().destinationCrs(),
            profile=self.profile,
            render_options=self.options,
            grid_size=grid_size,
            pattern=pattern,
            ink_color=preset["colors"][0],
            layer_name=f"Urban Portrait Halftone ({self.options.preset})",
        )
        if layer is not None and layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            if self.options.paint_background:
                self._apply_background()
            self.canvas.refresh()
            self.message.emit(f"Generated halftone layer ({layer.featureCount()} dots).")
        return layer
