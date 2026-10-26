# -*- coding: utf-8 -*-
"""Algorithmic halftone and vector stippling generator for 02Urban Portrait."""
from __future__ import annotations

import math

# A dot of radius cell / sqrt(pi) covers exactly one cell, so the darkest tone
# prints as solid ink and every other tone keeps its share of ink.
FULL_COVER_RADIUS = 1.0 / math.sqrt(math.pi)
PATTERNS = ("Square", "Hex")


def grid_shape(width: float, height: float, grid_size: int, pattern: str = "Square") -> tuple[int, int, float, float]:
    """Return ``(columns, rows, dx, dy)`` for square (or hexagonal) cells.

    ``grid_size`` counts dots along the longer side of the frame; the shorter
    side gets as many as keep the spacing equal, so dots never stretch.
    """
    if not (math.isfinite(width) and math.isfinite(height)) or width <= 0.0 or height <= 0.0:
        raise ValueError("Stipple bounds must have a positive width and height.")
    size = int(grid_size)
    if size < 2:
        raise ValueError("Stipple grids require at least two rows and columns.")
    spacing = max(width, height) / (size - 1)
    row_spacing = spacing * (math.sqrt(3.0) / 2.0 if pattern == "Hex" else 1.0)
    columns = max(2, int(round(width / spacing)) + 1)
    rows = max(2, int(round(height / row_spacing)) + 1)
    return columns, rows, width / (columns - 1), height / (rows - 1)


def dot_radius(luminance: int, max_radius: float) -> float:
    """Radius whose dot area is proportional to the darkness of the tone."""
    darkness = 1.0 - max(0, min(255, int(luminance))) / 255.0
    return max_radius * math.sqrt(darkness)


def calculate_stipple_points(
    min_x: float, min_y: float, max_x: float, max_y: float,
    grid_cols: int, grid_rows: int,
    sample_fn, max_radius: float = 5.0,
    pattern: str = "Square",
) -> list[dict]:
    """Pure-math grid calculation: returns point records with coordinate, radius, and tone.

    ``sample_fn(u, v)`` must return the final 0-255 tone at that image
    position (contrast, gamma and inversion already applied); it is used as is.
    """
    values = (min_x, min_y, max_x, max_y, max_radius)
    if any(not math.isfinite(float(value)) for value in values):
        raise ValueError("Stipple bounds and rendering values must be finite.")
    if max_x <= min_x or max_y <= min_y:
        raise ValueError("Stipple bounds must have a positive width and height.")
    if int(grid_cols) < 2 or int(grid_rows) < 2:
        raise ValueError("Stipple grids require at least two rows and columns.")
    if max_radius <= 0.0:
        raise ValueError("Stipple radius must be positive.")
    dx = (max_x - min_x) / (grid_cols - 1)
    dy = (max_y - min_y) / (grid_rows - 1)
    hexagonal = pattern == "Hex"
    points = []

    for row in range(grid_rows):
        y = max_y - row * dy  # top to bottom
        shift = 0.5 * dx if hexagonal and row % 2 else 0.0
        for col in range(grid_cols):
            x = min_x + col * dx + shift
            if x > max_x + 1e-9 * dx:
                continue
            u = (x - min_x) / (max_x - min_x)
            v = (max_y - y) / (max_y - min_y)
            luma = max(0, min(255, int(sample_fn(u, v))))
            radius = dot_radius(luma, max_radius)
            if radius < max_radius * 0.04:
                continue
            points.append({
                "id": len(points) + 1,
                "x": x,
                "y": y,
                "u": u,
                "v": v,
                "luminance": luma,
                "radius": round(radius, 6),
                "tone_bin": min(4, luma // 52),
            })

    return points


def generate_stipple_layer(bounds: tuple[float, float, float, float],
                           crs,
                           profile,
                           render_options,
                           grid_size: int = 60,
                           pattern: str = "Square",
                           ink_color: str = "#111827",
                           layer_name: str = "Urban Portrait Halftone"):
    """Build a memory layer of variable-radius dots styled in map units."""
    from qgis.core import (
        QgsFeature,
        QgsGeometry,
        QgsMarkerSymbol,
        QgsPointXY,
        QgsProperty,
        QgsSingleSymbolRenderer,
        QgsVectorLayer,
    )

    min_x, min_y, max_x, max_y = bounds
    columns, rows, dx, dy = grid_shape(max_x - min_x, max_y - min_y, grid_size, pattern)
    # Every dot owns one dx * dy cell in both patterns (hex rows sit closer).
    max_radius = math.sqrt(dx * dy) * FULL_COVER_RADIUS

    points = calculate_stipple_points(
        min_x, min_y, max_x, max_y,
        grid_cols=columns, grid_rows=rows,
        sample_fn=lambda u, v: profile.sample(u, v, render_options),
        max_radius=max_radius,
        pattern=pattern,
    )

    layer = QgsVectorLayer(
        "Point?field=id:integer&field=luma:integer&field=radius:double&field=tone:integer",
        layer_name, "memory",
    )
    layer.setCrs(crs)
    features = []
    for pt in points:
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(pt["x"], pt["y"])))
        feat.setAttributes([pt["id"], pt["luminance"], pt["radius"], pt["tone_bin"]])
        features.append(feat)
    layer.dataProvider().addFeatures(features)
    layer.updateExtents()

    symbol = QgsMarkerSymbol.createSimple({
        "name": "circle",
        "color": ink_color,
        "outline_style": "no",
        "size_unit": "MapUnit",
        "size": str(2.0 * max_radius),
    })
    symbol.setDataDefinedSize(QgsProperty.fromExpression('2 * "radius"'))
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    return layer
