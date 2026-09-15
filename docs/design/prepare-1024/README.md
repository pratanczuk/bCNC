# Compact Prepare and cut settings

Prepare now has three visible tabs: Material, Plotter, and Mat. Each default section fits the 1024 × 600 client viewport without a sidebar scrollbar. The mat stays visible and Review job remains in the bottom action bar. Stop mat movement is shown while mat handling is active.

[Material](material.png) · [Plotter & tool](plotter-tool.png) · [Mat](mat.png)

## Pressure and speed audit

There are two distinct editors, with explicit purposes:

| Editor | Meaning | Access |
| --- | --- | --- |
| Cut settings | Active pressure and cutting speed | Prepare → Material → Cut settings, or the same form through Settings |
| Material presets | Saved reusable pressure and speed | Prepare → Material → Material presets → Cut settings in the library |

Prepare's summary is read-only. The duplicate Save shortcut and ambiguous Pressure button were removed. Library fields now say Preset speed and Preset pressure. Layers retain tool and operation assignments only. Machine's jog speed controls manual movement and does not change cutting speed. Controller maximum-feed settings are machine limits.

Changing pressure or speed in Cut settings selects Current settings before refreshing the preset library. This prevents the previously selected preset from silently restoring its old values. The saved preset is unchanged; selecting it again deliberately restores its settings. A regression test covers this behavior.

The scrollbar can still appear for unusually long tool names, multiple tool descriptions, active notices, enlarged fonts, or smaller windows. Linux/Xvfb verification is separate from physical tablet and macOS display validation.

Validation: **307 tests passed** (202 + 105), **GUI coverage 93.62%**, compilation and diff checks passed. At 1024 × 600, the sidebar viewport is 433 pixels tall; Material uses 392, Plotter 396, and Mat 389 pixels. All three have no default sidebar scrollbar.
