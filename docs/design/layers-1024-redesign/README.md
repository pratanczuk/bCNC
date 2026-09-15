# Layers & objects at 1024 × 600

The layer/object list and editing controls use two equal columns. Selecting a row opens the corresponding Layer or Objects controls; the highlighted header buttons can switch between them. Search, selection actions, Undo, Redo, and Done remain visible.

Long forms are split into three short sections per context:

- Layer: Cut setup, Layer options, Manage.
- Objects: Properties, Arrange, Appearance.

All six sections fit the 1024 × 600 client viewport with no scrollbar at the standard font size. Actions have a minimum height of 48 pixels, list rows are 44 pixels, and text fields share rows with their Apply, Rename, or Move action. The list scrollbar appears only when rows exceed the available height. Detail pages retain an automatic scrollbar as a fallback for smaller windows or enlarged text.

## Screenshots

These are actual Tk screenshots under Linux/Xvfb, captured at 1024 × 600. Physical tablet and macOS display behavior still needs device validation.

- [Cut setup](layer-cut-setup.png)
- [Layer options](layer-options.png)
- [Manage layer](layer-manage.png)
- [Object properties](object-properties.png)
- [Arrange objects](object-arrange.png)
- [Object appearance](object-appearance.png)

## Regression checks

The layout tests visit all six sections, require their content and action buttons to fit, and verify that no scrollbar appears. Another test fills the list, confirms that its scrollbar appears, filters it to an empty result, and confirms that the scrollbar disappears. Existing layer lifecycle and drag/drop tests cover the reorganized actions.

Final validation: **301 tests passed** across the 197-test regression group and the separate 104-test workflow run. **GUI coverage: 92.99%**, above the 90% gate. Compilation and diff checks passed. The first workflow run had an intermittent failure in the existing import/center test; that test passed alone and the subsequent complete workflow run passed without changes to centering code.
