# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from zero2urbanportrait.core.stipple import calculate_stipple_points


def test_calculate_stipple_points():
    # Synthetic luminance gradient function: dark at top-left (u=0, v=0 -> 0), bright at bottom-right (u=1, v=1 -> 255)
    def sample_fn(u: float, v: float) -> int:
        return int((u + v) * 0.5 * 255)

    points = calculate_stipple_points(
        min_x=0.0, min_y=0.0, max_x=100.0, max_y=100.0,
        grid_cols=10, grid_rows=10,
        sample_fn=sample_fn, max_radius=5.0,
    )
    assert len(points) > 50
    first_pt = points[0]
    assert "x" in first_pt
    assert "y" in first_pt
    assert "radius" in first_pt
    assert "luminance" in first_pt
    assert "tone_bin" in first_pt

    # Top-left should have higher radius (darker) than bottom-right
    assert points[0]["radius"] >= points[-1]["radius"]


@pytest.mark.parametrize("kwargs, message", [
    ({"max_x": 0.0}, "positive width"),
    ({"grid_cols": 1}, "at least two"),
    ({"max_radius": 0.0}, "must be positive"),
])
def test_calculate_stipple_points_rejects_invalid_geometry(kwargs, message):
    arguments = {
        "min_x": 0.0, "min_y": 0.0, "max_x": 10.0, "max_y": 10.0,
        "grid_cols": 3, "grid_rows": 3, "sample_fn": lambda _u, _v: 128,
        "max_radius": 1.0,
    }
    arguments.update(kwargs)
    with pytest.raises(ValueError, match=message):
        calculate_stipple_points(**arguments)


def test_dot_area_is_proportional_to_darkness():
    from zero2urbanportrait.core.stipple import dot_radius
    full = dot_radius(0, 1.0) ** 2
    half = dot_radius(round(255 * 0.5), 1.0) ** 2
    assert full == pytest.approx(1.0)
    assert half / full == pytest.approx(0.5, abs=0.01)
    assert dot_radius(255, 1.0) == 0.0


def test_sample_fn_is_used_as_is():
    # Inversion and gamma belong to the image profile; the grid must not redo them.
    points = calculate_stipple_points(0.0, 0.0, 10.0, 10.0, 3, 3, lambda _u, _v: 0, max_radius=1.0)
    assert all(point["luminance"] == 0 for point in points)
    assert all(point["radius"] == pytest.approx(1.0) for point in points)


def test_grid_shape_keeps_cells_square():
    from zero2urbanportrait.core.stipple import grid_shape
    columns, rows, dx, dy = grid_shape(200.0, 100.0, 21)
    assert (columns, rows) == (21, 11)
    assert dx == pytest.approx(dy)
    columns, rows, dx, dy = grid_shape(100.0, 300.0, 31)
    assert rows == 31 and dx == pytest.approx(dy)


def test_hex_pattern_offsets_alternate_rows():
    from zero2urbanportrait.core.stipple import grid_shape
    columns, rows, dx, dy = grid_shape(100.0, 100.0, 11, "Hex")
    assert dy == pytest.approx(dx * 3 ** 0.5 / 2, rel=0.08)
    points = calculate_stipple_points(0.0, 0.0, 100.0, 100.0, columns, rows,
                                      lambda _u, _v: 0, max_radius=1.0, pattern="Hex")
    first_x = {}
    for point in points:
        first_x.setdefault(round(point["y"], 6), point["x"])
    offsets = sorted(set(round(x, 6) for x in first_x.values()))
    assert offsets == [0.0, pytest.approx(dx / 2)]
    assert all(0.0 <= point["x"] <= 100.0 for point in points)
