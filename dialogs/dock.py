"""Dock interface for the live urban portrait workflow."""
from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path

from qgis.PyQt.QtCore import QEvent, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPixmap
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStyle,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsRubberBand

from ..core.engine import PortraitEngine, RenderOptions
from ..core.presets import PRESETS, export_presets_json, import_presets_json
from ..tools.frame_tool import FrameMapTool
from .theme import apply_adaptive_theme, dock_color_tokens


TITLE = "02Urban Portrait"


class StepNodeWidget(QFrame):
    """Interactive visual stepper with 3 numbered circular badge nodes and dynamic step guide."""

    step_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("stepperContainer")
        self._current_step = 0
        self._step_completed = [False, False, False]
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        nodes_row = QHBoxLayout()
        nodes_row.setContentsMargins(2, 2, 2, 2)
        nodes_row.setSpacing(4)

        self._step_buttons = []
        step_definitions = [
            ("1", "Set up"),
            ("2", "Shape"),
            ("3", "Export"),
        ]

        for idx, (num, title) in enumerate(step_definitions):
            btn = QPushButton(f"  {num}  {title}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, i=idx: self.step_clicked.emit(i))
            self._step_buttons.append(btn)
            nodes_row.addWidget(btn, 1)
            if idx < len(step_definitions) - 1:
                arrow = QLabel("➔")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arrow.setStyleSheet("color: #64748b; font-weight: bold; font-size: 11px;")
                nodes_row.addWidget(arrow)

        layout.addLayout(nodes_row)

        self.guide_label = QLabel("👉 Step 1: Upload a portrait picture and select vector layers.")
        self.guide_label.setObjectName("stepGuideLabel")
        self.guide_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.guide_label.setWordWrap(True)
        layout.addWidget(self.guide_label)

    def set_current_step(self, step: int) -> None:
        self._current_step = max(0, min(step, 2))
        self.refresh()

    def set_completed(self, step: int, completed: bool) -> None:
        if 0 <= step < len(self._step_completed):
            self._step_completed[step] = completed
            self.refresh()

    def set_guide_text(self, text: str) -> None:
        self.guide_label.setText(text)

    def refresh(self) -> None:
        step_names = ["Set up", "Shape", "Export"]
        badges = ["❶", "❷", "❸"]

        for i, btn in enumerate(self._step_buttons):
            name = step_names[i]
            is_active = (i == self._current_step)
            is_done = self._step_completed[i]

            badge = "✔" if is_done and not is_active else badges[i]
            btn.setText(f"{badge}  {name}")

            if is_active:
                btn.setStyleSheet(
                    "QPushButton { background-color: #0891b2; color: #ffffff; "
                    "font-weight: 700; border: 2px solid #22d3ee; border-radius: 12px; "
                    "padding: 5px 8px; font-size: 10px; }"
                )
            elif is_done:
                btn.setStyleSheet(
                    "QPushButton { background-color: rgba(6, 182, 212, 0.16); color: #06b6d4; "
                    "font-weight: 600; border: 1px solid #0891b2; border-radius: 12px; "
                    "padding: 5px 8px; font-size: 10px; }"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { background-color: rgba(100, 116, 139, 0.12); color: #94a3b8; "
                    "font-weight: 500; border: 1px solid rgba(148, 163, 184, 0.3); border-radius: 12px; "
                    "padding: 5px 8px; font-size: 10px; }"
                )


class UrbanPortraitDock(QDockWidget):
    request_map_tool = pyqtSignal(object)
    request_unset_tool = pyqtSignal(object)

    def __init__(self, iface, parent=None):
        super().__init__("02Urban Portrait - City as a Face", parent)
        self._restoring_state = False
        self._preview_pixmap = QPixmap()
        self._halftone_layer_ids: set[str] = set()
        self._export_completed = False
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
        self.setMinimumWidth(390)
        self._apply_theme()
        shell = QWidget(self)
        shell.setObjectName("studioShell")
        root = QVBoxLayout(shell)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(9)

        hero = QFrame(shell)
        hero.setObjectName("heroCard")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(14, 13, 14, 13)
        hero_layout.setSpacing(11)
        icon_label = QLabel()
        icon_label.setFixedSize(50, 50)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QPixmap(str(Path(__file__).resolve().parents[1] / "icons" / "icon.png"))
        if not icon.isNull():
            icon_label.setPixmap(
                icon.scaled(
                    46, 46, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        hero_layout.addWidget(icon_label)
        hero_copy = QVBoxLayout()
        hero_copy.setSpacing(2)
        title = QLabel("02Urban Portrait")
        title.setObjectName("heroTitle")
        subtitle = QLabel("Shape the city into a face")
        subtitle.setObjectName("heroSubtitle")
        hero_copy.addWidget(title)
        hero_copy.addWidget(subtitle)
        hero_layout.addLayout(hero_copy, 1)
        badge = QLabel("LOCAL  ·  SAFE")
        badge.setObjectName("localBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        root.addWidget(hero)

        # ── Interactive 3-Stage Workflow Stepper ─────────────────────────
        self.stepper = StepNodeWidget(shell)
        root.addWidget(self.stepper)

        self.tabs = QTabWidget(shell)
        self.tabs.setDocumentMode(True)
        self.setup_layout = self._create_tab(self.tabs, "Set up")
        self.style_layout = self._create_tab(self.tabs, "Portrait")
        self.output_layout = self._create_tab(self.tabs, "Export")
        root.addWidget(self.tabs, 1)

        # ══════════════════════════════════════════════════════════════════
        # TAB 1: SET UP
        # ══════════════════════════════════════════════════════════════════
        image_box = QGroupBox("❶ Step 1.1 · Upload Portrait Picture")
        image_layout = QVBoxLayout(image_box)
        image_layout.setSpacing(8)
        self.preview = QLabel("No image selected")
        self.preview.setFixedHeight(180)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setObjectName("imagePreview")
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
        self.image_details.setObjectName("successHint")
        image_layout.addWidget(self.image_details)
        self.browse_button.setObjectName("accentButton")
        self.browse_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        self.setup_layout.addWidget(image_box)

        layer_box = QGroupBox("❷ Step 1.2 · Select Vector Canvas")
        layer_layout = QVBoxLayout(layer_box)
        layer_hint = QLabel("Select the roads, buildings or points that will carry the portrait.")
        layer_hint.setWordWrap(True)
        layer_hint.setObjectName("mutedHint")
        layer_layout.addWidget(layer_hint)
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
        self.refresh_layers_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.setup_layout.addWidget(layer_box)

        frame_box = QGroupBox("❸ Step 1.3 · Geographic Frame Placement")
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
        aspect_note.setObjectName("mutedHint")
        frame_layout.addWidget(aspect_note)
        self.setup_layout.addWidget(frame_box)

        self.next_to_shape_btn = QPushButton("Proceed to Step 2: Shape Portrait ➔")
        self.next_to_shape_btn.setObjectName("primaryButton")
        self.next_to_shape_btn.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        self.setup_layout.addWidget(self.next_to_shape_btn)
        self.setup_layout.addStretch(1)

        # ══════════════════════════════════════════════════════════════════
        # TAB 2: PORTRAIT (SHAPE)
        # ══════════════════════════════════════════════════════════════════
        style_box = QGroupBox("❹ Step 2.1 · Art Direction & Presets")
        form = QFormLayout(style_box)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)
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
        palette_btn_row = QHBoxLayout()
        self.import_palette_btn = QPushButton("Import JSON…")
        self.export_palette_btn = QPushButton("Export JSON…")
        self.import_palette_btn.clicked.connect(self._import_presets)
        self.export_palette_btn.clicked.connect(self._export_presets)
        palette_btn_row.addWidget(self.import_palette_btn)
        palette_btn_row.addWidget(self.export_palette_btn)
        form.addRow("Palettes", palette_btn_row)

        form.addRow("Geometry sampling", self.sampling)
        form.addRow("Gamma", self.gamma)
        form.addRow("Smart edge emphasis", self.edge)
        form.addRow("Layer opacity", self.opacity)
        form.addRow("Visible feature limit", self.max_features)
        form.addRow(self.auto_contrast)
        form.addRow(self.invert)
        self.style_layout.addWidget(style_box)

        # ── Live Render Box ───────────────────────────────────────────
        live_box = QGroupBox("❺ Step 2.2 · Render Live Portrait")
        live_layout = QVBoxLayout(live_box)
        live_hint = QLabel("Create once, then tune the portrait while the map updates in place.")
        live_hint.setWordWrap(True)
        live_hint.setObjectName("mutedHint")
        live_layout.addWidget(live_hint)
        self.live = QCheckBox("Live update during map navigation")
        self.live.setChecked(True)
        live_layout.addWidget(self.live)
        render_row = QHBoxLayout()
        self.apply_button = QPushButton("Create portrait")
        self.apply_button.setObjectName("primaryButton")
        self.update_button = QPushButton("Update")
        render_row.addWidget(self.apply_button, 2)
        render_row.addWidget(self.update_button)
        live_layout.addLayout(render_row)
        self.style_layout.addWidget(live_box)

        # ── Vector Stippling & Halftone Studio ────────────────────────
        stipple_box = QGroupBox("✨ Step 2.3 · Vector Halftone & Engraving Studio")
        stipple_layout = QVBoxLayout(stipple_box)
        stipple_hint = QLabel("Convert the portrait into an algorithmic vector stippled engraving layer with variable-radius dot density.")
        stipple_hint.setWordWrap(True)
        stipple_hint.setObjectName("mutedHint")
        stipple_layout.addWidget(stipple_hint)

        stipple_row = QHBoxLayout()
        stipple_row.addWidget(QLabel("Grid resolution:"))
        self.stipple_grid = QSpinBox()
        self.stipple_grid.setRange(20, 200)
        self.stipple_grid.setValue(60)
        self.stipple_grid.setSingleStep(10)
        stipple_row.addWidget(self.stipple_grid)
        self.stipple_btn = QPushButton("✨ Generate Halftone Layer")
        self.stipple_btn.setObjectName("accentButton")
        self.stipple_btn.clicked.connect(self._generate_halftone)
        stipple_row.addWidget(self.stipple_btn)
        stipple_layout.addLayout(stipple_row)
        self.style_layout.addWidget(stipple_box)

        self.next_to_export_btn = QPushButton("Proceed to Step 3: Export Artwork ➔")
        self.next_to_export_btn.setObjectName("primaryButton")
        self.next_to_export_btn.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        self.style_layout.addWidget(self.next_to_export_btn)
        self.style_layout.addStretch(1)

        # ══════════════════════════════════════════════════════════════════
        # TAB 3: EXPORT
        # ══════════════════════════════════════════════════════════════════
        export_intro = QLabel(
            "Finish the composition, export the map artwork, or keep a reusable QGIS style."
        )
        export_intro.setWordWrap(True)
        export_intro.setObjectName("tabIntro")
        self.output_layout.addWidget(export_intro)

        safe_box = QGroupBox("❻ Step 3.1 · Style Portability & Recovery")
        safe_layout = QVBoxLayout(safe_box)
        safe_hint = QLabel(
            "Export one selected portrait layer as QML, or restore every source renderer instantly."
        )
        safe_hint.setWordWrap(True)
        safe_hint.setObjectName("mutedHint")
        safe_layout.addWidget(safe_hint)
        safe_row = QHBoxLayout()
        self.restore_button = QPushButton("Restore original styles")
        self.export_button = QPushButton("Export QML...")
        self.restore_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogResetButton)
        )
        self.export_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        safe_row.addWidget(self.restore_button)
        safe_row.addWidget(self.export_button)
        safe_layout.addLayout(safe_row)
        self.output_layout.addWidget(safe_box)
        self.output_layout.addStretch(1)

        # ── Bottom Progress & Status ──────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        root.addWidget(self.progress)
        self.status = QLabel("Ready. Choose a portrait image and one or more vector layers.")
        self.status.setWordWrap(True)
        self.status.setObjectName("statusCard")
        root.addWidget(self.status)
        self.setWidget(shell)

    def _create_tab(self, tabs: QTabWidget, title: str) -> QVBoxLayout:
        scroll = QScrollArea(tabs)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget(scroll)
        page.setObjectName("tabPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(9, 12, 9, 12)
        layout.setSpacing(11)
        scroll.setWidget(page)
        tabs.addTab(scroll, title)
        return layout

    def _apply_theme(self) -> None:
        root = self.widget()
        if root is None or getattr(self, "_theme_refreshing", False):
            return
        self._theme_refreshing = True
        try:
            apply_adaptive_theme(root)
        finally:
            self._theme_refreshing = False

    def _connect_signals(self) -> None:
        self.tabs.currentChanged.connect(self._tab_changed)
        self.stepper.step_clicked.connect(self.tabs.setCurrentIndex)
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

    def _tab_changed(self, index: int) -> None:
        self.stepper.set_current_step(index)
        self._update_step_guide()

    def _update_step_guide(self) -> None:
        has_image = self.engine.profile is not None
        has_layers = len(self.selected_layers()) > 0
        has_portrait = bool(self.engine._styled_layers or self._halftone_layer_ids)
        current = self.tabs.currentIndex()

        if current == 0:
            if not has_image:
                self.stepper.set_guide_text("👉 Step 1.1: Click 'Upload picture...' to select a portrait image.")
            elif not has_layers:
                self.stepper.set_guide_text("👉 Step 1.2: Select one or more vector layers from the list below.")
            else:
                self.stepper.set_guide_text("✅ Step 1 ready! Click 'Proceed to Step 2 ➔' or adjust frame.")
        elif current == 1:
            if not has_portrait:
                self.stepper.set_guide_text("👉 Step 2: Choose an art preset and click 'Create portrait'.")
            else:
                self.stepper.set_guide_text("✅ Portrait active! Tune style sliders or proceed to Step 3.")
        else:
            self.stepper.set_guide_text("👉 Step 3: Export the composition artwork or save layer QML style.")

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
        has_image = self.engine.profile is not None
        has_layers = bool(selected)
        has_styled = bool(styled)
        has_portrait = bool(styled or self._halftone_layer_ids)
        can_shape = has_image and has_layers

        self.apply_button.setEnabled(can_shape)
        self.update_button.setEnabled(has_styled)
        self.restore_button.setEnabled(has_styled)
        self.export_button.setEnabled(
            len(selected) == 1 and selected[0].id() in styled
        )

        self.next_to_shape_btn.setEnabled(can_shape)
        self.next_to_shape_btn.setToolTip(
            "Continue to portrait controls." if can_shape
            else "Upload an image and select at least one vector layer first."
        )
        self.next_to_export_btn.setEnabled(has_portrait)
        self.next_to_export_btn.setToolTip(
            "Continue to artwork export." if has_portrait
            else "Create a portrait before continuing to export."
        )
        self.stepper.set_completed(0, can_shape)
        self.stepper.set_completed(1, has_portrait)
        self.stepper.set_completed(2, self._export_completed)
        self._update_step_guide()

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
        if not self.selected_layers() and self.layer_list.count() > 0:
            self.layer_list.item(0).setSelected(True)
        self._update_controls()

    def _select_active(self) -> None:
        active = self.iface.activeLayer()
        if not isinstance(active, QgsVectorLayer):
            self._set_status("Active layer is not a vector layer.", error=True)
            return
        for row in range(self.layer_list.count()):
            item = self.layer_list.item(row)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) == active.id())
        self._update_controls()

    def _choose_image(self) -> None:
        filters = "Supported pictures (*.jpg *.jpeg *.png *.tif *.tiff *.webp);;All files (*.*)"
        path, _selected_filter = QFileDialog.getOpenFileName(self, "Select portrait image", "", filters)
        if not path:
            return
        try:
            self.engine.set_image(path)
        except ValueError as exc:
            self._set_status(str(exc), error=True)
            return
        self._display_loaded_image()
        if self.engine.bounds is None or self.follow_canvas.isChecked():
            self.engine.set_bounds(self.canvas.extent())
            self._show_frame(self.engine.bounds)
        self._update_controls()
        self._write_project_state()

    def _use_canvas_frame(self) -> None:
        if self.engine.profile is None:
            self._set_status("Choose an image before setting the frame.", error=True)
            return
        self.engine.set_bounds(self.canvas.extent())
        self._show_frame(self.engine.bounds)
        self._style_changed()

    def _draw_frame(self) -> None:
        if self.engine.profile is None:
            self._set_status("Choose an image before drawing a frame.", error=True)
            return
        self.request_map_tool.emit(self.frame_tool)
        self._set_status("Click and drag a box across the map canvas.")

    def _accept_frame(self, rectangle: QgsRectangle) -> None:
        self.request_unset_tool.emit(self.frame_tool)
        self.engine.set_bounds(rectangle)
        self._show_frame(self.engine.bounds)
        self._style_changed()

    def _show_frame(self, rectangle: QgsRectangle | None) -> None:
        if rectangle is None:
            self._frame_band.hide()
            self.frame_label.setText("Frame: not set")
            return
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
        try:
            self.engine.restyle()
            self.engine.refresh()
        except (RuntimeError, ValueError) as exc:
            self._set_status(f"Portrait update failed: {exc}", error=True)
            return
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
        if (self.live.isChecked() and self.engine.profile is not None
                and self.engine._styled_layers):
            self._live_timer.start()

    def _live_refresh(self) -> None:
        if self.engine.profile is None or not self.engine._styled_layers:
            return
        if self.follow_canvas.isChecked():
            self.engine.set_bounds(self.canvas.extent())
            self._show_frame(self.engine.bounds)
        self.engine.options = self._options()
        self.engine.refresh()

    def _restore(self) -> None:
        restored = self.engine.restore()
        self._set_status(f"Restored {restored} original layer style(s).")
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
        if ok:
            self._export_completed = True
            self._update_controls()
        self._set_status(f"Style exported: {path}" if ok else f"Could not export style: {result}", error=not ok)

    def _generate_halftone(self) -> None:
        if self.engine.profile is None:
            self._set_status("Choose a portrait picture first.", error=True)
            return
        grid = self.stipple_grid.value()
        self.engine.options = self._options()
        try:
            layer = self.engine.generate_halftone(grid_size=grid)
            if layer:
                self._halftone_layer_ids.add(layer.id())
                self._set_status(f"Halftone stipple layer generated ({layer.featureCount()} dots).")
                self._refresh_layers()
                self._update_controls()
        except Exception as exc:
            self._set_status(f"Halftone generation failed: {exc}", error=True)

    def _import_presets(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Palette Presets", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            loaded = import_presets_json(path)
            PRESETS.update(loaded)
            current = self.preset.currentText()
            self.preset.clear()
            self.preset.addItems(list(PRESETS))
            if current in PRESETS:
                self.preset.setCurrentText(current)
            self._set_status(f"Imported {len(loaded)} palette preset(s) from {Path(path).name}.")
        except Exception as exc:
            self._set_status(f"Palette import failed: {exc}", error=True)

    def _export_presets(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Palette Presets", "urban_portrait_presets.json", "JSON Files (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            export_presets_json(path)
            self._set_status(f"Saved palette presets to: {path}")
        except Exception as exc:
            self._set_status(f"Palette export failed: {exc}", error=True)

    def _set_progress(self, sampled: int, visible: int) -> None:
        self.progress.setRange(0, max(1, visible))
        self.progress.setValue(min(sampled, max(1, visible)))

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status.setText(text)
        if error:
            t = dock_color_tokens()
            self.status.setStyleSheet(
                f"color: {t['error_text']}; background: {t['error_bg']}; "
                f"border: 1px solid {t['error_border']}; "
                "border-radius: 8px; padding: 8px 10px;"
            )
        else:
            t = dock_color_tokens()
            self.status.setStyleSheet(
                f"color: {t['text']}; background: {t['card']}; "
                f"border: 1px solid {t['border']}; "
                "border-radius: 8px; padding: 8px 10px;"
            )
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

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        ):
            self._apply_theme()

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
