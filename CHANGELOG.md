# Changelog

## [0.3.2] - 2026-08-21

### Added
- **High-Visibility OSM Acquisition & Basemap UI**:
  - Upgraded "🗺️ Add OSM Basemap" and "⬇️ Download This View (OSM)" buttons with bold theme styling and explanatory tooltips.
  - Added dynamic real-time canvas extent safety pill container (`QFrame#osmPillCard`) with live area readiness feedback.
- **Polished Artwork Export Panel**: Clarified vector/raster format choices and styled the primary composition export button.

## [0.3.1] - 2026-08-21

### Added
- **Visual Workflow Stepper (`StepNodeWidget`)**: Added an interactive 3-stage visual progress stepper featuring numbered circular badge nodes (❶ Set up ➔ ❷ Shape ➔ ❸ Export) with live action guidance and completion status tracking.
- **Numbered Section Badges**: All group box sections are now sequential numbered steps (❶ Step 1.1 through ❻ Step 3.1) for an intuitive, structured workflow.
- **Step Navigation Buttons**: Added explicit 'Proceed to Next Step ➔' actions in Set up and Shape panels.

## [0.3.0] - 2026-08-21

### Added
- **Vector Halftone & Stippling Engraving Generator**: Converts sampled portrait luminance into variable-radius dot grids and algorithmic engraving layers.
- **5 New Master Presets**: Added *Cyberpunk 2077*, *Vintage Engraving*, *Thermal Heatmap*, *Emerald Eco-Map*, and *Nordic Slate* art-direction colorways.
- **Palette Import/Export**: Portable JSON serialization (`.json`) for custom user colorways and sharing.

## [0.2.7] - 2026-08-09

- Add a complete OpenStreetMap, tile-service and Overpass API third-party notice.
- Link the data-attribution guidance from the README.

## [0.2.6] - 2026-08-07

- Added online user manual link (https://yusufeminoglu.github.io/zero2urbanportrait/) and GitHub repository star call-to-action.

All notable changes follow [Keep a Changelog](https://keepachangelog.com/).

## [0.2.3] - 2026-08-03

### Changed
- Replace the hardcoded stylesheet with palette-derived colour tokens so the dock
  stays readable under QGIS light, dark and high-contrast themes. The hero card
  keeps its intentional dark branding; all other surfaces follow the active Qt
  palette.
- The dock now listens for PaletteChange and re-applies the theme automatically.
- Status-bar error colours use palette-aware tokens instead of assuming a light
  background.

### Added
- `dialogs/theme.py` with WCAG contrast-ratio checks, palette-aware colour tokens,
  and `apply_adaptive_theme()` entry point.

## [0.2.2] - 2026-07-20

### Changed

- Rebuilt the studio as a polished three-step Set up, Portrait, and Export workflow.
- Added a branded hero, active workflow strip, card-based controls, clearer action hierarchy, and cohesive visual theme.
- Moved OSM acquisition, portrait shaping, artwork export, QML portability, and renderer recovery into focused spaces.

## [0.2.1] - 2026-07-20

### Fixed

- Preserve every uploaded picture's original aspect ratio in canvas, drawn, live, and restored frames.
- Keep the studio visible on its first toolbar activation.

### Changed

- Clarified the upload and ratio-lock workflow, added image dimensions, and made the preview responsive.
- Disable render, update, restore, and QML actions until their required inputs are available.
- Disconnect project layer signals cleanly when the dock is disposed.

## [0.2.0] - 2026-07-20

### Added

- Built-in OpenStreetMap basemap and bounded Overpass download for roads, buildings, and land use.
- Live download-area validation capped at 6 km per side and 25 square kilometres.
- Current composition export to PNG, PDF, and SVG.
- Optional portrait-frame visibility control.

### Changed

- Reduced road widths and shadow underlay expansion for balanced cartographic output.
- Changed the plugin icon background to `#e8eded`.
- Portrait frame now hides automatically after a successful render.

## [0.1.0] - 2026-07-19

### Added

- Live, non-destructive luminance styling for line, polygon, and point layers.
- Map-locked and screen-locked image frames with pan/zoom refresh.
- Fast, balanced, and high-quality geometry sampling modes.
- Ink, Neon, Blueprint, Sepia, and Negative artistic presets.
- Smart auto-contrast, gamma, inversion, and edge-emphasis masks.
- Original-renderer restoration and per-layer safety limits.
- Project-persistent image frame and visual settings.
