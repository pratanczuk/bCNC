# Cut preview cleanup

The default view now shows a compact visual legend for cut outlines, travel, and sequence numbers; a slider with an outline counter; and a short inner-first option. Longer tool/compensation information is behind Preview details. The subtitle describes a preview rather than adding artwork.

The sidebar wraps text using its allocated canvas width, preventing the narrow text column shown in the report. Regression checks cover 1868, 1280, 390, and 320 pixel widths, expandable details, and preview-only slider behavior.

Actual Tk captures: [desktop](cut-preview-1868x1060.png), [phone](cut-preview-390x844.png).

Validation: **292 tests passed**, **GUI coverage 92.88%**. Compilation and diff checks passed.
