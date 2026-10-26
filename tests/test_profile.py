import pytest

from zero2urbanportrait.core.profile import (
    adjust_luminance,
    blend_edge,
    fit_bounds_to_aspect,
    map_to_normalized,
    quantile_limits,
)


def test_map_to_normalized_flips_y():
    point = map_to_normalized(25, 75, (0, 0, 100, 100))
    assert point is not None
    assert point.u == 0.25
    assert point.v == 0.25
    assert map_to_normalized(101, 50, (0, 0, 100, 100)) is None


def test_fit_bounds_preserves_landscape_image_ratio():
    fitted = fit_bounds_to_aspect((0, 0, 100, 100), 16 / 9)
    assert fitted == (0, 21.875, 100, 78.125)
    assert (fitted[2] - fitted[0]) / (fitted[3] - fitted[1]) == 16 / 9


def test_fit_bounds_preserves_portrait_image_ratio():
    fitted = fit_bounds_to_aspect((0, 0, 200, 100), 2 / 3)
    assert fitted == pytest.approx((66.6666667, 0, 133.3333333, 100))


def test_fit_bounds_rejects_invalid_input():
    with pytest.raises(ValueError):
        fit_bounds_to_aspect((0, 0, 0, 100), 1.0)
    with pytest.raises(ValueError):
        fit_bounds_to_aspect((0, 0, 100, 100), 0.0)


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


def test_tone_index_matches_preset_breaks():
    from zero2urbanportrait.core.presets import TONE_BREAKS
    from zero2urbanportrait.core.profile import tone_index
    for index in range(5):
        assert tone_index(TONE_BREAKS[index]) == index
        assert tone_index(TONE_BREAKS[index + 1] - 1) == index
    assert tone_index(-5) == 0 and tone_index(999) == 4


def test_group_by_tone_leaves_paper_to_the_catch_all():
    from zero2urbanportrait.core.profile import group_by_tone
    groups = group_by_tone({7: 10, 3: 0, 5: 60, 9: 255, 11: 230, 2: 170})
    assert groups == [[3, 7], [5], [], [2]]
