"""Small-area OpenStreetMap download without third-party QGIS plugins."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlencode

from qgis.PyQt.QtCore import QByteArray, QObject, QUrl, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsNetworkAccessManager,
    QgsPointXY,
    QgsProcessingUtils,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
MAX_SIDE_METRES = 6000.0
MAX_AREA_SQUARE_METRES = 25_000_000.0
USER_AGENT = "02UrbanPortrait/0.2 (+https://github.com/YusufEminoglu/zero2urbanportrait)"


def extent_metrics(rectangle: QgsRectangle, crs) -> tuple[QgsRectangle, float, float, float]:
    """Transform an extent to WGS84 and return bbox, width, height, and area."""
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    transform = QgsCoordinateTransform(crs, wgs84, QgsProject.instance())
    bbox = transform.transformBoundingBox(rectangle)
    distance = QgsDistanceArea()
    distance.setEllipsoid("WGS84")
    middle_lat = (bbox.yMinimum() + bbox.yMaximum()) / 2.0
    middle_lon = (bbox.xMinimum() + bbox.xMaximum()) / 2.0
    width = distance.measureLine(
        QgsPointXY(bbox.xMinimum(), middle_lat), QgsPointXY(bbox.xMaximum(), middle_lat)
    )
    height = distance.measureLine(
        QgsPointXY(middle_lon, bbox.yMinimum()), QgsPointXY(middle_lon, bbox.yMaximum())
    )
    return bbox, width, height, width * height


def validate_download_extent(rectangle: QgsRectangle, crs) -> tuple[QgsRectangle, str]:
    """Reject broad or invalid requests before they reach a public Overpass server."""
    if rectangle.isEmpty() or rectangle.width() <= 0 or rectangle.height() <= 0:
        raise ValueError("The map canvas has no valid download area.")
    bbox, width, height, area = extent_metrics(rectangle, crs)
    if bbox.yMinimum() < -85.0 or bbox.yMaximum() > 85.0:
        raise ValueError("OSM download is limited to latitudes between 85 S and 85 N.")
    if bbox.xMinimum() > bbox.xMaximum():
        raise ValueError("Downloads crossing the antimeridian are not supported.")
    if width > MAX_SIDE_METRES or height > MAX_SIDE_METRES or area > MAX_AREA_SQUARE_METRES:
        raise ValueError(
            f"Zoom in before downloading. Current view is {width / 1000:.1f} x "
            f"{height / 1000:.1f} km ({area / 1_000_000:.1f} km2); maximum is "
            "6 x 6 km and 25 km2."
        )
    summary = f"{width / 1000:.2f} x {height / 1000:.2f} km ({area / 1_000_000:.2f} km2)"
    return bbox, summary


def overpass_query(bbox: QgsRectangle) -> str:
    """Build a bounded query for portrait-ready OSM feature families."""
    box = (
        f"{bbox.yMinimum():.7f},{bbox.xMinimum():.7f},"
        f"{bbox.yMaximum():.7f},{bbox.xMaximum():.7f}"
    )
    return (
        "[out:xml][timeout:60][maxsize:268435456];\n(\n"
        f'  way["highway"]({box});\n'
        f'  way["building"]({box});\n'
        f'  relation["building"]({box});\n'
        f'  way["landuse"]({box});\n'
        f'  relation["landuse"]({box});\n'
        ");\n(._;>;);\nout body qt;"
    )


class OsmDownloadManager(QObject):
    """Own a single asynchronous Overpass request and convert its response."""

    started = pyqtSignal(str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reply = None

    @property
    def busy(self) -> bool:
        return self._reply is not None

    def add_basemap(self) -> QgsRasterLayer:
        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            if layer.customProperty("zero2urbanportrait/osm_basemap", False):
                return layer
        uri = "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmin=0&zmax=19"
        layer = QgsRasterLayer(uri, "OpenStreetMap Standard", "wms")
        if not layer.isValid():
            raise RuntimeError("The OpenStreetMap basemap could not be created.")
        layer.setCustomProperty("zero2urbanportrait/osm_basemap", True)
        layer.setAttribution("© OpenStreetMap contributors")
        layer.setAttributionUrl("https://www.openstreetmap.org/copyright")
        project.addMapLayer(layer)
        return layer

    def download(self, rectangle: QgsRectangle, crs) -> None:
        if self.busy:
            raise RuntimeError("An OSM download is already running.")
        bbox, summary = validate_download_extent(rectangle, crs)
        request = QNetworkRequest(QUrl(OVERPASS_URL))
        request.setRawHeader(QByteArray(b"User-Agent"), QByteArray(USER_AGENT.encode("ascii")))
        request.setRawHeader(
            QByteArray(b"Content-Type"), QByteArray(b"application/x-www-form-urlencoded; charset=UTF-8")
        )
        body = QByteArray(urlencode({"data": overpass_query(bbox)}).encode("utf-8"))
        self._reply = QgsNetworkAccessManager.instance().post(request, body)
        self._reply.finished.connect(self._on_finished)
        self.started.emit(summary)

    def cancel(self) -> None:
        if self._reply is not None:
            self._reply.abort()

    def _on_finished(self) -> None:
        reply = self._reply
        self._reply = None
        if reply is None:
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        network_error = reply.error()
        error_code = int(getattr(network_error, "value", network_error))
        payload = bytes(reply.readAll())
        error_text = reply.errorString()
        reply.deleteLater()
        if error_code or not payload:
            if status in (429, 504):
                self.failed.emit(
                    f"Overpass returned HTTP {status}. The public server is busy; wait briefly, "
                    "zoom in further, and retry."
                )
            else:
                self.failed.emit(f"OSM download failed (HTTP {status or 'unknown'}): {error_text}")
            return
        if not payload.lstrip().startswith(b"<?xml") and not payload.lstrip().startswith(b"<osm"):
            self.failed.emit("Overpass returned an unexpected response instead of OSM XML.")
            return
        try:
            layers = self._load_osm_payload(payload)
        except (OSError, RuntimeError, ValueError) as exc:
            self.failed.emit(f"OSM data could not be converted: {exc}")
            return
        if not layers:
            self.failed.emit("No roads, buildings, or land-use polygons were found in this view.")
            return
        self.finished.emit(layers)

    def _load_osm_payload(self, payload: bytes) -> list[QgsVectorLayer]:
        path = Path(QgsProcessingUtils.generateTempFilename("02urbanportrait.osm"))
        path.write_bytes(payload)
        return load_osm_layers(path)


def _tag(feature, field_names: set[str], key: str) -> str:
    if key in field_names:
        value = feature[key]
        if value is not None:
            text = str(value)
            if text and text.lower() != "null":
                return text
    if "other_tags" not in field_names:
        return ""
    other = str(feature["other_tags"] or "")
    match = re.search(rf'"{re.escape(key)}"=>"([^"\\]*(?:\\.[^"\\]*)*)"', other)
    return match.group(1).replace('\\"', '"') if match else ""


def _copy_tagged(source: QgsVectorLayer, name: str, geometry_uri: str, key: str) -> QgsVectorLayer | None:
    if not source.isValid():
        return None
    output = QgsVectorLayer(f"{geometry_uri}?crs=EPSG:4326", name, "memory")
    fields = QgsFields()
    fields.append(QgsField("osm_id", QVariant.String))
    fields.append(QgsField("name", QVariant.String))
    fields.append(QgsField("class", QVariant.String))
    output.dataProvider().addAttributes(fields)
    output.updateFields()
    source_fields = {field.name() for field in source.fields()}
    features = []
    for source_feature in source.getFeatures():
        class_value = _tag(source_feature, source_fields, key)
        if not class_value:
            continue
        geometry = source_feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        feature = QgsFeature(output.fields())
        feature.setGeometry(geometry)
        feature.setAttributes([
            str(source_feature["osm_id"]) if "osm_id" in source_fields else "",
            _tag(source_feature, source_fields, "name"),
            class_value,
        ])
        features.append(feature)
    if not features:
        return None
    output.dataProvider().addFeatures(features)
    output.updateExtents()
    output.setCustomProperty("zero2urbanportrait/osm_download", True)
    output.setCustomProperty("zero2urbanportrait/osm_kind", key)
    return output


def load_osm_layers(path: Path) -> list[QgsVectorLayer]:
    """Convert an OSM XML file through QGIS/GDAL into focused memory layers."""
    lines = QgsVectorLayer(f"{path}|layername=lines", "OSM lines", "ogr")
    polygons = QgsVectorLayer(f"{path}|layername=multipolygons", "OSM polygons", "ogr")
    candidates = (
        _copy_tagged(lines, "OSM Roads", "MultiLineString", "highway"),
        _copy_tagged(polygons, "OSM Buildings", "MultiPolygon", "building"),
        _copy_tagged(polygons, "OSM Land Use", "MultiPolygon", "landuse"),
    )
    return [layer for layer in candidates if layer is not None]
