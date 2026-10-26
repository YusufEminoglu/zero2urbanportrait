"""QGIS runtime acceptance checks for 02Urban Portrait.

Run from the plugins root on both runtimes:

    python-qgis-ltr.bat -m zero2urbanportrait.tests.smoke_qgis
    python-qgis.bat     -m zero2urbanportrait.tests.smoke_qgis

Every check renders or reads back real QGIS state: pixel colours on a rendered
map, a project saved to disk and read again, a PNG written by the exporter.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsLineSymbol,
    QgsMapRendererSequentialJob,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QSize  # noqa: E402
from qgis.PyQt.QtGui import QColor, QImage  # noqa: E402

application = QgsApplication([], False)
application.initQgis()

from qgis.gui import QgsMapCanvas  # noqa: E402

from zero2urbanportrait.core.engine import (  # noqa: E402
    ORIGINAL_RENDERER_PROPERTY,
    STYLED_PROPERTY,
    ImageProfile,
    PortraitEngine,
    RenderOptions,
)
from zero2urbanportrait.core.exporter import export_canvas, page_size_for_ratio  # noqa: E402
from zero2urbanportrait.core.presets import PRESETS  # noqa: E402
from zero2urbanportrait.core.stipple import generate_stipple_layer  # noqa: E402

CRS = QgsCoordinateReferenceSystem("EPSG:3857")
EXTENT = QgsRectangle(0, 0, 1000, 1000)
WORK = Path(tempfile.mkdtemp(prefix="z2up_smoke_"))
RESULTS: list[tuple[str, bool, str]] = []


def check(name):
    def wrap(function):
        try:
            function()
            RESULTS.append((name, True, ""))
        except Exception:  # report every failure, keep running the rest
            RESULTS.append((name, False, traceback.format_exc()))
        return function
    return wrap


def gradient_image(path: Path) -> Path:
    """Black on the left, white on the right."""
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    for x in range(200):
        tone = round(x * 255 / 199)
        for y in range(200):
            image.setPixel(x, y, QColor(tone, tone, tone).rgba())
    image.save(str(path))
    return path


def vertical_lines(count: int = 20) -> QgsVectorLayer:
    layer = QgsVectorLayer("LineString?crs=EPSG:3857", "streets", "memory")
    features = []
    for index in range(count):
        x = 25 + index * 50
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, 50), QgsPointXY(x, 950)]))
        features.append(feature)
    layer.dataProvider().addFeatures(features)
    layer.updateExtents()
    layer.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple(
        {"line_color": "#ff00ff", "line_width": "1.5"})))
    return layer


def new_canvas() -> QgsMapCanvas:
    canvas = QgsMapCanvas()
    canvas.resize(500, 500)
    canvas.setDestinationCrs(CRS)
    canvas.setExtent(EXTENT)
    canvas.setCanvasColor(QColor("#ffffff"))
    return canvas


def render(layer: QgsVectorLayer, background: QColor | None = None) -> QImage:
    from qgis.core import QgsMapSettings
    settings = QgsMapSettings()
    settings.setLayers([layer])
    settings.setDestinationCrs(CRS)
    settings.setExtent(EXTENT)
    settings.setOutputSize(QSize(400, 400))
    settings.setBackgroundColor(background or QColor("#ffffff"))
    job = QgsMapRendererSequentialJob(settings)
    job.start()
    job.waitForFinished()
    return job.renderedImage()


def column_colour(image: QImage, map_x: float) -> QColor:
    """Darkest pixel in the column of a vertical line at ``map_x``."""
    px = int(map_x / 1000 * image.width())
    darkest = QColor("#ffffff")
    for dx in (-1, 0, 1):
        colour = QColor(image.pixel(px + dx, image.height() // 2))
        if colour.lightness() < darkest.lightness():
            darkest = colour
    return darkest


IMAGE = gradient_image(WORK / "gradient.png")


@check("renderer is self-contained and follows the image tones")
def _renderer_follows_tones():
    QgsProject.instance().clear()
    layer = vertical_lines()
    QgsProject.instance().addMapLayer(layer)
    canvas = new_canvas()
    engine = PortraitEngine(canvas)
    engine.set_image(str(IMAGE))
    engine.set_bounds(EXTENT)
    engine.options = RenderOptions(preset="Ink Portrait", auto_contrast=False, edge_amount=0.0)
    sampled, visible = engine.apply([layer])
    assert (sampled, visible) == (20, 20), (sampled, visible)
    renderer = layer.renderer()
    assert isinstance(renderer, QgsCategorizedSymbolRenderer), type(renderer)
    assert renderer.classAttribute() == "$id"
    categories = renderer.categories()
    assert len(categories) == 5
    assert categories[4].value() == "" and not categories[4].renderState()  # Ink hides Paper
    deep = set(categories[0].value())
    assert min(f.id() for f in layer.getFeatures()) in deep
    image = render(layer)
    left, right = column_colour(image, 25), column_colour(image, 975)
    assert left.lightness() < 40, left.name()
    assert right.name() == "#ffffff", right.name()  # Paper tone is hidden
    # Lightness rises monotonically from the dark side to the light side.
    tones = [column_colour(image, 25 + i * 50).lightness() for i in range(0, 16, 3)]
    assert tones == sorted(tones), tones
    assert layer.customProperty(STYLED_PROPERTY, False)
    assert layer.customProperty(ORIGINAL_RENDERER_PROPERTY, "")


@check("saved project keeps the portrait and can restore the original style")
def _project_roundtrip():
    QgsProject.instance().clear()
    layer = vertical_lines()
    QgsProject.instance().addMapLayer(layer)
    canvas = new_canvas()
    engine = PortraitEngine(canvas)
    engine.set_image(str(IMAGE))
    engine.set_bounds(EXTENT)
    engine.options = RenderOptions(preset="Neon Night", auto_contrast=False)
    engine.apply([layer])
    before = render(layer)
    # A file-backed copy so the project can be read back with its features.
    path = WORK / "lines.gpkg"
    from qgis.core import QgsVectorFileWriter
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(path), QgsProject.instance().transformContext(), options)
    assert result[0] == QgsVectorFileWriter.WriterError.NoError, result
    disk = QgsVectorLayer(f"{path}|layername=lines", "streets_gpkg", "ogr")
    assert disk.isValid()
    disk.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple(
        {"line_color": "#ff00ff", "line_width": "1.5"})))
    QgsProject.instance().addMapLayer(disk)
    engine.apply([disk])
    disk_id = disk.id()
    disk_before = render(disk)
    project_path = WORK / "portrait.qgz"
    assert QgsProject.instance().write(str(project_path))
    QgsProject.instance().clear()
    assert QgsProject.instance().read(str(project_path))
    reread = QgsProject.instance().mapLayer(disk_id)
    assert isinstance(reread, QgsVectorLayer) and reread.isValid()
    assert isinstance(reread.renderer(), QgsCategorizedSymbolRenderer)
    after = render(reread)
    assert after == disk_before, "saved portrait renders differently after reopening"
    assert before.size() == after.size()
    # A fresh engine (as after a QGIS restart) adopts and restores it.
    engine2 = PortraitEngine(new_canvas())
    assert engine2.adopt_project_layers() >= 1
    assert engine2.restore() >= 1
    restored = reread.renderer()
    assert isinstance(restored, QgsSingleSymbolRenderer), type(restored)
    assert restored.symbol().color().name() == "#ff00ff"
    assert not reread.customProperty(STYLED_PROPERTY, False)


@check("preset paper colour is painted and restored")
def _paper_colour():
    QgsProject.instance().clear()
    layer = vertical_lines()
    QgsProject.instance().addMapLayer(layer)
    canvas = new_canvas()
    engine = PortraitEngine(canvas)
    engine.set_image(str(IMAGE))
    engine.options = RenderOptions(preset="Neon Night")
    engine.apply([layer])
    assert canvas.canvasColor().name() == PRESETS["Neon Night"]["background"], canvas.canvasColor().name()
    assert engine.background_painted()
    engine.options = RenderOptions(preset="Blueprint")
    engine.restyle()
    assert canvas.canvasColor().name() == PRESETS["Blueprint"]["background"]
    engine.restore()
    assert canvas.canvasColor().name() == "#ffffff", canvas.canvasColor().name()
    assert not engine.background_painted()
    engine.options = RenderOptions(preset="Neon Night", paint_background=False)
    engine.apply([layer])
    assert canvas.canvasColor().name() == "#ffffff"


@check("artwork export prints on the canvas paper, at the canvas ratio")
def _export_background():
    assert page_size_for_ratio(3.0) == (420.0, 140.0)
    width, height = page_size_for_ratio(0.5)
    assert abs(width / height - 0.5) < 1e-9 and height <= 420.0
    QgsProject.instance().clear()
    layer = vertical_lines()
    QgsProject.instance().addMapLayer(layer)
    canvas = new_canvas()
    canvas.setLayers([layer])
    engine = PortraitEngine(canvas)
    engine.set_image(str(IMAGE))
    engine.options = RenderOptions(preset="Neon Night")
    engine.apply([layer])
    out = WORK / "export.png"
    export_canvas(canvas, str(out), "PNG", 72)
    exported = QImage(str(out))
    assert not exported.isNull()
    corner = QColor(exported.pixel(2, 2)).name()
    assert corner == PRESETS["Neon Night"]["background"], corner
    ratio = exported.width() / exported.height()
    assert abs(ratio - canvas.width() / canvas.height()) < 0.02, ratio


@check("halftone dots scale with darkness, invert flips them, ink follows the preset")
def _halftone():
    profile = ImageProfile.load(str(IMAGE))
    bounds = (0.0, 0.0, 1000.0, 500.0)
    plain = generate_stipple_layer(bounds, CRS, profile, RenderOptions(auto_contrast=False), 21, "Square",
                                   PRESETS["Neon Night"]["colors"][0])
    inverted = generate_stipple_layer(bounds, CRS, profile, RenderOptions(auto_contrast=False, invert=True), 21)
    assert plain.crs().authid() == "EPSG:3857"

    def radius_by_side(layer):
        left = [f["radius"] for f in layer.getFeatures() if f.geometry().asPoint().x() < 200]
        right = [f["radius"] for f in layer.getFeatures() if f.geometry().asPoint().x() > 800]
        return (sum(left) / len(left) if left else 0.0), (sum(right) / len(right) if right else 0.0)

    left, right = radius_by_side(plain)
    assert left > right * 3, (left, right)
    inv_left, inv_right = radius_by_side(inverted)
    assert inv_right > inv_left * 3, (inv_left, inv_right)
    # Square cells: 21 dots on the long side, 11 on the short side.
    xs = sorted({round(f.geometry().asPoint().x(), 6) for f in plain.getFeatures()})
    ys = sorted({round(f.geometry().asPoint().y(), 6) for f in plain.getFeatures()})
    assert abs((xs[1] - xs[0]) - (ys[1] - ys[0])) < 1e-6, (xs[:2], ys[:2])
    symbol = plain.renderer().symbol()
    assert symbol.color().name() == PRESETS["Neon Night"]["colors"][0]
    feature = next(plain.getFeatures())
    context = plain.createExpressionContext()
    context.setFeature(feature)
    size, ok = symbol.dataDefinedSize().value(context, -1)
    assert ok and abs(float(size) - 2 * feature["radius"]) < 1e-9, (size, ok, feature["radius"])
    hexed = generate_stipple_layer(bounds, CRS, profile, RenderOptions(auto_contrast=False), 21, "Hex")
    rows = {}
    for f in hexed.getFeatures():
        rows.setdefault(round(f.geometry().asPoint().y(), 6), []).append(f.geometry().asPoint().x())
    firsts = sorted(min(v) for v in rows.values())
    assert firsts[-1] - firsts[0] > 1.0, "hex rows are not offset"


class _MessageBar:
    def __init__(self):
        self.warnings = []

    def pushWarning(self, title, text):  # noqa: N802 - QGIS API
        self.warnings.append(text)


class _Iface:
    def __init__(self, canvas):
        self._canvas = canvas
        self._bar = _MessageBar()

    def mapCanvas(self):  # noqa: N802 - QGIS API
        return self._canvas

    def messageBar(self):  # noqa: N802 - QGIS API
        return self._bar

    def activeLayer(self):  # noqa: N802 - QGIS API
        return None

    def mainWindow(self):  # noqa: N802 - QGIS API
        return None


@check("dock lifecycle: create, reconnect a saved portrait, follow project changes")
def _dock_lifecycle():
    from zero2urbanportrait.dialogs.studio import UrbanPortraitDock
    QgsProject.instance().clear()
    layer = vertical_lines()
    path = WORK / "dock_lines.gpkg"
    from qgis.core import QgsVectorFileWriter
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(path), QgsProject.instance().transformContext(), options)
    disk = QgsVectorLayer(f"{path}|layername=dock_lines", "streets", "ogr")
    assert disk.isValid()
    QgsProject.instance().addMapLayer(disk)
    canvas = new_canvas()
    dock = UrbanPortraitDock(_Iface(canvas))
    assert not dock.preset_swatch.pixmap().isNull()
    dock.engine.set_image(str(IMAGE))
    dock._display_loaded_image()
    dock.engine.set_bounds(EXTENT)
    dock.layer_list.selectAll()
    dock.preset.setCurrentText("Blueprint")
    dock._apply()
    assert dock.engine.has_portrait()
    assert dock.restore_button.isEnabled()
    assert canvas.canvasColor().name() == PRESETS["Blueprint"]["background"]
    dock._generate_halftone()
    assert dock._halftone_layer_ids
    project_path = WORK / "dock.qgz"
    dock._write_project_state()
    assert QgsProject.instance().write(str(project_path))
    # Reading the project again must reconnect the portrait (live updates on).
    assert QgsProject.instance().read(str(project_path))
    assert dock.engine.has_portrait(), "saved portrait was not reconnected"
    assert dock.engine.profile is not None
    assert dock.preset.currentText() == "Blueprint"
    assert not dock._halftone_layer_ids  # stale ids from the old project are gone
    dock._restore()
    reread = QgsProject.instance().mapLayersByName("streets")[0]
    assert isinstance(reread.renderer(), QgsSingleSymbolRenderer)
    assert not dock.engine.background_painted()
    QgsProject.instance().clear()
    assert not dock.engine.has_portrait()
    assert dock.engine.profile is None
    dock.dispose()


QgsProject.instance().clear()
application.exitQgis()
failed = [item for item in RESULTS if not item[1]]
for name, ok, detail in RESULTS:
    print(("PASS " if ok else "FAIL ") + name)
    if detail:
        print(detail)
print(f"{'FAIL' if failed else 'PASS'} ({len(RESULTS) - len(failed)}/{len(RESULTS)}) 02Urban Portrait QGIS checks")
sys.exit(1 if failed else 0)
