"""Dock interface for the live urban portrait workflow."""
from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path

from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPixmap
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsRubberBand

from ..core.engine import PortraitEngine, RenderOptions
from ..core.presets import PRESETS
from ..tools.frame_tool import FrameMapTool


TITLE = "02Urban Portrait"


class UrbanPortraitDock(QDockWidget):
    request_map_tool = pyqtSignal(object)
    request_unset_tool = pyqtSignal(object)

    def __init__(self, iface, parent=None):
        super().__init__("02Urban Portrait - City as a Face", parent)
        self._restoring_state = False
        self._preview_pixmap = QPixmap()
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.engine = PortraitEngine(self.canvas, self)
        self.frame_tool = FrameMapTool(self.canvas)
        self._frame_band = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self._frame_band.setStrokeColor(QColor("#ff477e"))
        self._frame_band.setFillColor(QColor(255, 71, 126, 22))
        self._frame_band.setWidth(2)
        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(240)
        self._live_timer.timeout.connect(self._live_refresh)
        self._build_ui()
        self._connect_signals()
        self._refresh_layers()
        self._restore_project_state()
        self._update_controls()

    def _build_ui(self) -> None:
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget(scroll)
        root = QVBoxLayout(container)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        intro = QLabel("Turn streets and buildings into a portrait. Source features are never edited.")
        intro.setWordWrap(True)
        intro.setStyleSheet("font-weight: 600; color: #334155;")
        root.addWidget(intro)

        image_box = QGroupBox("1. Portrait mask")
        image_layout = QVBoxLayout(image_box)
        self.preview = QLabel("No image selected")
        self.preview.setFixedHeight(180)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background: #071023; color: #94a3b8; border-radius: 6px;")
        image_layout.addWidget(self.preview)
        image_row = QHBoxLayout()
        self.image_path = QLabel("Choose JPG, PNG, TIFF, or WebP")
        self.image_path.setWordWrap(True)
        self.browse_button = QPushButton("Upload picture...")
        image_row.addWidget(self.image_path, 1)
        image_row.addWidget(self.browse_button)
        image_layout.addLayout(image_row)
        self.image_details = QLabel("Aspect ratio is always preserved; images are never stretched.")
        self.image_details.setWordWrap(True)
        self.image_details.setStyleSheet("color: #0f766e;")
        image_layout.addWidget(self.image_details)
        root.addWidget(image_box)

        layer_box = QGroupBox("2. Vector layers")
        layer_layout = QVBoxLayout(layer_box)
        self.layer_list = QListWidget()
        self.layer_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.layer_list.setMinimumHeight(105)
        layer_layout.addWidget(self.layer_list)
        layer_buttons = QHBoxLayout()
        self.active_button = QPushButton("Active")
        self.all_button = QPushButton("All vectors")
        self.refresh_layers_button = QPushButton("Refresh")
        layer_buttons.addWidget(self.active_button)
        layer_buttons.addWidget(self.all_button)
        layer_buttons.addWidget(self.refresh_layers_button)
        layer_layout.addLayout(layer_buttons)
        root.addWidget(layer_box)

        frame_box = QGroupBox("3. Geographic image frame")
        frame_layout = QVBoxLayout(frame_box)
        frame_buttons = QHBoxLayout()
        self.canvas_frame_button = QPushButton("Use canvas extent")
        self.draw_frame_button = QPushButton("Draw frame")
        frame_buttons.addWidget(self.canvas_frame_button)
        frame_buttons.addWidget(self.draw_frame_button)
        frame_layout.addLayout(frame_buttons)
        self.follow_canvas = QCheckBox("Screen-locked mask (frame follows pan and zoom)")
        self.follow_canvas.setToolTip("Off: the image stays at fixed map coordinates. On: it follows the viewport.")
        frame_layout.addWidget(self.follow_canvas)
        self.frame_label = QLabel("Frame: not set (canvas extent will be used)")
        self.frame_label.setWordWrap(True)
        frame_layout.addWidget(self.frame_label)
        aspect_note = QLabel("The frame is automatically fitted to the uploaded picture ratio.")
        aspect_note.setWordWrap(True)
        aspect_note.setStyleSheet("color: #64748b;")
        frame_layout.addWidget(aspect_note)
        root.addWidget(frame_box)

        style_box = QGroupBox("4. Art direction")
        form = QFormLayout(style_box)
        self.preset = QComboBox()
        self.preset.addItems(list(PRESETS))
        self.sampling = QComboBox()
        self.sampling.addItems(("Fast", "Balanced", "High quality"))
        self.sampling.setCurrentText("Balanced")
        self.gamma = QDoubleSpinBox()
        self.gamma.setRange(0.2, 3.0)
        self.gamma.setSingleStep(0.1)
        self.gamma.setValue(1.0)
        self.edge = QDoubleSpinBox()
        self.edge.setRange(0.0, 1.0)
        self.edge.setSingleStep(0.1)
        self.edge.setValue(0.25)
        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0.05, 1.0)
        self.opacity.setSingleStep(0.05)
        self.opacity.setValue(1.0)
        self.max_features = QSpinBox()
        self.max_features.setRange(500, 100000)
        self.max_features.setSingleStep(500)
        self.max_features.setValue(10000)
        self.auto_contrast = QCheckBox("Smart percentile stretch")
        self.auto_contrast.setChecked(True)
        self.invert = QCheckBox("Invert light and shadow")
        form.addRow("Preset", self.preset)
        form.addRow("Geometry sampling", self.sampling)
        form.addRow("Gamma", self.gamma)
        form.addRow("Smart edge emphasis", self.edge)
        form.addRow("Layer opacity", self.opacity)
        form.addRow("Visible feature limit", self.max_features)
        form.addRow(self.auto_contrast)
        form.addRow(self.invert)
        root.addWidget(style_box)

        live_box = QGroupBox("5. Render")
        live_layout = QVBoxLayout(live_box)
        self.live = QCheckBox("Live update during map navigation")
        self.live.setChecked(True)
        live_layout.addWidget(self.live)
        render_row = QHBoxLayout()
        self.apply_button = QPushButton("Create portrait")
        self.apply_button.setStyleSheet("font-weight: 700; padding: 7px; background: #22d3ee; color: #082f49;")
        self.update_button = QPushButton("Update")
        render_row.addWidget(self.apply_button, 2)
        render_row.addWidget(self.update_button)
        live_layout.addLayout(render_row)
        safe_row = QHBoxLayout()
        self.restore_button = QPushButton("Restore original styles")
        self.export_button = QPushButton("Export QML...")
        safe_row.addWidget(self.restore_button)
        safe_row.addWidget(self.export_button)
        live_layout.addLayout(safe_row)
        root.addWidget(live_box)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        root.addWidget(self.progress)
        self.status = QLabel("Ready. Choose a portrait image and one or more vector layers.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: #475569; padding: 5px;")
        root.addWidget(self.status)
        root.addStretch(1)
        scroll.setWidget(container)
        self.setWidget(scroll)

    def _connect_signals(self) -> None:
        self.browse_button.clicked.connect(self._choose_image)
        self.refresh_layers_button.clicked.connect(self._refresh_layers)
        self.layer_list.itemSelectionChanged.connect(self._update_controls)
        self.active_button.clicked.connect(self._select_active)
        self.all_button.clicked.connect(self.layer_list.selectAll)
        self.canvas_frame_button.clicked.connect(self._use_canvas_frame)
        self.draw_frame_button.clicked.connect(self._draw_frame)
        self.frame_tool.frame_created.connect(self._accept_frame)
        self.frame_tool.cancelled.connect(lambda: self.request_unset_tool.emit(self.frame_tool))
        self.apply_button.clicked.connect(self._apply)
        self.update_button.clicked.connect(self._manual_update)
        self.restore_button.clicked.connect(self._restore)
        self.export_button.clicked.connect(self._export_qml)
        self.engine.message.connect(self._set_status)
        self.engine.progress.connect(self._set_progress)
        self.canvas.extentsChanged.connect(self._schedule_live)
        project = QgsProject.instance()
        project.layersAdded.connect(self._project_layers_changed)
        project.layersRemoved.connect(self._project_layers_changed)
        self.follow_canvas.toggled.connect(self._follow_canvas_changed)
        for widget in (self.preset, self.sampling, self.gamma, self.edge, self.opacity,
                       self.max_features, self.auto_contrast, self.invert):
            signal = getattr(widget, "currentTextChanged", None) or getattr(widget, "valueChanged", None) or getattr(widget, "toggled", None)
            if signal is not None:
                signal.connect(self._style_changed)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._update_image_preview()

    def _project_layers_changed(self, _layers=None) -> None:
        self._refresh_layers()

    def _display_loaded_image(self) -> None:
        if self.engine.profile is None:
            return
        profile = self.engine.profile
        path = Path(profile.path)
        self.image_path.setText(path.name)
        self.image_path.setToolTip(str(path))
        width = profile.source_width
        height = profile.source_height
        self.image_details.setText(
            f"{width} x {height} px - aspect {width / height:.3f}:1 - ratio locked"
        )
        self._preview_pixmap = QPixmap.fromImage(profile.image)
        self._update_image_preview()

    def _update_image_preview(self) -> None:
        if self._preview_pixmap.isNull() or not hasattr(self, "preview"):
            return
        size = self.preview.contentsRect().size()
        if size.width() <= 1 or size.height() <= 1:
            return
        self.preview.setPixmap(
            self._preview_pixmap.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _update_controls(self) -> None:
        if not hasattr(self, "apply_button"):
            return
        selected = self.selected_layers()
        styled = self.engine._styled_layers
        self.apply_button.setEnabled(self.engine.profile is not None and bool(selected))
        self.update_button.setEnabled(bool(styled))
        self.restore_button.setEnabled(bool(styled))
        self.export_button.setEnabled(
            len(selected) == 1 and selected[0].id() in styled
        )

    def selected_layers(self) -> list[QgsVectorLayer]:
        project = QgsProject.instance()
        layers = []
        for item in self.layer_list.selectedItems():
            layer = project.mapLayer(item.data(Qt.ItemDataRole.UserRole))
            if isinstance(layer, QgsVectorLayer):
                layers.append(layer)
        return layers

    def _refresh_layers(self) -> None:
        selected = {layer.id() for layer in self.selected_layers()} if hasattr(self, "layer_list") else set()
        self.layer_list.clear()
        layers = [layer for layer in QgsProject.instance().mapLayers().values() if isinstance(layer, QgsVectorLayer)]
        for layer in sorted(layers, key=lambda candidate: candidate.name().lower()):
            kind = QgsWkbTypes.displayString(layer.wkbType())
            item = QListWidgetItem(f"{layer.name()}  [{kind}]")
            item.setData(Qt.ItemDataRole.UserRole, layer.id())
            self.layer_list.addItem(item)
            if layer.id() in selected:
                item.setSelected(True)

    def _select_active(self) -> None:
        active = self.iface.activeLayer()
        self.layer_list.clearSelection()
        if not isinstance(active, QgsVectorLayer):
            self._set_status("The active layer is not a vector layer.", error=True)
            return
        for row in range(self.layer_list.count()):
            item = self.layer_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == active.id():
                item.setSelected(True)
                self.layer_list.scrollToItem(item)
                return

    def _choose_image(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self, "Upload portrait picture", "", "Images (*.png *.jpg *.jpeg *.tif *.tiff *.webp *.bmp)"
        )
        if not path:
            return
        try:
            self.engine.set_image(path)
        except (ValueError, OSError) as exc:
            self._set_status(str(exc), error=True)
            return
        self._display_loaded_image()
        if self.engine.bounds is not None:
            self._show_frame(self.engine.bounds)
        self._update_controls()
        self._write_project_state()

    def _use_canvas_frame(self) -> None:
        self._accept_frame(self.canvas.extent())

    def _draw_frame(self) -> None:
        self.follow_canvas.setChecked(False)
        self.request_map_tool.emit(self.frame_tool)
        self._set_status("Drag a rectangle over the map to place the portrait.")

    def _accept_frame(self, rectangle: QgsRectangle) -> None:
        self.engine.set_bounds(rectangle)
        self._show_frame(self.engine.bounds)
        self.request_unset_tool.emit(self.frame_tool)
        self._write_project_state()
        self._set_status("Geographic portrait frame set with the picture aspect ratio preserved.")

    def _show_frame(self, rectangle: QgsRectangle) -> None:
        self._frame_band.setToGeometry(QgsGeometry.fromRect(rectangle), None)
        self._frame_band.show()
        self.frame_label.setText(
            f"Frame: {rectangle.xMinimum():.3f}, {rectangle.yMinimum():.3f} to "
            f"{rectangle.xMaximum():.3f}, {rectangle.yMaximum():.3f}"
        )

    def _options(self) -> RenderOptions:
        return RenderOptions(
            preset=self.preset.currentText(), sampling=self.sampling.currentText(),
            gamma=self.gamma.value(), invert=self.invert.isChecked(),
            auto_contrast=self.auto_contrast.isChecked(), edge_amount=self.edge.value(),
            max_features=self.max_features.value(), opacity=self.opacity.value(),
        )

    def _apply(self) -> None:
        layers = self.selected_layers()
        if not layers:
            self._set_status("Select at least one vector layer.", error=True)
            return
        if self.follow_canvas.isChecked() or self.engine.bounds is None:
            self.engine.set_bounds(self.canvas.extent())
            self._show_frame(self.engine.bounds)
        self.engine.options = self._options()
        try:
            self.engine.apply(layers)
        except (ValueError, RuntimeError) as exc:
            self._set_status(str(exc), error=True)
            return
        self._update_controls()
        self._write_project_state()

    def _manual_update(self) -> None:
        if not self.engine._styled_layers:
            self._set_status("Create a portrait before requesting an update.", error=True)
            return
        self.engine.options = self._options()
        if self.follow_canvas.isChecked():
            self.engine.set_bounds(self.canvas.extent())
            self._show_frame(self.engine.bounds)
        self.engine.restyle()
        self.engine.refresh()
        self._write_project_state()

    def _style_changed(self, _value=None) -> None:
        if self._restoring_state:
            return
        self.engine.options = self._options()
        if self.engine._styled_layers:
            self.engine.restyle()
        if self.live.isChecked() and self.engine._styled_layers:
            self._live_timer.start()
        self._write_project_state()

    def _follow_canvas_changed(self, enabled: bool) -> None:
        if self._restoring_state:
            return
        if enabled and self.engine.profile is not None:
            self.engine.set_bounds(self.canvas.extent())
            self._show_frame(self.engine.bounds)
            if self.engine._styled_layers:
                self._live_timer.start()
        self._write_project_state()

    def _schedule_live(self) -> None:
        if self.live.isChecked():
            self._live_timer.start()

    def _live_refresh(self) -> None:
        if self.follow_canvas.isChecked():
            self.engine.set_bounds(self.canvas.extent())
            self._show_frame(self.engine.bounds)
        self.engine.options = self._options()
        self.engine.refresh()

    def _restore(self) -> None:
        selected = {layer.id() for layer in self.selected_layers()}
        self.engine.restore(selected or None)
        self._update_controls()

    def _export_qml(self) -> None:
        layers = self.selected_layers()
        if len(layers) != 1:
            self._set_status("Select exactly one styled layer to export its QML.", error=True)
            return
        default = f"{layers[0].name()}_urban_portrait.qml"
        path, _selected_filter = QFileDialog.getSaveFileName(self, "Export QGIS style", default, "QGIS style (*.qml)")
        if not path:
            return
        if not path.lower().endswith(".qml"):
            path += ".qml"
        result = layers[0].saveNamedStyle(path)
        ok = bool(result[1]) if isinstance(result, tuple) and len(result) > 1 else not bool(result)
        self._set_status(f"Style exported: {path}" if ok else f"Could not export style: {result}", error=not ok)

    def _set_progress(self, sampled: int, visible: int) -> None:
        self.progress.setRange(0, max(1, visible))
        self.progress.setValue(min(sampled, max(1, visible)))

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {'#b91c1c' if error else '#475569'}; padding: 5px;")
        if error:
            self.iface.messageBar().pushWarning(TITLE, text)

    def _write_project_state(self) -> None:
        if self._restoring_state:
            return
        bounds = self.engine.bounds
        container = self.engine.frame_container
        state = {
            "image": self.engine.profile.path if self.engine.profile else "",
            "bounds": [bounds.xMinimum(), bounds.yMinimum(), bounds.xMaximum(), bounds.yMaximum()] if bounds else [],
            "frame_container": [
                container.xMinimum(), container.yMinimum(),
                container.xMaximum(), container.yMaximum(),
            ] if container else [],
            "preset": self.preset.currentText(), "sampling": self.sampling.currentText(),
            "gamma": self.gamma.value(), "edge": self.edge.value(), "opacity": self.opacity.value(),
            "invert": self.invert.isChecked(), "auto_contrast": self.auto_contrast.isChecked(),
            "max_features": self.max_features.value(), "follow_canvas": self.follow_canvas.isChecked(),
        }
        QgsProject.instance().writeEntry("zero2urbanportrait", "state", json.dumps(state))

    def _restore_project_state(self) -> None:
        raw, ok = QgsProject.instance().readEntry("zero2urbanportrait", "state", "")
        if not ok or not raw:
            return
        self._restoring_state = True
        try:
            state = json.loads(raw)
            image = state.get("image", "")
            if image and Path(image).is_file():
                self.engine.set_image(image)
                self._display_loaded_image()
            bounds = state.get("frame_container", state.get("bounds", []))
            if len(bounds) == 4:
                self.engine.set_bounds(QgsRectangle(*bounds))
                self._show_frame(self.engine.bounds)
            self.preset.setCurrentText(state.get("preset", "Ink Portrait"))
            self.sampling.setCurrentText(state.get("sampling", "Balanced"))
            self.gamma.setValue(float(state.get("gamma", 1.0)))
            self.edge.setValue(float(state.get("edge", 0.25)))
            self.opacity.setValue(float(state.get("opacity", 1.0)))
            self.invert.setChecked(bool(state.get("invert", False)))
            self.auto_contrast.setChecked(bool(state.get("auto_contrast", True)))
            self.max_features.setValue(int(state.get("max_features", 10000)))
            self.follow_canvas.setChecked(bool(state.get("follow_canvas", False)))
        except (TypeError, ValueError, json.JSONDecodeError):
            self._set_status("Saved portrait settings could not be restored.", error=True)
        finally:
            self._restoring_state = False

    def dispose(self) -> None:
        self._live_timer.stop()
        with suppress(TypeError, RuntimeError):
            self.canvas.extentsChanged.disconnect(self._schedule_live)
        project = QgsProject.instance()
        with suppress(TypeError, RuntimeError):
            project.layersAdded.disconnect(self._project_layers_changed)
        with suppress(TypeError, RuntimeError):
            project.layersRemoved.disconnect(self._project_layers_changed)
        self.request_unset_tool.emit(self.frame_tool)
        self.frame_tool.dispose()
        self._frame_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self._frame_band.hide()
        self.engine.dispose()
