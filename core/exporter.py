"""One-click export of the current canvas composition."""
from __future__ import annotations

from qgis.core import (
    QgsFillSymbol,
    QgsLayoutExporter,
    QgsLayoutItemMap,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsPrintLayout,
    QgsProject,
    QgsUnitTypes,
)


def page_size_for_ratio(ratio: float, long_side: float = 420.0, short_side: float = 210.0) -> tuple[float, float]:
    """Return a page (mm) with exactly the canvas aspect ratio, A3-bounded."""
    ratio = float(ratio) if ratio and ratio > 0 else 1.0
    if ratio >= 1.0:
        width = min(long_side, short_side * ratio)
        return width, width / ratio
    height = min(long_side, short_side / ratio)
    return height * ratio, height


def export_canvas(canvas, path: str, output_format: str, dpi: int = 300) -> None:
    """Export a temporary single-map layout as PNG, PDF, or SVG."""
    project = QgsProject.instance()
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("02Urban Portrait temporary export")
    page = layout.pageCollection().page(0)
    page_width, page_height = page_size_for_ratio(canvas.width() / max(1, canvas.height()))
    page.setPageSize(QgsLayoutSize(page_width, page_height, QgsUnitTypes.LayoutUnit.LayoutMillimeters))
    map_settings = canvas.mapSettings()
    map_item = QgsLayoutItemMap(layout)
    layout.addLayoutItem(map_item)
    map_item.attemptMove(QgsLayoutPoint(0, 0, QgsUnitTypes.LayoutUnit.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(page_width, page_height, QgsUnitTypes.LayoutUnit.LayoutMillimeters))
    map_item.setCrs(map_settings.destinationCrs())
    map_item.setMapRotation(map_settings.rotation())
    # zoomToExtent keeps the item size; setExtent would resize it off the page.
    map_item.zoomToExtent(canvas.extent())
    map_item.setLayers(canvas.layers())
    # The artwork's paper is the canvas colour (a preset may have painted it);
    # the layout default would silently print every portrait on white.
    map_item.setBackgroundColor(canvas.canvasColor())
    map_item.setBackgroundEnabled(True)
    map_item.setFrameEnabled(False)
    page.setPageStyleSymbol(QgsFillSymbol.createSimple({
        "color": canvas.canvasColor().name(), "outline_style": "no",
    }))
    exporter = QgsLayoutExporter(layout)
    output_format = output_format.upper()
    if output_format == "PDF":
        settings = QgsLayoutExporter.PdfExportSettings()
        result = exporter.exportToPdf(path, settings)
    elif output_format == "SVG":
        settings = QgsLayoutExporter.SvgExportSettings()
        settings.forceVectorOutput = True
        result = exporter.exportToSvg(path, settings)
    else:
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = max(72, min(1200, int(dpi)))
        result = exporter.exportToImage(path, settings)
    if result != QgsLayoutExporter.ExportResult.Success:
        raise RuntimeError(f"QGIS export failed with result code {int(result)}.")
