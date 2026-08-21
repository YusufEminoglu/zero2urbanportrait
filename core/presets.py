# -*- coding: utf-8 -*-
"""Art-direction presets and palette management for 02Urban Portrait."""
from __future__ import annotations

import json
from pathlib import Path

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


def export_presets_json(path: str | Path, presets_dict: dict | None = None) -> None:
    """Save preset dictionary to a JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    to_save = presets_dict or PRESETS
    serializable = {}
    for name, pr in to_save.items():
        serializable[name] = {
            "colors": list(pr.get("colors", [])),
            "background": pr.get("background", "#ffffff"),
            "widths": list(pr.get("widths", [])),
            "hide_highlights": bool(pr.get("hide_highlights", False)),
        }
    with open(p, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)


def import_presets_json(path: str | Path) -> dict:
    """Load custom presets from a JSON file."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Preset file not found: {p}")
    with open(p, "r", encoding="utf-8") as f:
        raw = json.load(f)
    loaded = {}
    for name, item in raw.items():
        if isinstance(item, dict) and "colors" in item and "background" in item:
            loaded[name] = {
                "colors": tuple(item["colors"]),
                "background": item["background"],
                "widths": tuple(item.get("widths", (1.35, 1.0, 0.68, 0.38, 0.12))),
                "hide_highlights": bool(item.get("hide_highlights", False)),
            }
    return loaded
