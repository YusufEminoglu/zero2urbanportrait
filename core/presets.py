"""Art-direction presets kept separate from QGIS renderer construction."""
from __future__ import annotations

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
}

TONE_BREAKS = (0, 52, 104, 156, 208, 256)
