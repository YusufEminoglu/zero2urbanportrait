# 02Urban Portrait - City as a Face

02Urban Portrait turns roads, building footprints, points, and other vector networks into a live optical portrait inside QGIS. A chosen image is mapped to a geographic frame; each visible feature samples the image luminance and receives a reversible rule-based style. No source geometry or attribute is changed.

## Highlights

- Two data workflows: built-in OSM acquisition or any existing project vector layer.
- One-click OSM Standard basemap plus safe small-area roads/buildings/land-use download.
- Map-locked or screen-locked portrait masks with an optional frame overlay.
- Fast center, balanced multi-point, and high-quality geometry sampling.
- Live debounced updates while panning and zooming.
- Five art presets: Ink, Neon, Blueprint, Sepia, and Negative.
- Local smart contrast, gamma, inversion, and edge emphasis.
- Line underlays for shadow/glow depth and tonal polygon fills.
- Multiple vector layers in one composition.
- Original renderer restoration, QML style export, and PNG/PDF/SVG artwork export.
- Project-persistent frame and visual settings.
- No pip dependency, cloud upload, API key, or mutation of source data.

## Quick start

1. Open the **02Urban Portrait** toolbar button.
2. Choose one data workflow:
   - Select vector layers already in the project; or
   - Add the OSM basemap, zoom to a neighbourhood, and download the current view.
3. Choose a portrait image.
4. Use the canvas extent or draw a geographic frame.
5. Choose a preset and smart mask controls.
6. Click **Create portrait**, then export the current composition as PNG, PDF, or SVG.

The built-in public Overpass workflow rejects views wider than 6 km or larger than 25 square kilometres. This prevents accidental city/country-scale requests. Downloaded OSM layers are memory layers and can be saved permanently with QGIS **Export > Save Features As**.

For long road features, Balanced or High quality sampling preserves the portrait better than a single center sample. Set a sensible visible feature limit for very dense OSM extracts.

## How it works

The plugin keeps luminance results in an in-memory cache keyed by layer and feature ID. A registered QGIS expression function exposes those values to a `QgsRuleBasedRenderer`; five tonal rules drive line weight, underlay, fill, color, opacity, and highlight suppression. The renderer is temporary and the original renderer is cloned before styling.

## Privacy and smart tools

Automatic contrast and edge masks use local image statistics. Images never leave QGIS. The plugin is dependency-free and works offline.

## Compatibility

QGIS 3.28+ and QGIS 4.x. License: GPL-3.0-or-later.
