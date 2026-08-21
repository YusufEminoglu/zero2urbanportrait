# -*- coding: utf-8 -*-
"""Algorithmic Halftone and Vector Stippling Engraving Generator for 02Urban Portrait."""
from __future__ import annotations

import math
from contextlib import suppress


def calculate_stipple_points(
    min_x: float, min_y: float, max_x: float, max_y: float,
    grid_cols: int, grid_rows: int,
    sample_fn, max_radius: float = 5.0,
    gamma: float = 1.0, invert: bool = False
) -> list[dict]:
    """Pure-math grid calculation: returns point records with coordinate, radius, and tone."""
    values = (min_x, min_y, max_x, max_y, max_radius, gamma)
    if any(not math.isfinite(float(value)) for value in values):
        raise ValueError("Stipple bounds and rendering values must be finite.")
    if max_x <= min_x or max_y <= min_y:
        raise ValueError("Stipple bounds must have a positive width and height.")
    if int(grid_cols) < 2 or int(grid_rows) < 2:
        raise ValueError("Stipple grids require at least two rows and columns.")
    if max_radius <= 0.0 or gamma <= 0.0:
        raise ValueError("Stipple radius and gamma must be positive.")
    dx = (max_x - min_x) / max(1, grid_cols - 1)
    dy = (max_y - min_y) / max(1, grid_rows - 1)
    points = []

    for row in range(grid_rows):
        v = row / max(1, grid_rows - 1)
        y = max_y - row * dy  # top to bottom
        for col in range(grid_cols):
            u = col / max(1, grid_cols - 1)
            x = min_x + col * dx

            luma = sample_fn(u, v)
            if invert:
                luma = 255 - luma
            luma = max(0, min(255, int(luma)))

            # Darker pixels produce larger dots
            intensity = 1.0 - (luma / 255.0)
            if gamma != 1.0 and intensity > 0.0:
                intensity = math.pow(intensity, gamma)

            radius = max_radius * intensity
            if radius < 0.05:
                continue

            tone_bin = min(4, int(luma / 52))

            points.append({
                "id": len(points) + 1,
                "x": x,
                "y": y,
                "u": u,
                "v": v,
                "luminance": luma,
                "radius": round(radius, 3),
                "tone_bin": tone_bin,
            })

    return points


def generate_stipple_layer(bounds: tuple[float, float, float, float],
                           crs_auth_id: str,
                           profile,
                           render_options,
                           grid_cols: int = 60,
                           grid_rows: int = 60,
                           layer_name: str = "Urban Portrait Halftone"):
    """Build a styled QgsVectorLayer of variable-radius vector stipple points."""
    try:
        from qgis.core import (
            QgsFeature, QgsGeometry, QgsPointXY,
            QgsVectorLayer, QgsMarkerSymbol, QgsSingleSymbolRenderer,
            QgsProperty,
        )
    except ImportError:  # pragma: no cover
        return None

    min_x, min_y, max_x, max_y = bounds

    def sample_fn(u, v):
        return profile.sample(u, v, render_options)

    # Estimate max dot radius in map units so dots touch at maximum density
    cell_w = (max_x - min_x) / max(1, grid_cols)
    cell_h = (max_y - min_y) / max(1, grid_rows)
    max_radius_map = min(cell_w, cell_h) * 0.55

    points = calculate_stipple_points(
        min_x, min_y, max_x, max_y,
        grid_cols=grid_cols, grid_rows=grid_rows,
        sample_fn=sample_fn,
        max_radius=max_radius_map,
        gamma=render_options.gamma,
        invert=render_options.invert,
    )

    uri = f"Point?crs={crs_auth_id}&field=id:integer&field=luma:integer&field=radius:double&field=tone:integer"
    layer = QgsVectorLayer(uri, layer_name, "memory")
    pr = layer.dataProvider()

    features = []
    for pt in points:
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(pt["x"], pt["y"])))
        feat.setAttributes([pt["id"], pt["luminance"], pt["radius"], pt["tone_bin"]])
        features.append(feat)

    pr.addFeatures(features)
    layer.updateExtents()

    # Data-defined size renderer
    with suppress(Exception):
        symbol = QgsMarkerSymbol.createSimple({
            "name": "circle",
            "color": "#111827",
            "outline_color": "#000000",
            "outline_width": "0",
            "size_unit": "MapUnit",
        })
        symbol.setDataDefinedSize(QgsProperty.fromField("radius * 2"))
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()

    return layer
