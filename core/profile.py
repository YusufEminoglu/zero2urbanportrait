"""Dependency-free tone transforms and map-to-image coordinate helpers."""
from __future__ import annotations

from dataclasses import dataclass
from math import pow


@dataclass(frozen=True)
class NormalizedPoint:
    """Image coordinates normalized to the inclusive 0..1 range."""

    u: float
    v: float


def map_to_normalized(x: float, y: float, bounds: tuple[float, float, float, float]) -> NormalizedPoint | None:
    """Map a world point to image coordinates, flipping the vertical axis."""
    xmin, ymin, xmax, ymax = bounds
    width = xmax - xmin
    height = ymax - ymin
    if width <= 0.0 or height <= 0.0 or x < xmin or x > xmax or y < ymin or y > ymax:
        return None
    return NormalizedPoint((x - xmin) / width, (ymax - y) / height)


def adjust_luminance(value: float, low: float = 0.0, high: float = 255.0,
                     gamma: float = 1.0, invert: bool = False) -> int:
    """Stretch, gamma-correct, and optionally invert an 8-bit luminance."""
    if high <= low:
        high = low + 1.0
    normalized = min(1.0, max(0.0, (float(value) - low) / (high - low)))
    corrected = pow(normalized, 1.0 / max(0.05, float(gamma)))
    if invert:
        corrected = 1.0 - corrected
    return int(round(corrected * 255.0))


def quantile_limits(histogram: list[int], clip_fraction: float = 0.01) -> tuple[int, int]:
    """Return robust low/high histogram limits for automatic contrast."""
    total = sum(max(0, int(count)) for count in histogram[:256])
    if total <= 0:
        return 0, 255
    target = total * min(0.25, max(0.0, clip_fraction))
    running = 0
    low = 0
    for low, count in enumerate(histogram[:256]):
        running += max(0, int(count))
        if running >= target:
            break
    running = 0
    high = 255
    for high in range(min(255, len(histogram) - 1), -1, -1):
        running += max(0, int(histogram[high]))
        if running >= target:
            break
    return (low, high) if high > low else (0, 255)


def blend_edge(luminance: int, edge_strength: int, amount: float) -> int:
    """Darken image edges while preserving the underlying tonal portrait."""
    mix = min(1.0, max(0.0, float(amount)))
    edge_tone = 255 - min(255, max(0, int(edge_strength)))
    return int(round((1.0 - mix) * luminance + mix * min(luminance, edge_tone)))
