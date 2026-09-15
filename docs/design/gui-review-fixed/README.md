# GUI correction and visual review

The custom editors and utilities now run inside the application workspace, with shared controls and responsive layouts. The original proposal and the September 15 audit remain unchanged as historical references.

[Open the current screenshot gallery](index.html) · [Measurements](measurements.json) · [Original audit](../visual-audit-2026-09-15/README.md)

## Corrections

| Area | Implemented behavior |
| --- | --- |
| Shared controls | 8 px rounded buttons and fields, rounded choice controls and tabs, semantic light/dark colors, keyboard focus, consistent spacing, and readable disabled labels that retain native disabled behavior. Comfortable buttons are at least 48 px; job actions are at least 56 px. Compact mouse density retains touch sizes at narrow widths. |
| Main workspace | Project name and save status in the header, outlined desktop toolbar icons, Properties/Layers selection, working Hide/Show panel, bounded phone inspector, and visible phone More navigation. Long project names are shortened with the complete name in a tooltip. |
| Text, Shape, Trace, Arrange, Combine, Offset, Layout, Contours, Weeding, Cut preview | Workspace editors with preview, scrollable controls and fixed Apply/Cancel areas. Short screens reduce preview height. Narrow action groups stack instead of clipping. Arrange stages its changes and commits one undo record. |
| Prepare | Ordered Plotter, Layer setups, and Mat/origin sections. Compact setup uses the workspace width and an explicit preview toggle. Automatic loading remains the default. |
| Cut | Distinct Review, Running, Paused, Tool change, Loading mat, Stopped, Job ended, and Connection lost headings. Setup controls leave the active-job view. Stop remains available outside scrolling content. Tool confirmation remains unchecked and gates Continue. Result screens offer preparation of another job with fresh mat confirmation. Connection loss explicitly says the physical state is unknown. |
| Layers | Desktop list/detail layout; compact list-to-detail navigation with Back. Returning to a selection does not silently overwrite a staged preset. Numeric controls remain available for precise editing. |
| Materials & tools | Searchable lists, compact list/detail pages, saved presets, and a Use on selected layer action that opens a staged layer setup. Selecting a preset does not immediately change artwork. |
| Settings | Flat category selector; Controller settings has its own category. Machine motion is available through Machine. Appearance offers System, Light, Dark and density preferences. Planning labels sit above fields. Support actions fit narrow screens. Mat setup includes an origin diagram and loading preference. |
| Connection | Explicit USB/Network choice. USB exposes port and baud rate; Network exposes host and TCP port. Existing service validation and persistence are retained. |
| Machine | Wide two-column layout and compact scrolling layout, central Stop, persistent Stop movement, and a separate recovery section. Commands still use the existing machine service. |
| Projects and guide | Scrollable project/recovery lists, fixed Close, create/import routes, and ordered first-cut guidance. Opening a project returns to Design. |
| Errors and alarms | Scrollable explanation/details, fixed return/copy/details actions, and a machine-review route for alarms. Short phone screens retain usable footer buttons. |
| Unsaved document | Filename-specific Save project / Discard changes / Keep editing prompt. |
| Imports | SVG/DXF import adds to existing artwork and remains undoable. Opening a project keeps its separate semantics. |

## Verification

The renderer uses real Tk widgets, temporary test preferences, and an isolated Xvfb display. The gallery contains **135 renders**, with **zero clipped button labels or undersized custom-page controls** reported by the measurement pass. It covers 320×600, 390×844 and 1280×900, including every Settings category, both library kinds, guide steps, errors/details, dark appearance and simulated job states. `measurements.json` records clipped-button and undersized-control findings for the custom-page captures.

Automated acceptance tests additionally exercise 600, 768, 840, 1024 and 1440 pixel widths, including 1024×600 landscape. Tests cover navigation bounds, visible canvas, panel collapse across breakpoints, page lifecycle, palette/density changes, library search and staged assignment, explicit unsaved-prompt outcomes, short-screen alarm actions and connection-loss wording. Existing import, document/undo, controller and job regressions remain part of the full suite.

Coverage includes all new GUI modules, including workspace pages, appearance and icons. The greater-than-90% gate applies to the workflow/dialog UI layer; the complete application coverage is reported separately. Line coverage is not a visual similarity score.

The six body/secondary/primary text-and-background palette pairs measure 6.07:1–13.41:1 contrast (Light: 13.41, 6.07, 6.38; Dark: 13.09, 7.95, 8.78). These token calculations do not replace full accessibility testing.

Run from the repository root:

```sh
xvfb-run -a .venv/bin/python -m coverage run --source=bCNC -m unittest discover -s tests
.venv/bin/python tools/check_gui_coverage.py
xvfb-run -a -s '-screen 0 1440x1100x24' .venv/bin/python tools/render_gui_review.py
```

## Scope of visual evidence

These captures verify the actual Tk application, not a browser mockup. The proposal does not contain an exact reference image for every window and state, so this report does **not** certify pixel-for-pixel 1:1 equivalence. Desktop secondary editors use a workspace preview with a side inspector; native file/color/font pickers retain platform presentation. System appearance detection currently follows GNOME/GTK settings, with explicit Light/Dark available independently.

Phone dimensions are desktop-rendered layout checks. Physical phone/tablet deployment, on-screen keyboards, touch gestures, screen readers, 200% text and translated-label acceptance still require device/accessibility validation. Simulated running/paused/alarm captures are presentation evidence; no real cutting or machine movement was performed.

## Final automated result

**278 tests passed. GUI line coverage: 92.52% (3,837 / 4,147 statements). Complete application line coverage: 74.83%.** The GUI report has 0 excluded lines. Syntax compilation and `git diff --check` passed.
