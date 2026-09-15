# Navigation, startup, touch exit, and node dragging

## Changes

- Opening a workspace page styles only that page using the current palette. It no longer runs the system-theme subprocess, repaints every existing button, or reapplies global ttk styles.
- Pages receive styling before being presented. Reopening a page retains its responsive-text handler instead of adding another binding. Presentation no longer forces an intermediate idle paint.
- Rounded buttons retain geometry when icon/height values are unchanged. Fonts and text measurements are reused within the current Tk root; the text cache is bounded to 512 entries.
- **More → Exit application** remains in the fixed footer at desktop and phone sizes. It uses the normal unsaved-project prompt. Cancel retains the control registry, and repeated exit attempts cannot bypass active job/mat/tool-sequence checks.
- **Contours & nodes → Move node** supports press/drag/release. The coordinate transform stays fixed during dragging, moved handles remain pickable, and the document changes only on Apply. Cancel and Undo retain their existing behavior.

## Local measurements

Same Xvfb fixture (`AdaptiveGUITest.setUpClass`), cProfile enabled, one startup followed by Machine and Layers opening and `app.update()`. These are indicative local timings, not hardware guarantees.

| Operation | Before | After |
| --- | ---: | ---: |
| Startup fixture | 2.34 s | 1.46 s |
| Machine | 1.11 s | 0.61 s |
| Layers | 1.66 s | 0.83 s |

## Visual checks

Actual Tk captures: [phone Exit](exit-320x600.png), [desktop Exit](exit-1280x900.png), [dragged node preview](node-drag.png). No hardware connection or motion was used.

Regression tests cover scoped styling, stable bindings, reused measurements, visible touch exit, canceled/successful exit, repeated exit attempts during motion, mouse drag coordinates, preview isolation, Apply/Undo, and ignoring drags outside nodes or during a job.

Validation: **286 tests passed** (182 + 104 in separate processes, combined coverage). GUI layer coverage: **92.69%**; full application coverage: **75.17%**. Bytecode compilation and `git diff --check` passed.
