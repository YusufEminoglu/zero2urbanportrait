from zero2urbanportrait.core.presets import PRESETS


def test_road_widths_are_cartographic_not_cad_heavy():
    for preset in PRESETS.values():
        widths = preset["widths"]
        assert widths == tuple(sorted(widths, reverse=True))
        assert max(widths) <= 1.55
        assert min(widths) >= 0.1
