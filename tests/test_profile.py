from zero2urbanportrait.core.profile import (
    adjust_luminance,
    blend_edge,
    map_to_normalized,
    quantile_limits,
)


def test_map_to_normalized_flips_y():
    point = map_to_normalized(25, 75, (0, 0, 100, 100))
    assert point is not None
    assert point.u == 0.25
    assert point.v == 0.25
    assert map_to_normalized(101, 50, (0, 0, 100, 100)) is None


def test_luminance_adjustments():
    assert adjust_luminance(0) == 0
    assert adjust_luminance(255) == 255
    assert adjust_luminance(0, invert=True) == 255
    assert adjust_luminance(100, low=100, high=200) == 0


def test_histogram_limits_and_edges():
    histogram = [0] * 256
    histogram[20] = 10
    histogram[220] = 10
    assert quantile_limits(histogram) == (20, 220)
    assert blend_edge(180, 255, 1.0) == 0
