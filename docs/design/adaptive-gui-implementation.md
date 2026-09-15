# Adaptive GUI implementation

## Current implementation

Foil Studio uses a shared rounded control system and responsive workspace pages for its editors and utilities. Project/save status, Properties/Layers, desktop outline icons, phone More navigation, focused setup/job views, separate Machine controls and Appearance settings are implemented.

The latest screen-by-screen details, acceptance scope and real application captures are in the [GUI correction report](gui-review-fixed/README.md) and [screenshot gallery](gui-review-fixed/index.html). The original [proposal](foil-studio-ui-proposal.md) and [audit](visual-audit-2026-09-15/README.md) remain available for comparison. Screenshots in `docs/screenshots/adaptive-*` are earlier implementation captures.

SVG/DXF import adds to the current document and preserves undo. The bundled mat-loading default is Automatic; an explicitly saved Manual preference is respected. Properties edits selected artwork, while Select activates canvas selection. Hide/Show panel changes the real canvas space and retains its state across resizing.

## Local checkpoints

`old-gui` is an annotated local tag at `c37348a`, preserving the original implementation. Work on the redesign remains local; no remote push is part of this task.

## Coverage contract

Coverage is collected for **all `bCNC` application Python modules**. The enforced **greater-than-90% line coverage** gate covers the workflow and dialog UI modules listed in `tools/check_gui_coverage.py`, including reused editors and the new workspace-page, appearance and icon modules. The complete application number is reported separately; legacy canvas, sender and geometry coverage is not claimed to exceed 90%.

Tests use real Tk widgets under Xvfb, real document geometry and undo, and mocked/loopback machine transports. The GUI acceptance tests verify responsive control bounds, staged edits, page return behavior, palette/density changes, library assignment, unsaved-prompt results, short-screen alarm controls and truthful connection-loss state.

```sh
xvfb-run -a .venv/bin/python -m coverage run --source=bCNC -m unittest discover -s tests
.venv/bin/python tools/check_gui_coverage.py
```

The gate writes application and GUI JSON reports to `artifacts/coverage/` and the complete HTML report to `htmlcov/index.html`.

## Launch

```sh
.venv/bin/python -m bCNC -S
```

`-S` disables automatic connection for that launch. Restart an already-running application to load the revised code. No real cutting or machine movement was performed by these tests.

## Final automated result

**278 tests passed. GUI line coverage: 92.52% (3,837 / 4,147 statements). Complete application line coverage: 74.83%.** The GUI report has 0 excluded lines. Syntax compilation and `git diff --check` passed.
