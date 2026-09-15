# Cut-screen fixes

- A completed or stopped cut shows an explicit Unload mat action and Prepare another job. It hides Start cut and returns from the phone preview to the setup panel.
- Completion above an open utility page or an existing warning uses a workspace page with Unload mat; the underlying page remains intact.
- The adaptive cut layout is now changed on phase transitions. The base workflow no longer repeatedly restores mat/setup controls that the adaptive screen hides.
- Connection status remains above the workspace and open pages: Disconnected or Connected with the current controller state.

Real Tk captures at 320 × 600: [finished cut](cut-finished-phone.png), [completion above another page](cut-finished-overlay.png).

Regression tests exercise stable mat-control mapping across repeated polls, completion after phone preview, unload action routing, unloading status/Stop, completion above an existing page, and connection-status visibility at phone and desktop sizes. Tests use simulated state and do not move hardware.

Validation: **291 tests passed** (187 + 104); **GUI coverage 92.84%**. Compilation and `git diff --check` passed.
