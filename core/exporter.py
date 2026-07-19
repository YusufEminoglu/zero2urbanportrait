"""One-click export of the current canvas composition."""
from __future__ import annotations

from qgis.core import (
    QgsLayoutExporter,
    QgsLayoutItemMap,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsPrintLayout,
    QgsProject,
    QgsUnitTypes,
)


def export_canvas(canvas, path: str, output_format: str, dpi: int = 300) -> None:
    """Export a temporary single-map layout as PNG, PDF, or SVG."""
    project = QgsProject.instance()
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("02Urban Portrait temporary export")
    page = layout.pageCollection().page(0)
    ratio = canvas.width() / max(1, canvas.height())
    page_height = 210.0
    page_width = max(120.0, min(420.0, page_height * ratio))
    page.setPageSize(QgsLayoutSize(page_width, page_height, QgsUnitTypes.LayoutUnit.LayoutMillimeters))
    map_item = QgsLayoutItemMap(layout)
    layout.addLayoutItem(map_item)
    map_item.attemptMove(QgsLayoutPoint(0, 0, QgsUnitTypes.LayoutUnit.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(page_width, page_height, QgsUnitTypes.LayoutUnit.LayoutMillimeters))
    map_item.setExtent(canvas.extent())
    map_item.setLayers(canvas.layers())
    map_item.setBackgroundEnabled(True)
    map_item.setFrameEnabled(False)
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
