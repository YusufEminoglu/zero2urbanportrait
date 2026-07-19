"""Drag a geographic image frame directly on the map canvas."""
from __future__ import annotations

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsGeometry, QgsRectangle, QgsWkbTypes
from qgis.gui import QgsMapTool, QgsRubberBand


class FrameMapTool(QgsMapTool):
    frame_created = pyqtSignal(object)
    cancelled = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.start = None
        self.band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.band.setStrokeColor(QColor("#00c2ff"))
        self.band.setFillColor(QColor(0, 194, 255, 35))
        self.band.setWidth(2)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def canvasPressEvent(self, event):  # noqa: N802 - QGIS API
        if event.button() == Qt.MouseButton.LeftButton:
            self.start = self.toMapCoordinates(event.pos())
            self._update(self.start)

    def canvasMoveEvent(self, event):  # noqa: N802 - QGIS API
        if self.start is not None:
            self._update(self.toMapCoordinates(event.pos()))

    def canvasReleaseEvent(self, event):  # noqa: N802 - QGIS API
        if self.start is None or event.button() != Qt.MouseButton.LeftButton:
            return
        end = self.toMapCoordinates(event.pos())
        rectangle = QgsRectangle(self.start, end)
        self.start = None
        self.band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        if rectangle.width() > 0 and rectangle.height() > 0:
            self.frame_created.emit(rectangle)

    def keyPressEvent(self, event):  # noqa: N802 - QGIS API
        if event.key() == Qt.Key.Key_Escape:
            self.start = None
            self.band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self.cancelled.emit()

    def deactivate(self):
        self.start = None
        self.band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        super().deactivate()

    def dispose(self) -> None:
        self.band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.band.hide()

    def _update(self, end) -> None:
        rectangle = QgsRectangle(self.start, end)
        self.band.setToGeometry(QgsGeometry.fromRect(rectangle), None)
