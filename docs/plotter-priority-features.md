# Priority 1 and 2 features

Implemented on `codex/foil-studio-workflow`. The Design sidebar scrolls to expose
editing tools; Prepare provides the first-cut guide; Cut provides the sequence
preview and material-layer selection.

## Priority 1

| Feature | Where and how |
| --- | --- |
| Align and distribute | **Design → Layout**. Align left/right/top/bottom or either center axis against the selection or mat. Distribution uses equal edge gaps between at least three objects/groups and keeps the outer positions. |
| Repeat grid | **Layout → Repeat grid**. Set rows, columns and gap. The selected arrangement repeats intact. Attached groups remain units. Preview and mat validation happen before one undoable Apply. |
| Editable projects | **Save project**, **Projects & recovery**, or Ctrl+S. `.foil` is versioned UTF-8 JSON containing text/font/layout parameters, transforms, groups, layers, enabled state, color, passes, vector outlines and cut data. Use **Projects → Export prepared cut G-code** for an output file with the current cut settings and compensation; it preserves the editable project. SVG/G-code remain interchange/output formats. |
| Re-editable text | Select a text object and choose **Text** again. It restores text, font, size, spacing, alignment and radius. Applying retains its tracked position/rotation/scale. A missing font is explained before replacement. |
| Text layout | **Text → Spacing & curve**. Letter spacing in mm, line spacing as a multiplier, left/center/right multiline alignment, and a positive circle radius for a single curved line. Zero radius keeps text straight. |
| Attached groups | Select objects, then **Layers & objects → Objects → Attach**. Selecting a member on the canvas or sidebar expands the selection. Moving, arranging, packing and repeating treat attached groups as units. Detach is undoable. |
| Material layers | **Layers & objects** adds, renames, reorders and deletes explicit layers, including empty layers. Set a preview color and include/exclude layers from cuts. Delete can move contents to Default or remove the contents too. Default remains the permanent fallback. |
| Object manager | Search the layer/object tree and multi-select with Ctrl/Shift. Rename objects, move them between layers (also by dragging), reorder, duplicate, delete, attach/detach, set passes and override or inherit layer colors. Layer exclusion preserves individual object cut settings. All edits support Undo/Redo. |

Project loading validates the complete document before replacing the current job.
Writes use a temporary file and atomic replacement. Canceling a save during a
new/open operation keeps the current design. Projects do not store a live serial
session, machine position confirmation or a command to resume motion.

## Priority 2

| Feature | Where and how |
| --- | --- |
| Contour and node tools | **Design → Contours**. Select a contour, click a preview node or choose it in the node list, then move/insert/delete nodes. Hide removes the selected contour, Close gap enforces a distance limit, and Simplify enforces a deviation bound. Each Apply is undoable. |
| Weeding lines | **Design → Weed lines**. Set row spacing, clearance and border margin. Horizontal cuts are clipped outside the protected artwork; enclosed counters remain protected. The source remains unchanged and new cuts are a separate object on its material layer. |
| Material-saving placement | **Layout → Pack on mat**. Deterministic rectangular shelf packing with margin and gap, without rotating objects. Groups stay intact; overflow is rejected before editing. |
| Cut-order preview | **Cut → Preview cut sequence**. Scrub a slider through numbered outlines and inter-outline travel. The preview reads the prepared job, including compensation and passes, and sends no commands. Optional inner-first ordering works on a separate vector cut buffer. |
| Local recovery | Dirty projects receive an atomic recovery snapshot approximately every 30 seconds while idle. Recovery copies are under `foil-recovery` beside the user configuration. A subsequent session advertises available copies in Design; restore through **Projects & recovery**, then save as a project. |
| Recent projects | **Projects & recovery** lists up to 12 saved/opened project paths. Missing or damaged files use the unified friendly error presentation and do not erase the current design. |
| First-cut guide | Open from **Prepare** or **Projects & recovery**. It walks through connection, blade/pressure setup, a separate calibration design, mat positioning and result inspection. It never starts a cut; Start remains an explicit action in Cut. |

## Scope and practical limits

- Packing is a deterministic rectangular strategy, not irregular nesting or a
  guaranteed optimal material layout. Irregular nesting was explicitly a later
  extension in the plan.
- Node tools operate on polylines. Curves are approximated at 0.02 mm; simplify
  checks its requested deviation against that polyline. Moving a node explicitly
  changes geometry and is rejected when it creates a self-crossing closed ring.
- Contour Apply converts only the affected object to outlines. Undo restores its
  prior text properties. Other objects and material layers are retained.
- Supported Unicode characters depend on the chosen font. Missing glyphs are
  reported. Complex-script shaping is not implemented; circular text is one line.
- Edits through older raw-line tools cannot always be mapped back to text.
  Re-editing such stale text is blocked rather than silently overwriting those
  changes. Normal canvas movement and Design transforms maintain text metadata.
- Weeding is horizontal and protects entire outer silhouettes, including holes.
  Select one material layer at a time. It does not attempt automatic weed cuts
  inside glyph counters.
- Inner-first planning is available for vector-generated objects. Arbitrary
  imported machine G-code may include modal/tool actions and is not rewritten;
  turn inner-first off for those jobs. Disabled objects remain excluded.
- The cut preview shows XY outlines and travel between them. Startup/footer and
  vertical motion are not drawn; it is not a machine simulation or a timing
  estimate. Cut settings are machine/session preferences, not project contents.
