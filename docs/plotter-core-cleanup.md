# Plotter core cleanup: analysis and implementation plan

## Scope and evidence

This fork supports foil/vinyl cutting on a mat with GRBL/grblHAL. The audit traced
imports, plugin discovery, controller discovery, file dispatch, packaging scripts,
and existing GUI callbacks. Source files were removed only where remaining
plotter code had no dependency on them. Git history remains the recovery source.

## Completed in this change

- Removed G2Core and Smoothie controller implementations; GRBL0, GRBL1 and their
  shared controller classes remain. Removed obsolete terminal-state handling.
- Removed 27 plugins outside the supported plotter allowlist: 3D slicing,
  drilling, milling, carving, laser/pyrography, and miscellaneous generators.
- Removed private mesh, gear, MIDI and height-map libraries plus the vendored STL
  package and its python_utils helper package. Remaining import scans show no
  callers of these libraries.
- Removed scipy, numpy-stl, ply, and tkinter-gl runtime dependencies. The GL
  package had no Python imports anywhere in the application. Updated Debian,
  ARMv7, and CI package validation paths to match the retained runtime.
- Removed the legacy_plugins escape hatch: retired plugins cannot be re-enabled
  by a stale user configuration. The supported plugin allowlist remains explicit.
- Removed the mesh-import advertisement and mesh entries from file pickers.
  Explicit STL/PLY imports now fail before changing the current artwork.

First-pass removed source: **51 files, 14958 lines**. The inventory below records the
pre-deletion line count, not the net diff across the rest of the branch.

## Executed follow-up stages

1. Added `PlotterEngine` as the workspace job/control interface. It prepares a
   separate cut buffer, applies pressure/feed settings, performs drag-knife
   compensation and checks the resulting mat bounds. Start, pause and stop use
   the existing sender. The compiler rejects retired drilling/probing/tool-change
   commands before adding even the startup/header to its queue.
2. Removed Stock, Material, EndMill, Cut, Drill, Profile, Pocket and Tabs records,
   their fixed diagnostic controls, and milling generators from CNC.py. The
   modern material/blade settings and presets are now the product model. Kept
   generic plugin editing and supported vector tools. Old milling commands show
   a friendly explanation; old saved tool selections fall back to CNC settings.
3. Removed ProbePage, Probe/Orient objects, autolevel compilation, canned-cycle
   expansion/rendering, manual tool-change macros, orientation markers, height-map
   rendering and probe STL export (`bstl.py`). Probe/orientation/XYZ/mesh file
   requests are rejected before changing artwork. GRBL pin status and PRB/TLO
   telemetry remain independent of height maps; `Pn:P` still reaches MatManager.
   G80 remains valid as GRBL motion cancellation, with no canned-cycle generator.
4. Routed diagnostic text and trace actions through the modern dialogs. Extracted
   shared font discovery into FontDiscovery.py; deleted TextGenerator.py,
   ImageTraceDialog.py and the old SHX text plugin. Removed shxparser from runtime,
   Debian/ARM and Flatpak dependency definitions. Text uses TrueType/OpenType.
5. Removed the pendant HTTP server, web assets, icons, ribbon group, CLI switches
   and defaults. Renamed its formerly shared queue to a local command queue so
   custom buttons still execute on the Tk thread. Saved layouts containing the
   pendant or Probe page are tolerated without startup errors.

## Retained core

| Component | Active reason |
| --- | --- |
| CNC parser, motion/path model, compiler and undo | GRBL streaming, preview, import/export and editing |
| bpath/bmath, DXF/SVG and font geometry | Shapes, text, booleans and drag-knife compensation |
| Z-axis and spindle/PWM commands | Blade lift/down and pressure output |
| GRBL0/GRBL1 and shared controller code | Connection, status, alarms and streaming |
| NumPy, Pillow, OpenCV, fontTools, Shapely | Active image, text and vector paths |
| Generic diagnostic settings/plugin editor | Controller settings and supported vector tools |

## Verification and external follow-up

- **108 tests pass** under Xvfb: real Tk/editor integration, header/footer
  editing/defaults and undo, fonts, tracing, booleans, drag-knife compensation,
  source-preserving pressure/feed streaming, old saved layouts, rejected legacy
  files/commands, modern diagnostic dialogs and mat pin/PRB telemetry.
- Clean wheel built from a temporary source copy, inspected for retired modules
  and dependencies, installed into an isolated target without downloading
  dependencies, and passed the installed package smoke check using the existing
  application Python environment. Source package smoke and packaging shell/JSON
  checks also pass.
- Real GRBL/grblHAL cutter checks and native cross-platform installer builds
  remain external validation. No physical pressure, knife or mat-sensor behavior
  is claimed from simulated serial reports.

## Removed-file inventory

