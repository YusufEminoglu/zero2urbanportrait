"""Live luminance sampling and non-destructive QGIS renderer engine."""
from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QImage, QImageReader, qAlpha, qBlue, qGray, qGreen, qRed
from qgis.core import (
    QgsCoordinateTransform,
    QgsExpression,
    QgsExpressionFunction,
    QgsFeatureRequest,
    QgsFillSymbol,
    QgsGeometry,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsRuleBasedRenderer,
    QgsSimpleLineSymbolLayer,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .presets import PRESETS, TONE_BREAKS
from .profile import adjust_luminance, blend_edge, map_to_normalized, quantile_limits


_LUMINANCE_CACHE: dict[tuple[str, int], int] = {}
_FUNCTION_NAME = "zero2portrait_luma"


class _LuminanceFunction(QgsExpressionFunction):
    def __init__(self):
        super().__init__(_FUNCTION_NAME, 2, "02Urban Portrait")

    def func(self, values, context, parent, node=None):  # noqa: D401
        """Return cached luminance for a layer id and feature id."""
        del context, parent, node
        try:
            return _LUMINANCE_CACHE.get((str(values[0]), int(values[1])), 255)
        except (TypeError, ValueError, IndexError):
            return 255


_EXPRESSION_FUNCTION = _LuminanceFunction()


def register_expression_function() -> None:
    """Register the renderer expression once per QGIS process."""
    if not QgsExpression.isFunctionName(_FUNCTION_NAME):
        QgsExpression.registerFunction(_EXPRESSION_FUNCTION)


def unregister_expression_function() -> None:
    """Remove the renderer expression when the plugin is unloaded."""
    if QgsExpression.isFunctionName(_FUNCTION_NAME):
        QgsExpression.unregisterFunction(_FUNCTION_NAME)


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


class ImageProfile:
    """A downsampled image with fast luminance and edge sampling."""

    def __init__(self, image: QImage, path: str):
        if image.isNull():
            raise ValueError("The selected image could not be decoded.")
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
        self.bounds: QgsRectangle | None = None
        self.options = RenderOptions()
        self._original_renderers: dict[str, object] = {}
        self._styled_layers: set[str] = set()

    def set_image(self, path: str) -> None:
        self.profile = ImageProfile.load(path)
        self.message.emit(f"Image loaded: {Path(path).name} ({self.profile.image.width()} x {self.profile.image.height()})")

    def set_bounds(self, rectangle: QgsRectangle) -> None:
        if rectangle.isEmpty() or rectangle.width() <= 0 or rectangle.height() <= 0:
            raise ValueError("Image frame must have a positive width and height.")
        self.bounds = QgsRectangle(rectangle)

    def apply(self, layers: list[QgsVectorLayer]) -> tuple[int, int]:
        if self.profile is None:
            raise ValueError("Choose a portrait image first.")
        if self.bounds is None:
            self.set_bounds(self.canvas.extent())
        register_expression_function()
        total_sampled = 0
        total_visible = 0
        for layer in layers:
            if not layer.isValid():
                continue
            if layer.id() not in self._original_renderers:
                self._original_renderers[layer.id()] = layer.renderer().clone()
            sampled, visible = self._sample_layer(layer)
            total_sampled += sampled
            total_visible += visible
            layer.setRenderer(self._build_renderer(layer))
            layer.setCustomProperty("zero2urbanportrait/styled", True)
            layer.triggerRepaint()
            self._styled_layers.add(layer.id())
        self.canvas.refresh()
        self.message.emit(f"Styled {len(layers)} layer(s); sampled {total_sampled} of {total_visible} visible features.")
        return total_sampled, total_visible

    def refresh(self) -> tuple[int, int]:
        project = QgsProject.instance()
        layers = [project.mapLayer(layer_id) for layer_id in self._styled_layers]
        valid = [layer for layer in layers if isinstance(layer, QgsVectorLayer) and layer.isValid()]
        if not valid or self.profile is None or self.bounds is None:
            return 0, 0
        total_sampled = 0
        total_visible = 0
        for layer in valid:
            sampled, visible = self._sample_layer(layer)
            total_sampled += sampled
            total_visible += visible
            layer.triggerRepaint()
        self.canvas.refresh()
        self.message.emit(f"Live update: {total_sampled} sampled feature(s).")
        return total_sampled, total_visible

    def restyle(self) -> None:
        project = QgsProject.instance()
        for layer_id in tuple(self._styled_layers):
            layer = project.mapLayer(layer_id)
            if isinstance(layer, QgsVectorLayer):
                layer.setRenderer(self._build_renderer(layer))
                layer.triggerRepaint()
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
                layer.removeCustomProperty("zero2urbanportrait/styled")
                layer.triggerRepaint()
                restored += 1
            self._styled_layers.discard(layer_id)
            self._original_renderers.pop(layer_id, None)
            stale = [key for key in _LUMINANCE_CACHE if key[0] == layer_id]
            for key in stale:
                _LUMINANCE_CACHE.pop(key, None)
        self.canvas.refresh()
        self.message.emit(f"Restored {restored} original renderer(s).")
        return restored

    def dispose(self) -> None:
        self.restore()
        unregister_expression_function()

    def _sample_layer(self, layer: QgsVectorLayer) -> tuple[int, int]:
        if self.profile is None or self.bounds is None:
            raise RuntimeError("Portrait image and geographic frame are required.")
        project = QgsProject.instance()
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        to_layer = QgsCoordinateTransform(canvas_crs, layer.crs(), project)
        to_canvas = QgsCoordinateTransform(layer.crs(), canvas_crs, project)
        request_rect = to_layer.transformBoundingBox(self.canvas.extent())
        request = QgsFeatureRequest().setFilterRect(request_rect).setNoAttributes()
        limit = max(100, int(self.options.max_features))
        values: dict[tuple[str, int], int] = {}
        visible = 0
        sampled = 0
        for feature in layer.getFeatures(request):
            visible += 1
            if sampled >= limit:
                continue
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            geometry = QgsGeometry(geometry)
            with suppress(Exception):
                geometry.transform(to_canvas)
            points = self._sample_points(geometry, layer.geometryType())
            luminances = []
            bounds_tuple = (self.bounds.xMinimum(), self.bounds.yMinimum(),
                            self.bounds.xMaximum(), self.bounds.yMaximum())
            for point in points:
                normalized = map_to_normalized(point.x(), point.y(), bounds_tuple)
                if normalized is not None:
                    luminances.append(self.profile.sample(normalized.u, normalized.v, self.options))
            value = int(round(sum(luminances) / len(luminances))) if luminances else 255
            values[(layer.id(), int(feature.id()))] = value
            sampled += 1
        stale = [key for key in _LUMINANCE_CACHE if key[0] == layer.id()]
        for key in stale:
            _LUMINANCE_CACHE.pop(key, None)
        _LUMINANCE_CACHE.update(values)
        self.progress.emit(sampled, visible)
        return sampled, visible

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

    def _build_renderer(self, layer: QgsVectorLayer) -> QgsRuleBasedRenderer:
        preset = PRESETS.get(self.options.preset, PRESETS["Ink Portrait"])
        root = QgsRuleBasedRenderer.Rule(None)
        layer_id = layer.id().replace("'", "''")
        for index in range(5):
            low, high = TONE_BREAKS[index], TONE_BREAKS[index + 1]
            symbol = self._make_symbol(layer.geometryType(), preset, index)
            symbol.setOpacity(max(0.0, min(1.0, self.options.opacity)))
            if index == 4 and preset["hide_highlights"]:
                symbol.setOpacity(0.0)
            rule = QgsRuleBasedRenderer.Rule(symbol)
            rule.setLabel(("Deep shadow", "Shadow", "Midtone", "Highlight", "Paper")[index])
            rule.setFilterExpression(
                f"{_FUNCTION_NAME}('{layer_id}', $id) >= {low} AND "
                f"{_FUNCTION_NAME}('{layer_id}', $id) < {high}"
            )
            root.appendChild(rule)
        return QgsRuleBasedRenderer(root)

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
