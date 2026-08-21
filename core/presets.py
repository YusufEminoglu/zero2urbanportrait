# -*- coding: utf-8 -*-
"""Art-direction presets and palette management for 02Urban Portrait."""
from __future__ import annotations

from contextlib import suppress
import json
import math
from pathlib import Path
import re


MAX_PRESET_FILE_BYTES = 1024 * 1024
MAX_IMPORTED_PRESETS = 100
_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")

PRESETS = {
    "Ink Portrait": {
        "colors": ("#090b10", "#20242d", "#4d535f", "#a8adb5", "#e7e9ec"),
        "background": "#f5f1e8", "widths": (1.35, 1.0, 0.68, 0.38, 0.12), "hide_highlights": True,
    },
    "Neon Night": {
        "colors": ("#ff477e", "#7b2cff", "#00c2ff", "#5eead4", "#c8fff4"),
        "background": "#050816", "widths": (1.55, 1.15, 0.78, 0.42, 0.14), "hide_highlights": False,
    },
    "Blueprint": {
        "colors": ("#effcff", "#a7e8f2", "#58c9da", "#2389a1", "#155064"),
        "background": "#082f49", "widths": (1.3, 0.95, 0.65, 0.36, 0.12), "hide_highlights": False,
    },
    "Sepia Blocks": {
        "colors": ("#2c1810", "#5b3424", "#8f5f3e", "#c69b6d", "#ead7b7"),
        "background": "#f1e3c6", "widths": (1.4, 1.05, 0.7, 0.4, 0.12), "hide_highlights": True,
    },
    "Negative City": {
        "colors": ("#f7f7ff", "#c7d2fe", "#818cf8", "#4338ca", "#111133"),
        "background": "#07071a", "widths": (1.45, 1.08, 0.72, 0.4, 0.12), "hide_highlights": False,
    },
    "Cyberpunk 2077": {
        "colors": ("#060814", "#7000ff", "#ff0055", "#00f0ff", "#ffe600"),
        "background": "#050811", "widths": (1.50, 1.10, 0.75, 0.40, 0.14), "hide_highlights": False,
    },
    "Vintage Engraving": {
        "colors": ("#2c1d11", "#4a3525", "#70533d", "#a48366", "#d8c5b0"),
        "background": "#f6eee3", "widths": (1.35, 1.00, 0.68, 0.38, 0.12), "hide_highlights": True,
    },
    "Thermal Heatmap": {
        "colors": ("#0a0826", "#4d006e", "#a8184c", "#f36410", "#f9f871"),
        "background": "#050414", "widths": (1.50, 1.12, 0.74, 0.38, 0.13), "hide_highlights": False,
    },
    "Emerald Eco-Map": {
        "colors": ("#061c14", "#0f3d2e", "#1e6b52", "#3fa882", "#7be3bc"),
        "background": "#030f0b", "widths": (1.40, 1.05, 0.70, 0.38, 0.12), "hide_highlights": False,
    },
    "Nordic Slate": {
        "colors": ("#12171c", "#242d38", "#414f5e", "#7a8a9e", "#cbd5e1"),
        "background": "#f1f5f9", "widths": (1.30, 0.95, 0.65, 0.35, 0.12), "hide_highlights": True,
    },
}

TONE_BREAKS = (0, 52, 104, 156, 208, 256)


def validate_preset(name: str, item: dict) -> dict:
    """Return a renderer-safe normalized preset or raise ``ValueError``."""
    clean_name = str(name).strip()
    if not clean_name or len(clean_name) > 80:
        raise ValueError("Preset names must contain 1 to 80 characters.")
    if not isinstance(item, dict):
        raise ValueError(f"Preset '{clean_name}' must be a JSON object.")
    colors = item.get("colors")
    if not isinstance(colors, (list, tuple)) or len(colors) != 5:
        raise ValueError(f"Preset '{clean_name}' must define exactly five colors.")
    normalized_colors = tuple(str(color).strip() for color in colors)
    if any(not _COLOR_PATTERN.fullmatch(color) for color in normalized_colors):
        raise ValueError(f"Preset '{clean_name}' contains an invalid hexadecimal color.")
    background = str(item.get("background", "")).strip()
    if not _COLOR_PATTERN.fullmatch(background):
        raise ValueError(f"Preset '{clean_name}' has an invalid background color.")
    widths = item.get("widths", (1.35, 1.0, 0.68, 0.38, 0.12))
    if not isinstance(widths, (list, tuple)) or len(widths) != 5:
        raise ValueError(f"Preset '{clean_name}' must define exactly five line widths.")
    try:
        normalized_widths = tuple(float(width) for width in widths)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Preset '{clean_name}' contains a non-numeric line width.") from exc
    if any(not math.isfinite(width) or width <= 0.0 or width > 20.0
           for width in normalized_widths):
        raise ValueError(f"Preset '{clean_name}' line widths must be finite and between 0 and 20.")
    return {
        "colors": normalized_colors,
        "background": background,
        "widths": normalized_widths,
        "hide_highlights": bool(item.get("hide_highlights", False)),
    }


def export_presets_json(path: str | Path, presets_dict: dict | None = None) -> None:
    """Save preset dictionary to a JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    to_save = PRESETS if presets_dict is None else presets_dict
    if not isinstance(to_save, dict) or not to_save:
        raise ValueError("At least one valid preset is required for export.")
    serializable = {}
    for name, pr in to_save.items():
        normalized = validate_preset(name, pr)
        serializable[str(name).strip()] = {
            "colors": list(normalized["colors"]),
            "background": normalized["background"],
            "widths": list(normalized["widths"]),
            "hide_highlights": normalized["hide_highlights"],
        }
    temporary = p.with_name(f".{p.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(serializable, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(p)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


def import_presets_json(path: str | Path) -> dict:
    """Load custom presets from a JSON file."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Preset file not found: {p}")
    if p.stat().st_size > MAX_PRESET_FILE_BYTES:
        raise ValueError("Preset file exceeds the 1 MB safety limit.")
    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Preset file contains invalid JSON at line {exc.lineno}.") from exc
    if not isinstance(raw, dict) or not raw:
        raise ValueError("Preset file must contain a non-empty JSON object.")
    if len(raw) > MAX_IMPORTED_PRESETS:
        raise ValueError(f"Preset file exceeds the {MAX_IMPORTED_PRESETS}-preset safety limit.")
    loaded = {}
    for name, item in raw.items():
        clean_name = str(name).strip()
        if clean_name in loaded:
            raise ValueError(f"Preset file contains a duplicate normalized name: {clean_name!r}.")
        loaded[clean_name] = validate_preset(name, item)
    return loaded