```text
bCNC/controllers/G2Core.py: 248 lines
bCNC/controllers/SMOOTHIE.py: 127 lines
bCNC/lib/imageToGcode.py: 1358 lines
bCNC/lib/involute.py: 469 lines
bCNC/lib/meshcut.py: 364 lines
bCNC/lib/midiparser.py: 324 lines
bCNC/lib/ply.py: 76 lines
bCNC/lib/python_utils/__about__.py: 9 lines
bCNC/lib/python_utils/__init__.py: 0 lines
bCNC/lib/python_utils/compat.py: 0 lines
bCNC/lib/python_utils/converters.py: 233 lines
bCNC/lib/python_utils/formatters.py: 112 lines
bCNC/lib/python_utils/import_.py: 78 lines
bCNC/lib/python_utils/logger.py: 62 lines
bCNC/lib/python_utils/terminal.py: 167 lines
bCNC/lib/python_utils/time.py: 63 lines
bCNC/lib/stl/__about__.py: 12 lines
bCNC/lib/stl/__init__.py: 20 lines
bCNC/lib/stl/_speedups.pyx: 178 lines
bCNC/lib/stl/base.py: 585 lines
bCNC/lib/stl/main.py: 120 lines
bCNC/lib/stl/mesh.py: 5 lines
bCNC/lib/stl/stl.py: 395 lines
bCNC/lib/stl/utils.py: 21 lines
bCNC/plugins/Helical_Descent.py: 521 lines
bCNC/plugins/LaserCut.py: 462 lines
bCNC/plugins/Random.py: 79 lines
bCNC/plugins/bowl.py: 135 lines
bCNC/plugins/box.py: 458 lines
bCNC/plugins/driller.py: 455 lines
bCNC/plugins/drillmark.py: 318 lines
bCNC/plugins/endmilloffset.py: 573 lines
bCNC/plugins/flatten.py: 326 lines
bCNC/plugins/function_plot.py: 273 lines
bCNC/plugins/halftone.py: 293 lines
bCNC/plugins/heightmap.py: 401 lines
bCNC/plugins/hilbert.py: 150 lines
bCNC/plugins/involuteGear.py: 276 lines
bCNC/plugins/jigsaw.py: 426 lines
bCNC/plugins/midi2cnc.py: 344 lines
bCNC/plugins/pyrograph.py: 214 lines
bCNC/plugins/simpleDrill.py: 110 lines
bCNC/plugins/sketch.py: 371 lines
bCNC/plugins/slicemesh.py: 343 lines
bCNC/plugins/spiral.py: 513 lines
bCNC/plugins/spirograph.py: 149 lines
bCNC/plugins/stlSlicer.py: 860 lines
bCNC/plugins/trochoidPath.py: 107 lines
bCNC/plugins/trochoidal.py: 283 lines
bCNC/plugins/trochoidal_3D.py: 1335 lines
bCNC/plugins/zigzag.py: 157 lines
```

## Additional follow-up removals

- bCNC/ProbePage.py and bCNC/lib/bstl.py
- bCNC/TextGenerator.py, bCNC/ImageTraceDialog.py and bCNC/plugins/text.py
- bCNC/Pendant.py, bCNC/pendant/* and its start/stop icons
- Milling, probing and orientation code removed from the retained shared files
  CNC.py, ToolsPage.py, CNCCanvas.py, bmain.py and Sender.py, with their callers.

## Advanced settings migration: option audit

| Former diagnostics option | Result |
| --- | --- |
| Config and system language | Advanced → Configuration and System |
| GRBL controller settings | Read actual values, edit/send one selected setting, reread to verify |
| Header/footer | Advanced → Job G-code, with undo and new-design defaults |
| XYZ manual control, home, zero, reset/unlock | Redesigned Machine control; connection/state/queue guards |
| Serial setup | Existing modern Connection dialog, also linked from Machine control |
| Terminal output and configuration files | Read-only System viewer with Copy |
| Raw command bar and alternate run path | Removed from the product UI |
| CAM/plugin/database ribbon and duplicate editor options | Removed; use Design tools |
| Camera, arbitrary colors/fonts and shortcut editors | Removed from settings; text font selection remains in Design |
| Application laser/six-axis switches | Removed; blade PWM and Z lift retained; actual firmware settings remain readable |
| Global movement shortcuts and start/stop shell hooks | Removed |

Hidden editor/status widgets remain because the sender and canvas still use their
callbacks. The diagnostics toggle no longer reveals them. Opening Advanced during
a cut permits viewing System information and stopping; configuration writes and
manual movement remain guarded. New tests cover staged configuration, firmware
writes, jogging on both GRBL drivers, system views and removed keyboard movement.

## Follow-up dependency audit

Removed the camera module and canvas overlay/capture callbacks, hidden ABC-axis
DRO/jog frames, the unreferenced custom TrueType parser (`lib/ttf.py`), the unused
Mayavi mesh helper (`lib/utils.py`), unreachable command-bar focus shortcuts and
unused laser-mode branches in blade Z helpers. TrueType/OpenType text continues
through fontTools; blade lift and pressure commands remain covered by tests.

Replaced the obsolete pendant/PyAutoGUI smoke harness with a subprocess check of
the current module entry point. Removed its fixture/configuration and Python 2
Travis setup; GitHub Actions now runs unittest discovery under Xvfb. Arduino
loopback and fake-GRBL scripts remain useful standalone hardware tools.

Verification: 108 discoverable tests, source compilation and package smoke checks.
Static import inspection found callers for every remaining top-level/shared
library module. This does not claim that every method in shared legacy editor
and controller classes is removable or unused; dynamic callbacks remain active.
