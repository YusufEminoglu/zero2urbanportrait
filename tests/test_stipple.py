# -*- coding: utf-8 -*-
from __future__ import annotations

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
