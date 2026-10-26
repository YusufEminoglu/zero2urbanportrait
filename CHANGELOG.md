# Changelog

## [Unreleased]

### Fixed
- The halftone layer drew every dot at the same size: its data-defined size was set with `QgsProperty.fromField("radius * 2")`, which names a field that does not exist, so QGIS fell back to the static size. Dot size now evaluates the `radius` field.
- Halftone inversion and gamma were applied twice (once by the image profile, then again by the grid), so *Invert light and shadow* had no effect on the halftone and gamma pulled in the wrong direction. The tone is now computed once.
- A saved project reopened with blank or uniformly pale portrait layers: the renderer depended on a Python expression function and an in-memory cache that a new QGIS session does not have. The same flaw made an exported QML useless outside the session that wrote it.
- *Restore original styles* could not restore anything after the project had been reopened, because the original renderer lived only in memory.
- Preset background colours were defined but never applied, so the dark presets (Neon Night, Blueprint, Negative City, Cyberpunk 2077, Thermal Heatmap, Emerald Eco-Map) were drawn on a white map and exported on white paper.
- Artwork export ignored the canvas colour and could leave a white band when the canvas was wider than 2:1 or taller than 1:1.75, because the page width was clamped while the map item kept the canvas extent. The page now has the exact canvas ratio, and the map item follows the canvas CRS and rotation.
- Opening another project kept the previous project's picture, frame, and styled-layer list in the dock.
- A view that cannot be transformed into a layer's CRS raised an error on every pan during live updates.

### Changed
- The portrait renderer is now a `QgsCategorizedSymbolRenderer` on `$id` whose tone categories list the sampled feature ids. It no longer calls into Python per feature, so it renders at native speed in QGIS' parallel render threads, survives saving and reopening the project (also without the plugin), and exports as a complete QML for the same dataset.
- Halftone dot area is proportional to darkness (radius follows the square root of darkness), and the darkest tone covers its whole cell, so midtones print at their true ink share.
- Halftone cells are square on any frame shape: the dot count applies to the longer side.
- Halftone dots use the preset's deepest colour instead of a fixed near-black.
- New plugin icon: the portrait relief from the 0.4.2 medallion, freed from its plate and rim, on a transparent background that fills the icon edge to edge.

### Added
- *Paint the map background with the preset paper colour* (on by default). The previous colour is stored in the project and returns with *Restore original styles*.
- A five-colour swatch of the selected preset on its paper.
- Hex halftone pattern (offset rows, like a print screen) next to the square grid.
- Portrait layers saved in a project are reconnected when the dock opens: with the picture still on disk, live updates resume.
- QGIS acceptance checks that render real maps on QGIS 3.44 LTR and 4.x: tone order across a gradient, project save and reopen, paper colour and export background, halftone size, inversion and pattern, and the dock's project lifecycle.

## [0.4.2] - 2026-09-17

- Upgraded official plugin icon to high-end tactile 3D brand identity (isometric 45°, slim teal pedestal, full bleed transparent canvas).
- Synchronized documentation, repository and issue tracker endpoints to GeoPhilo and GitLab.

## [0.4.1] - 2026-09-06

- Migrate repository and documentation URLs to GitLab and Cloudflare Pages.

## [0.4.0] - 2026-08-21

### Added
- Workflow-aware navigation controls with clear prerequisite tooltips and completed-export feedback.
- Halftone-only composition export support, so generated engraving layers can be exported without first styling a source layer.
- Strict palette JSON validation for five renderer colors, background color, finite line widths, normalized names, a 1 MB file limit, and a 100-preset limit.
- QGIS GUI smoke coverage on both QGIS 3.44 LTR and QGIS 4.x.

### Changed
- Palette exports now use atomic replacement to prevent interrupted writes from leaving truncated JSON files.
- Live canvas refresh is scheduled only while a portrait is active, reducing idle work during ordinary map navigation.
- Invalid stipple bounds, grid dimensions, radius, gamma, and non-finite values now fail early with actionable messages.

### Fixed
- **Restore original styles** now restores all portrait-styled layers, matching the action label and recovery guidance.
- Artwork export temporarily hides the frame overlay and restores the user's previous visibility preference afterward, including failed exports.
- OSM download results clear stale layer selections before selecting the newly created roads, buildings, and land-use layers.
- Manual portrait updates now report render failures instead of leaking exceptions into the QGIS interface.

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
