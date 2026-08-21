# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

import pytest

from zero2urbanportrait.core.presets import (
    PRESETS, export_presets_json, import_presets_json, validate_preset,
)


def test_road_widths_are_cartographic_not_cad_heavy():
    assert len(PRESETS) >= 10
    for name, preset in PRESETS.items():
        widths = preset["widths"]
        assert widths == tuple(sorted(widths, reverse=True)), f"{name} widths not sorted descending"
        assert max(widths) <= 1.55, f"{name} max width too high"
        assert min(widths) >= 0.1, f"{name} min width too low"
        assert len(preset["colors"]) == 5, f"{name} must have 5 colors"


def test_preset_export_import_roundtrip(tmp_path):
    json_path = Path(tmp_path) / "test_presets.json"
    export_presets_json(json_path, PRESETS)
    assert json_path.exists()
    assert not (tmp_path / f".{json_path.name}.tmp").exists()
    loaded = import_presets_json(json_path)
    assert len(loaded) == len(PRESETS)
    assert "Cyberpunk 2077" in loaded
    assert "Vintage Engraving" in loaded
    assert loaded["Cyberpunk 2077"]["background"] == PRESETS["Cyberpunk 2077"]["background"]


@pytest.mark.parametrize("preset, message", [
    ({"colors": ["#000000"] * 4, "background": "#ffffff", "widths": [1] * 5}, "five colors"),
    ({"colors": ["not-a-color"] * 5, "background": "#ffffff", "widths": [1] * 5}, "hexadecimal"),
    ({"colors": ["#000000"] * 5, "background": "#ffffff", "widths": [1, 1, 1, 1, float("inf")]}, "finite"),
])
def test_validate_preset_rejects_renderer_unsafe_values(preset, message):
    with pytest.raises(ValueError, match=message):
        validate_preset("Unsafe", preset)


def test_import_rejects_invalid_json_and_non_object_root(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        import_presets_json(broken)

    array_root = tmp_path / "array.json"
    array_root.write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty JSON object"):
        import_presets_json(array_root)


def test_import_rejects_names_that_collide_after_whitespace_normalization(tmp_path):
    preset = {
        "colors": ["#111111", "#333333", "#555555", "#777777", "#999999"],
        "background": "#ffffff",
        "widths": [1.4, 1.0, 0.7, 0.4, 0.1],
    }
    path = tmp_path / "duplicates.json"
    path.write_text(json.dumps({"Custom": preset, " Custom ": preset}), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate normalized name"):
        import_presets_json(path)
