# -*- coding: utf-8 -*-
"""02Urban Portrait QGIS plugin lifecycle."""
from __future__ import annotations

import os
from contextlib import suppress

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QMessageBox, QToolBar

try:
    from qgis.PyQt.QtWidgets import QAction
except ImportError:  # pragma: no cover - Qt6
    from qgis.PyQt.QtGui import QAction


TITLE = "02Urban Portrait - City as a Face"


class O2UrbanPortraitPlugin:
    """Toolbar action and dock coordinator."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.toolbar = None
        self.actions = []
        self.dock = None
        self._previous_tool = None

    def initGui(self) -> None:  # noqa: N802 - QGIS API
        self.toolbar = QToolBar("02Urban Portrait Toolbar")
        self.toolbar.setObjectName("O2UrbanPortraitToolbar")
        self.iface.addToolBar(self.toolbar)
        self.panel_action = QAction(
            QIcon(os.path.join(self.plugin_dir, "icons", "icon.png")), TITLE,
            self.iface.mainWindow(),
        )
        self.panel_action.setCheckable(True)
        self.panel_action.setStatusTip("Create a live portrait from vector infrastructure")
        self.panel_action.triggered.connect(self._toggle_dock)
        self.toolbar.addAction(self.panel_action)
        self.actions.append(self.panel_action)

    def unload(self) -> None:
        if self.dock is not None:
            with suppress(Exception):
                self.dock.dispose()
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        if self.toolbar is not None:
            for action in self.actions:
                self.toolbar.removeAction(action)
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
        self.actions.clear()

    def _toggle_dock(self) -> None:
        if self.dock is None:
            try:
                from .dialogs.dock import UrbanPortraitDock

                self.dock = UrbanPortraitDock(self.iface, self.iface.mainWindow())
                self.dock.setObjectName("O2UrbanPortraitDock")
                self.dock.visibilityChanged.connect(self.panel_action.setChecked)
                self.dock.request_map_tool.connect(self._set_map_tool)
                self.dock.request_unset_tool.connect(self._unset_map_tool)
                self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
            except Exception as exc:
                QMessageBox.critical(self.iface.mainWindow(), TITLE, f"Could not open the studio:\n{exc}")
                self.panel_action.setChecked(False)
                return
        visible = not self.dock.isVisible()
        self.dock.setVisible(visible)
        if visible:
            self.dock.raise_()

    def _set_map_tool(self, tool) -> None:
        canvas = self.iface.mapCanvas()
        current = canvas.mapTool()
        if current is not tool:
            self._previous_tool = current
        canvas.setMapTool(tool)

    def _unset_map_tool(self, tool) -> None:
        canvas = self.iface.mapCanvas()
        if canvas.mapTool() is tool:
            if self._previous_tool is not None:
                canvas.setMapTool(self._previous_tool)
            else:
                canvas.unsetMapTool(tool)
        self._previous_tool = None

    def show_about(self) -> None:
        QMessageBox.about(
            self.iface.mainWindow(), TITLE,
            "<h3>02Urban Portrait</h3><p>Live luminance cartography for QGIS.</p>"
            "<p>Smart image analysis is local and source features remain untouched.</p>",
        )
