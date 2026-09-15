# Foil Studio: product review and implementation priorities

Reviewed 14 September 2026 against official documentation for Cricut **Design
Space** and Silhouette **Studio**. This is a documented feature comparison, not a
hands-on usability test or a claim of compatibility with their machines/files.

## What commercial tools do well

Cricut offers previewable offsets and combining overlapping offsets, including
text. We should make outlines easy to inspect before insertion, preserve sources,
and explain expansion versus inset in ordinary language.
[Official offset guide](https://help.cricut.com/hc/en-us/articles/360061650414-How-to-use-the-Offset-feature-in-Design-Space).

Cricut's text tools include circular curves and font/letter editing. Foil Studio
already creates multiline outlines from selected fonts, but loses editable text
semantics on insertion. Retaining content, font and spacing in a project document
would be more valuable than another font-picker facelift.
[Official text guide](https://help.cricut.com/hc/en-us/articles/5280755261719-Design-Space-Working-with-Text).

Cricut separates combining, slicing and welding. Our union, subtraction,
intersection, exclusion and concatenation cover core destructive geometry
operations. They are undoable, but are not persistent, editable operation groups;
our subtraction also does not create every leftover piece as a Slice operation
would. These differences should stay explicit.
[Official combine guide](https://help.cricut.com/hc/en-us/articles/9503908902551-Using-Combine-Slice-and-Weld-to-create-new-shapes-in-Design-Space).

Silhouette lists move/rotate/scale/align/replicate across its editions and a weed
line feature in Business Edition. Foil Studio has move/rotate/scale/mirror/center
and duplication; alignment between objects, distribution and repeat layouts
remain valuable gaps. A simple surrounding weeding rectangle is useful now, but
is not equivalent to automatic internal weed-line generation.
[Official edition comparison](https://www.silhouetteamerica.com/silhouette-studio).

## Implemented in this continuation

- Sidebar canvas and scrollbar occupy separate grid columns, with a visible gap;
  canvas content follows the available width. Footer actions remain outside the
  scrolling area. Sidebar width now reserves space for both buttons and scrollbar.
- **Offset & weeding border** in Design: outward/inward offsets, round or sharp
  joins, and a rectangular border around selected artwork. Offset calculation
  respects holes and welds overlapping selected filled shapes. Open paths are
  supported for borders; offsets require closed outlines.
- Live preview, friendly validation, empty-inset rejection, stale-artwork guard,
  and mat-boundary validation. Results retain original coordinates and are added
  as a separate object in one undo action. Source artwork is retained. Nothing is
  sent to the cutter by these editing actions.
- Header/footer staging, validation and undo transactions extracted to
  `PlotterDocument`; connection validation/lifecycle to `PlotterConnections`.
  Connection view no longer reaches into the hidden Serial frame. Its adapter
  preserves the same sender and existing partial-port cleanup/error handling.

## Ordered backlog and acceptance criteria

The priority 1 and 2 baseline below is now implemented. See [the feature guide](plotter-priority-features.md) for usage, verification and scope limits. Irregular nesting remains a later extension, as specified in the original plan.

| Priority | Addition | User benefit and completion criteria |
| --- | --- | --- |
| 1 | Align/distribute and repeat grid | Align selected objects to each other or mat; equal gaps; rows/columns with spacing; preview, one undo, overflow rejection |
| 1 | Editable project document | Save original text/font/style, groups, visibility and transformations independently of output G-code; versioned format and round-trip tests |
| 1 | Text layout | Reopen existing text, spacing, alignment and circular text; preserve counters and Unicode; explain missing-font substitution |
| 1 | Groups and material layers | Move an attached composition intact; choose layers for each foil color; preview exactly what will cut |
| 2 | Contour hide/repair and node tools | Remove unwanted trace islands without re-tracing; close gaps; simplify with bounded deviation; undo every edit |
| 2 | Internal weeding lines | Avoid artwork interiors, respect clearance, preview generated cuts and reject crossings |
| 2 | Material-saving placement | Start with deterministic rectangular packing; irregular nesting later; preserve groups, margins and source positions until Apply |
| 2 | Cut order preview | Inspect travel and cut sequence; inner holes before outer contours where appropriate; source untouched |
| 2 | Recovery and onboarding | Saved local projects, recent jobs, crash recovery and a guided first test cut; never auto-resume machine motion |
| Conditional | Print-and-cut registration | Requires a supported alignment/calibration workflow and verified machine capabilities; ordinary GRBL does not provide optical registration by itself |
| Outside foil/mat scope | Embroidery, rhinestones, milling, 3D, cloud marketplace, multi-cutter orchestration | Do not reintroduce removed core dependencies for unrelated commercial features |

## Architecture follow-through

Continue with an independent drag-knife geometry service, using line, arc, open,
closed and compound-contour fixtures against existing output before switching the
job adapter. Then move parser modal/formatting state and replace hidden widgets
one callback at a time. The current plugin bridge remains a real dependency and
must not be removed merely because its controls are hidden.

The project document is the prerequisite for editable text, operation groups and
layers. Building those only on generated G-code would make edits fragile and
repeat the coupling just removed from settings and connection setup.

## Verification for this continuation

- 125 tests pass under Xvfb, including seven added service/geometry/UI cases.
- All mapped sidebar descendants stay inside the viewport and left of the
  scrollbar in all three workflow steps at 1024×768 and 1280×900.
- Actual 1024×768 renders reviewed: [sidebar](screenshots/foil-studio-sidebar-fixed.png)
  and [outline dialog](screenshots/foil-studio-offset.png).
- Compilation, package entry-point smoke check and clean wheel installation pass.
- No physical plotter was connected or moved during verification.
