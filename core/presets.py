"""Art-direction presets kept separate from QGIS renderer construction."""
from __future__ import annotations

PRESETS = {
    "Ink Portrait": {
        "colors": ("#090b10", "#20242d", "#4d535f", "#a8adb5", "#e7e9ec"),
        "background": "#f5f1e8", "widths": (2.8, 2.1, 1.4, 0.7, 0.18), "hide_highlights": True,
    },
    "Neon Night": {
        "colors": ("#ff477e", "#7b2cff", "#00c2ff", "#5eead4", "#c8fff4"),
        "background": "#050816", "widths": (3.2, 2.5, 1.7, 0.9, 0.25), "hide_highlights": False,
    },
    "Blueprint": {
        "colors": ("#effcff", "#a7e8f2", "#58c9da", "#2389a1", "#155064"),
        "background": "#082f49", "widths": (2.6, 2.0, 1.35, 0.75, 0.22), "hide_highlights": False,
    },
    "Sepia Blocks": {
        "colors": ("#2c1810", "#5b3424", "#8f5f3e", "#c69b6d", "#ead7b7"),
        "background": "#f1e3c6", "widths": (2.9, 2.2, 1.5, 0.8, 0.2), "hide_highlights": True,
    },
    "Negative City": {
        "colors": ("#f7f7ff", "#c7d2fe", "#818cf8", "#4338ca", "#111133"),
        "background": "#07071a", "widths": (3.0, 2.25, 1.5, 0.75, 0.2), "hide_highlights": False,
    },
}

TONE_BREAKS = (0, 52, 104, 156, 208, 256)
