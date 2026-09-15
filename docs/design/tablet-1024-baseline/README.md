# Tablet baseline: 1024 × 600

1024 × 600 is the primary tablet design baseline. Tablet and desktop widths of 1024 or more use the same arrangement: one header row with project/navigation/utilities, persistent connection status, a left icon rail, a central mat, and a right inspector. Larger windows allocate extra space to the canvas, rather than enlarging every control in proportion to resolution.

- All eight toolbar actions stay on the left, with 48-pixel minimum touch targets.
- Short windows reduce margins and spacing; the rail is tested at 1024 × 560 too, allowing for operating-system window chrome. Smaller layouts remain as a fallback; the app does not force a client window larger than the screen.
- The 1024 × 600 design canvas measures 629 × 436 in the test environment.
- Machine controls use equal columns and adjacent Step/Speed fields, keeping all jog arrows and Stop visible without scrolling.
- Text reflows when its actual parent width changes, preventing provisional narrow wrapping on pages such as Connection.
- Forms remain scrollable with their action footers accessible.

## Visual review

[All tablet screens](contact-sheet.png) · [Design workspace](workspace-0-1024x600.png) · [Machine](Machine-1024x600.png) · [Connection](Connection-1024x600.png) · [Larger desktop](desktop-1440x900.png)

The review renders all custom screen families, settings categories, first-cut guide stages, and error details using actual Tk widgets under Xvfb. The recorded control audit reports no clipped button labels, horizontally overflowing buttons, or touch targets below 44 pixels; the left-rail regression additionally requires every icon to remain at least 48 pixels tall and fully visible. Controls intentionally below a form's scroll viewport remain reachable by scrolling.

These are Linux layout and interaction checks. Physical tablet and macOS display validation is still separate from the automated review.

Final validation: **299 tests passed** (195 + 104), **GUI coverage 92.93%**, compilation and diff checks passed. The tablet control audit returned zero issues.
