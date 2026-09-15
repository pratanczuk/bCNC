# Plotter architecture and cleanup

Updated 2026-09-14.

## Dependency direction

Views call application services. Services consume explicit inputs or injected
ports. `bmain.Application` is a Tk application that **composes** a `Sender`; it no
longer inherits transport behavior. Controllers communicate through sender state
and queues, without calling Tk widgets or application callbacks.

| Layer | Modules | Responsibility |
| --- | --- | --- |
| Presentation | PlotterWorkflow, PlotterDesign, PlotterStudio, PlotterSettings, PlotterAdvanced, PlotterLayersUI, PlotterTk | Modern controls, previews, event helpers and unified feedback |
| Application services | PlotterEngine, PlotterMachine, PlotterConnections, PlotterDocument, PlotterTransforms | Cut preparation, guarded movement, connections, document transactions and source-preserving transforms |
| Domain | PlotterPlanning, PlotterPolicy, PlotterGeometry, PlotterEditing, PlotterLayers, PlotterProject, PlotterKnife | Cut validation, geometry, objects, layers and drag-knife compensation |
| Conversion | PlotterCompensation, PlotterCompilation, PlotterPath, PlotterShapes | Detached cut buffers, planar serialization and shape generation |
| Adapters | PlotterAdapters, PlotterFiles | Machine/job/connection/configuration ports and file persistence |
| Infrastructure | Sender, PlotterProtocol, controller adapters, CNC, CNCCanvas, lib | Transport, firmware parsing, document algorithms, undo and planar rendering |

The existing CNC document implementation remains active infrastructure. Machine
status and machine configuration still use `CNC.vars`; parser feed modes and
preview bounds belong to individual parser instances. This is a bounded migration,
not a claim that all historical source has been rewritten or all global state removed.

## Completed migration

- Removed hidden legacy panels, the plugin registry/database and all 17 old plugins.
  Config, System and manual machine controls remain in Advanced settings.
- Removed Application/Sender inheritance, transport file/history/UI callbacks,
  local command shells and controller callbacks into the GUI.
- Extracted file handling and document transforms. Arrange preserves editable text,
  source outlines, layer/group properties and a single undo transaction.
- Compilation uses a detached document and completes before submitting the buffer.
  It never temporarily swaps the live artwork. Cancellation leaves source intact.
  The completion marker follows the footer. Progress counts acknowledged commands;
  compensated line indices no longer select unrelated source artwork.
- Parser bounds and feed mode are instance state; constructing or interleaving
  preview/compile parsers cannot reset live status or another preview's bounds.
- Replaced custom file dialogs with standard Tk dialogs. Removed `tkExtra`,
  `tkDialogs`, `bFileDialog`, their obsolete widget classes and standalone demos.
  The remaining clipboard/event/tooltip functions live in `PlotterTk`.
- Removed inaccessible 3D canvas projections. The canvas maps X–Y mat coordinates
  directly; pressure/lift remains a machine setting, not another drawing view.
- Removed reviewed milling actions, obsolete command wrappers and their unused
  helper chains. Removed unused matrix/quaternion, cardinal/cubic spline,
  numeric formatting, milling-offset and path fitting utilities. DXF NURBS,
  planar vector operations, boolean operations and drag-knife geometry remain.
- Preserved GRBL 0.8/0.9 compatibility, capability detection for GRBL 1.x and
  grblHAL extensions. Retained current TCP/serial connections and friendly errors.
- Fixed dialog lifecycle cleanup: cancelling a design dialog also cancels its
  pending idle callback, preventing a later widget from receiving that callback.
- Removed obsolete developer switches and the Python-port startup warning.
  Serial/TCP, baud, geometry and disconnect-on-start command-line options are
  connected to the current application configuration again.

## Audit and regression protection

`tools/audit_unused.py --include-libraries` is a read-only reference audit. Its
only remaining candidates are `_moveTo`, `_curveToOne`, `_closePath` and `_endPath`
in `lib/font_text.py`. These are required overrides called by fontTools `BasePen`.
Architecture tests explicitly preserve them and fail if new unreviewed candidates
appear. Literal command mappings, Tk bindings, inheritance, undo callbacks and
operator methods were considered when reviewing removals.

Static name counting cannot prove every branch reachable in a dynamic Python
program. The audit is a regression guard, not permission to bulk-delete methods.
Active firmware compatibility and error-recovery branches are intentional.

Verification covers service imports without Tk/configuration modules, parser
isolation, compensation, transforms/undo, compiled buffers, firmware discovery,
real TCP sockets with simulated firmware, connections, layers, text and GUI layout.
Run the full suite with:

```sh
xvfb-run -a ../.venv/bin/python -W ignore::ResourceWarning -m unittest discover -s tests
```

Final verification: **187 tests passed**; byte compilation and diff whitespace
checks passed. A clean wheel was built and installed separately, passed its
package smoke check, and opened the connection GUI at 1024 × 768 with TCP and
autoconnect controls visible. Simulated firmware tests do not replace a physical
plotter acceptance cut.

Earlier automatic-review rejections concerned combined broad edit/test commands.
Those commands were not applied. This migration used separately reviewed edits
and standalone verification; no rejected command remains a prerequisite.

## Material and tool profiles

`PlotterLibrary` validates the material/tool catalog and portable layer process
snapshots; `PlotterLibraryUI` edits it without transport access. `PlotterLayers`
stores assignments in the undoable catalog, which `PlotterProject` validates and
round-trips with the artwork. `DocumentJobPort` passes these explicit snapshots,
the current material and selected tool pass to `JobParameters`.

`PlotterProcesses` prepares one physical tool pass from detached vector artwork.
Pen validation strips knife parameters; the planner additionally bypasses the
compensator for pens. `PlotterPath.tool_path_to_block` emits pressure-actuator
commands with the tool released during travel. The same prepared buffer drives
preview, export and transport compilation. Multi-tool jobs use `PlotterSequence`: every pass is validated and compiled
before beginning, then each physical tool exchange requires explicit confirmation.
There is no automatic tool changer.

## Normal completion and explicit cancellation

Normal job completion is acknowledged through the sender's final WAIT / Idle
condition. It must not schedule a controller reset for a later state transition.
The retired cleanAfter/jobDone hook could remain set after runEnded, then purge
and reset the controller when a subsequent mat homing operation returned to
Idle. That deferred cleanup path has been removed. Explicit Stop still uses its
controller purge/reset path. The GUI regression runs an actual application job
entry/completion followed by unload and checks that no purge or extra commands
are injected. Unexpected firmware banners still abort mat handling, retaining
the banner in technical details and showing specific restart/reload guidance.

## Guided tool exchange transactions

`sequence_blocks` plans pens before knives, keeps the user header/footer at the
sequence boundaries and rejects origin-changing startup/header commands.
`PlotterEngine.sequence` compiles immutable per-tool buffers; preview uses the
same planning while export remains restricted to individual passes.

`ToolSequence` owns homing, waiting-for-confirmation, running, completion and
cancellation states. It waits for command acknowledgments and fresh Idle
reports for M5, $HX and restoration of the original effective XY work offset.
It checks that Y did not move during homing and verifies restored offsets before
allowing confirmation. A changed connection, movement/offset change during an
exchange, alarm, reset, timeout or interruption invalidates the sequence.
Normal application completion explicitly advances the sequence; generic run-end
notifications cannot trigger another pass. Transport never prompts from its
worker thread; the UI monitor drives the transaction and confirmation controls.
