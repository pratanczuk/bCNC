# Configuration and navigation review

Implemented 2026-09-15.

The bundled `bCNC/bCNC.ini` now contains current settings only. Removed Control, Buttons, Box, obsolete DragKnife preset lists, Warning, ribbon/DRO font settings, fixed canvas view, unused spindle settings and DRO padding. Removed the write-only window sash preference and its unused CNC padding loader.

`PlotterPreferences.py` describes additional persisted runtime keys beyond the defaults: window/language/update state, plotter calibration and profile libraries, recent files/projects, text/font selection and retained CNC values. Numeric `Controller.grbl_*` settings and arbitrary compiler `Error` command rules are intentionally supported dynamic entries. `[Error]` remains in the defaults because the compiler reads it. Adding a new preference requires adding a bundled default or a schema entry.

Saving creates a filtered copy of the active configuration and writes only values differing from defaults. It removes unsupported sections/options and empty sections. It does not delete defaults from the live configuration. Loading starts with a fresh parser so switching files cannot retain settings from the previous file. Writes use a temporary file in the same directory, flush/fsync and atomic replacement. The previous user file is backed up once as `<user-file>.before-cleanup`. Failed replacement leaves the previous file available. Old DragKnife overcut and external-editor values have migration paths.

New installations create the user override file on normal settings save/exit; they do not copy the old plugin-filled default template. Existing pressure, profiles, serial/TCP endpoint, autoconnect, and custom startup/header/footer overrides remain supported. The actual home-directory preferences were not rewritten by development tests; migration applies on the next normal save in the updated app.

The persistent footer now provides Back plus the existing contextual forward/start action. Back is disabled on Design. Navigation, including header tabs and direct `show_step` calls, is blocked while a cut, mat transaction or tool sequence is active. Invalid step indexes are ignored. Users can revisit Design and Prepare without connecting the machine; final start remains protected by the full cut-readiness checks.

Regression coverage includes initial creation, repeat saves, runtime-default preservation, legacy overcut migration, dynamic settings, custom multiline G-code, failed replacement, forward/back transitions and navigation locks. No plotter motion is needed for these checks.

Advanced settings regression: restored its original field/validation module after a naming collision during this change. Persistence ownership lives separately in `PlotterPreferences.py`. Added real header-button/tab tests, disk-save/reopen coverage, and Apply guards during mat/tool transactions.
