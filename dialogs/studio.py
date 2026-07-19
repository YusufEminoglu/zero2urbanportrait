"""Expanded studio with built-in OSM acquisition and map export."""
from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)
from qgis.core import QgsProject, QgsWkbTypes

from ..core.exporter import export_canvas
from ..core.osm_download import OsmDownloadManager, validate_download_extent
from .dock import UrbanPortraitDock as _BaseDock


class UrbanPortraitDock(_BaseDock):
    """Version-two dock that keeps the proven portrait workflow intact."""

    def __init__(self, iface, parent=None):
        self.osm_manager = OsmDownloadManager(parent)
        super().__init__(iface, parent)
        self._build_data_source_panel()
        self._build_frame_visibility_control()
        self._build_export_panel()
        self._connect_extended_signals()

    def _content_layout(self):
        return self.widget().widget().layout()

    def _build_data_source_panel(self) -> None:
        box = QGroupBox("Data source - choose either workflow")
        layout = QVBoxLayout(box)
        explanation = QLabel(
            "A. Use vector layers already in the project, or B. add the OSM basemap, "
            "zoom to a small urban area, and download portrait-ready vectors."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        row = QHBoxLayout()
        self.add_basemap_button = QPushButton("1. Add OSM basemap")
        self.download_osm_button = QPushButton("2. Download current view")
        row.addWidget(self.add_basemap_button)
        row.addWidget(self.download_osm_button)
        layout.addLayout(row)
        self.osm_area_label = QLabel("Safety limit: maximum 6 x 6 km and 25 km².")
        self.osm_area_label.setWordWrap(True)
        self.osm_area_label.setStyleSheet("color: #475569;")
        layout.addWidget(self.osm_area_label)
        self._content_layout().insertWidget(1, box)

    def _build_frame_visibility_control(self) -> None:
        frame_box = self.canvas_frame_button.parentWidget()
        frame_layout = frame_box.layout()
        self.show_frame = QCheckBox("Show portrait frame on map")
        self.show_frame.setChecked(False)
        frame_layout.addWidget(self.show_frame)
        self._frame_band.hide()

    def _build_export_panel(self) -> None:
        box = QGroupBox("6. Export map artwork")
        form = QFormLayout(box)
        self.export_format = QComboBox()
        self.export_format.addItems(("PNG", "PDF", "SVG"))
        self.export_dpi = QSpinBox()
        self.export_dpi.setRange(72, 1200)
        self.export_dpi.setValue(300)
        self.export_dpi.setSuffix(" dpi")
        self.export_map_button = QPushButton("Export current composition...")
        form.addRow("Format", self.export_format)
        form.addRow("Raster resolution", self.export_dpi)
        form.addRow(self.export_map_button)
        root = self._content_layout()
        root.insertWidget(max(0, root.count() - 2), box)

    def _connect_extended_signals(self) -> None:
        self.add_basemap_button.clicked.connect(self._add_osm_basemap)
        self.download_osm_button.clicked.connect(self._download_osm)
        self.osm_manager.started.connect(self._osm_started)
        self.osm_manager.finished.connect(self._osm_finished)
        self.osm_manager.failed.connect(self._osm_failed)
        self.show_frame.toggled.connect(self._toggle_frame_visibility)
        self.export_map_button.clicked.connect(self._export_map)
        self.canvas.extentsChanged.connect(self._update_osm_area_label)
        self._update_osm_area_label()

    def _add_osm_basemap(self) -> None:
        try:
            layer = self.osm_manager.add_basemap()
        except RuntimeError as exc:
            self._set_status(str(exc), error=True)
            return
        self._set_status(
            f"{layer.name()} added. Pan and zoom to the target neighbourhood, then use Download current view."
        )

    def _update_osm_area_label(self) -> None:
        try:
            _bbox, summary = validate_download_extent(
                self.canvas.extent(), self.canvas.mapSettings().destinationCrs()
            )
            self.osm_area_label.setText(f"Current view: {summary}. Ready to download.")
            self.osm_area_label.setStyleSheet("color: #166534;")
            if not self.osm_manager.busy:
                self.download_osm_button.setEnabled(True)
        except (ValueError, RuntimeError) as exc:
            self.osm_area_label.setText(str(exc))
            self.osm_area_label.setStyleSheet("color: #b45309;")
            if not self.osm_manager.busy:
                self.download_osm_button.setEnabled(False)

    def _download_osm(self) -> None:
        try:
            self.osm_manager.download(
                self.canvas.extent(), self.canvas.mapSettings().destinationCrs()
            )
        except (ValueError, RuntimeError) as exc:
            self._set_status(str(exc), error=True)

    def _osm_started(self, summary: str) -> None:
        self.download_osm_button.setEnabled(False)
        self.download_osm_button.setText("Downloading...")
        self.progress.setRange(0, 0)
        self._set_status(f"Downloading roads, buildings, and land use for {summary}...")

    def _osm_finished(self, layers: list) -> None:
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        group = root.findGroup("02Urban Portrait - OSM Download")
        if group is None:
            group = root.insertGroup(0, "02Urban Portrait - OSM Download")
        layer_ids = set()
        counts = []
        for layer in layers:
            project.addMapLayer(layer, False)
            group.addLayer(layer)
            layer_ids.add(layer.id())
            counts.append(f"{layer.name()}: {layer.featureCount()}")
        self._refresh_layers()
        for row in range(self.layer_list.count()):
            item = self.layer_list.item(row)
            if item.data(0x0100) in layer_ids:  # Qt.UserRole remains 0x0100 in Qt5/Qt6.
                item.setSelected(True)
        self.engine.set_bounds(self.canvas.extent())
        self._show_frame(self.engine.bounds)
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.download_osm_button.setText("2. Download current view")
        self._update_osm_area_label()
        self._set_status("OSM vectors added and selected. " + "; ".join(counts))

    def _osm_failed(self, message: str) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.download_osm_button.setText("2. Download current view")
        self._update_osm_area_label()
        self._set_status(message, error=True)

    def _toggle_frame_visibility(self, visible: bool) -> None:
        if visible and self.engine.bounds is not None:
            super()._show_frame(self.engine.bounds)
            self._frame_band.show()
        else:
            self._frame_band.hide()

    def _show_frame(self, rectangle) -> None:
        super()._show_frame(rectangle)
        if hasattr(self, "show_frame") and not self.show_frame.isChecked():
            self._frame_band.hide()

    def _apply(self) -> None:
        super()._apply()
        if self.engine._styled_layers and hasattr(self, "show_frame"):
            self.show_frame.setChecked(False)
            self._frame_band.hide()

    def _export_map(self) -> None:
        output_format = self.export_format.currentText()
        extension = output_format.lower()
        filters = {
            "PNG": "PNG image (*.png)",
            "PDF": "PDF document (*.pdf)",
            "SVG": "SVG vector image (*.svg)",
        }
        suggested = f"urban_portrait.{extension}"
        path, _selected_filter = QFileDialog.getSaveFileName(
            self, "Export urban portrait", suggested, filters[output_format]
        )
        if not path:
            return
        if Path(path).suffix.lower() != f".{extension}":
            path += f".{extension}"
        self.show_frame.setChecked(False)
        try:
            export_canvas(self.canvas, path, output_format, self.export_dpi.value())
        except (OSError, RuntimeError) as exc:
            self._set_status(str(exc), error=True)
            return
        self._set_status(f"Export complete: {path}")

    def dispose(self) -> None:
        self.osm_manager.cancel()
        with suppress(TypeError, RuntimeError):
            self.canvas.extentsChanged.disconnect(self._update_osm_area_label)
        super().dispose()
