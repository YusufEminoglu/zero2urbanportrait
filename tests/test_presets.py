# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
from pathlib import Path

from zero2urbanportrait.core.presets import PRESETS, export_presets_json, import_presets_json


def test_road_widths_are_cartographic_not_cad_heavy():
    assert len(PRESETS) >= 10
    for name, preset in PRESETS.items():
        widths = preset["widths"]
        assert widths == tuple(sorted(widths, reverse=True)), f"{name} widths not sorted descending"
        assert max(widths) <= 1.55, f"{name} max width too high"
        assert min(widths) >= 0.1, f"{name} min width too low"
        assert len(preset["colors"]) == 5, f"{name} must have 5 colors"


def test_preset_export_import_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = Path(tmpdir) / "test_presets.json"
        export_presets_json(json_path, PRESETS)
        assert json_path.exists()
        loaded = import_presets_json(json_path)
        assert len(loaded) == len(PRESETS)
        assert "Cyberpunk 2077" in loaded
        assert "Vintage Engraving" in loaded
        assert loaded["Cyberpunk 2077"]["background"] == PRESETS["Cyberpunk 2077"]["background"]
