# Inspector redraw and performance regression

## Cause

The generic edit-control update enabled the Properties actions every poll. The selection-specific update then disabled them again when there was no selection. Each cycle rebuilt five rounded-button images twice, including disabled text rendering, at the normal four polls per second.

The same update also registered the unchanged Stop callback repeatedly, recalculated the unchanged project-header text, and reapplied action-row grids on redundant Configure events.

## Fix

- Give selection actions one state update, based on selection and machine activity.
- Skip unchanged button presentation updates and unchanged command registration.
- Choose the final Stop action once, including during mat movement.
- Cache project-title layout until its text, save status, or available width changes.
- Reflow action rows only when their column count changes.

## Evidence

Same local Xvfb fixture, 1280×900, no selected artwork, 25 calls to `workflow.update_state()` followed by `app.update()`, measured with `cProfile`:

| Metric | Before | After |
| --- | ---: | ---: |
| Total instrumented time | 1.478 s | 0.044 s |
| Time inside workflow state updates | 1.385 s | 0.031 s |
| New button images | 250 | 0 |

This is approximately 34× faster for the measured idle-update workload, not a claim about every application operation or device.

Regression tests exercise 600 idle updates across 1280×900, 840×700 and 390×844, with and without selection. They require stable control geometry, visibility and scroll position, zero new button images, and no callback-count growth. Another test verifies that unchanged callbacks are reused while changing a command still invokes the new action. Native disabled-button behavior remains covered.

Full regression suite: **280 tests passed**. GUI line coverage: **92.55%**; complete application: 74.86%.
