# Scrollbar audit at 1024 × 600

The audit renders 59 actual Tk screen states with isolated test preferences and no hardware commands: editing dialogs, all layer sections, text/trace tabs, material and tool library sections, pen-specific fields, settings categories, both connection modes, the guide, errors/details, the three workspace steps, dark appearance, running/paused cuts, tool exchange, completion/unload, and connection loss.

[Browse all screenshots](index.html) · [Recorded scrollbar ranges](measurements.json)

## Changes

- Shared form, list, and text scrollbars appear only when content overflows. Grid and pack positions are retained when a scrollbar returns. Scroll frames refresh their bounds when remapped or re-entered after offscreen content changes.
- Materials & tools uses compact section tabs and two-column fields, with inline Save/Use actions. All library sections fit without default form scrollbars.
- Shape and boolean-operation choices use dropdowns instead of five full-height button rows.
- Short settings use adjacent labels and fields, compact actions, and separate Mat setup / Mat loading pages. Advanced pages use the available viewport instead of a fixed tall notebook, avoiding nested outer scrolling.
- Connection uses inline transport fields, refresh, and disconnect controls; empty feedback no longer reserves a blank row.
- More uses two columns, with Back and Exit kept visible.

## Results and limits

No unnecessary full-range form/list scrollbar was found. Layers, library sections, Shape, Combine, Cut preview, Appearance, Pressure & speed, Drag knife, Mat setup, Mat loading, Job commands, Controller settings, both Connection modes, Machine, More, guide stages, and the default error views fit without form scrollbars.

Long content still scrolls: text/font selection and spacing, tracing options, arrangement/layout/contour/weeding forms, projects/recovery, planning defaults, and the support log. Those scrollbars are retained because their content exceeds the current viewport; this change does not claim that every long form has been redesigned to eliminate scrolling. Dynamic lists can also gain a scrollbar as entries are added. The cut-preview progress slider is an input control and remains available.

Validation: **305 tests passed** (201 regression + 104 workflow), plus focused rechecks after the final short-form spacing adjustments. **GUI coverage: 93.28%**, above the 90% gate. Compilation and diff checks passed. The geometry audit returned zero unnecessary scrollbar or button-boundary findings.

These are Linux/Xvfb checks of the app's own views at a 1024 × 600 client viewport. Native operating-system file dialogs and physical tablet/macOS display behavior are outside this render audit.

Reproduce with `xvfb-run -a .venv/bin/python tools/audit_tablet_scrollbars.py`.