- Recovery copies contain artwork only. They never reconnect, confirm the mat or
  resume an interrupted cut. A 30-second interval is not a guarantee that the
  most recent keystroke is recoverable. Normal exit clears this session's copy;
  older copies remain available for manual recovery.

## Engineering changes

- `PlotterEditing`: headless layout, affine transforms, contour repair, weeding
  and order planning.
- `PlotterProject`: versioned serialization, validation, atomic writes and
  document/property undo transactions using the existing undo stack.
- `PlotterProjectUI`: local save/open/recent/recovery integration.
- `PlotterLayers`: headless layer catalog, effective cut visibility and undoable object operations.
- `PlotterLayersUI`: persistent searchable layer/object tree with drag-and-drop and property tabs.
- `PlotterStudio`: preview views for layouts, contours, weeding, cut
  sequence, projects and onboarding.
- Text metadata follows shared application transforms, including canvas dragging.
  Block copying preserves independent project properties.
- The drag-knife bridge now operates on an isolated document through a minimal
  compatibility port. Every enabled contour of compound text/traces is processed;
  passes/colors are retained and plugin/feed settings are restored after failure
  or success. The real editor, source blocks and undo stack are never swapped.

## Verification

- 153 tests pass under Xvfb, including 28 new geometry/project/workflow tests.
- Coverage includes layout overflow, equal gaps, non-overlapping packing, Unicode
  text and counters, transform/edit/undo, groups, layer exclusion, contour edits,
  weed clearance, inner-first order, atomic-write failure, invalid files, recovery
  without motion, and multi-contour compensation.
- Dialogs inspected at 1024×768. Control-width and project-footer visibility checks
  protect against collapsed panes or inaccessible buttons. Sidebar checks cover
  all workflow steps at 1024×768 and 1280×900.
- No physical cutter was connected or moved during verification.
- Clean wheel built and installed outside the checkout; every new dialog opened
  from that installed package. Final targeted source-metadata/export tests pass.

## Screenshots

- [Layout and repeat](screenshots/foil-studio-layout.png)
- [Layer manager](screenshots/foil-studio-layers.png)
- [Object manager](screenshots/foil-studio-objects.png)
- [Contours and nodes](screenshots/foil-studio-contours.png)
- [Weeding lines](screenshots/foil-studio-weed-lines.png)
- [Cut preview](screenshots/foil-studio-cut-preview.png)
- [Projects, export and recovery](screenshots/foil-studio-projects.png)
- [First-cut guide](screenshots/foil-studio-first-cut-guide.png)
- [Editable text](screenshots/foil-studio-editable-text.png)

## TCP plotter connections

Connection setup accepts a USB serial port or a raw TCP endpoint, for example
`socket://plotter.local:8888` or `socket://192.168.1.50:8888`. Enter the endpoint in
**USB port or TCP address**; no separate driver or connection mode is required.
The hostname must resolve on the computer, and the port must match the plotter's
TCP service. Bracketed IPv6 addresses are also accepted.

The baud field is disabled for TCP because raw sockets do not use it. Refresh serial
ports retains the entered endpoint, and reopening connection setup restores the
chosen address through the existing connection preferences. Malformed URLs are
rejected before changing connection state. Hostname, refusal, timeout and lost
connection errors use network-specific recovery guidance.

The existing pySerial sender handles both transports. Verified with an actual
local TCP echo endpoint through sender open/write/read/close, URL validation,
selector behavior and the full 159-test regression suite. No physical network
plotter was contacted.

## Layer and object workflow

Use **+ Add layer**, then enter a name in the Layer tab and choose **Rename layer**.
Empty layers survive project save/open and recovery. Select objects in the tree
and use the Objects tab to move them to a layer. Drag onto a layer to append, or
onto an object to insert before it. Ordering controls change source cut order;
optional inner-first preparation can further adjust the generated cut sequence.

**Include/Exclude** controls whether artwork participates in the cut. Turning a
layer back on preserves objects that were individually excluded. **Only this
layer** is useful for cutting one material; **All layers** restores layer inclusion.
Changing a layer color updates objects that inherit it; explicit object colors remain.

Deleting a layer defaults to keeping its objects in Default. Choose **Delete
objects too** to remove its contents in the same undoable operation. Duplicates
start at the original position and preserve text, transforms and passes. Attached
groups move and duplicate together; object deletion and property edits apply to
the explicitly selected tree rows. Use Select attached group when needed.

The manager stays open after edits. Errors appear in its footer; stale selections
are refreshed before edits, and editing is blocked during a running cut.

Connection setup exposes **Automatically connect on startup**. Toggle it to enable
or disable the existing saved startup preference without connecting immediately.
The preference applies when reopening Foil Studio, using the saved serial port or
TCP address. Close leaves the selected preference in place; normal application
shutdown writes it to settings. This does not automatically start a cut.

## Automatic firmware detection

Connection setup defaults to **Automatic (recommended)** for GRBL 0.8/0.9,
1.0/1.1 and grblHAL. GRBL 1.0 keeps legacy jog behavior; 1.1/grblHAL enable their
supported modern controls. Identification and report readiness are shown in the
workspace footer. Manual profiles are available for troubleshooting. Serial baud
remains a user setting (older GRBL boards may use 9600); TCP does not use it.

Connecting or enabling autoconnect does not explicitly reset, unlock, resume,
execute initialization macros or start a cut. Discovery waits for usable reports.
Advanced settings retain deliberate reset/homing/recovery actions. The retired
Connection initialization field is removed; job startup/header/footer are unchanged.
All connection preferences now live outside the old hidden Serial panel, which has
been deleted together with the other legacy page/ribbon views.
