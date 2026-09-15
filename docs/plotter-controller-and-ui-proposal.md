# Hidden UI removal and GRBL controller proposal

Reviewed and implemented 2026-09-14. The original audit and proposal below record
the migration rationale; the Implementation status section records the completed
changes. This is not hardware compatibility certification. The firmware survey
covers principal protocol families and representative forks, not every vendor build.

## Recommendation

Remove the legacy hidden GUI in stages, moving its state and behavior into the
existing application services first. Present **Firmware: Automatic (recommended)**
in the normal connection flow. Internally keep a shared GRBL implementation with
legacy/modern report parsers and capability-based family extensions. Do not create
one controller implementation for each processor board or minor firmware version.

## Hidden UI dependency audit

`PlotterWorkflow.set_workspace()` hides the ribbon, legacy pane/status, canvas
toolbar and mat panel after they have already been constructed. Hidden does not
mean unused: several widgets currently act as models and service dependencies.

| Component | Current live dependency | Replacement and removal order |
| --- | --- | --- |
| Serial frame in FilePage | `LegacyConnectionPort` reads/writes port, baud, firmware and autostart widgets; `Application.openClose()` uses them; `SerialFrame.saveConfig()` persists them | First: a plain ConnectionPreferences model and settings adapter; route startup/manual connect through the same service. Then delete SerialFrame and its registry dependencies. |
| Legacy mat panel | `Application._monitorSerial()` invokes `MatStatusPanel.updateSensorState()`; this can call `show()` and start a polling loop | First: move sensor interpretation into machine state and keep a single telemetry poll owner. Remove panel construction and callback. Verify Pn input does not resurrect an old panel. |
| DRO / State / Control frames | Serial monitor updates coordinates, feed and modal state through widgets; legacy command handling reads spindle and step variables | Replace with MachineState and explicit machine actions. Preserve modern Advanced settings / Machine controls. Remove old frames and their bindings once no command depends on them. |
| Terminal and buffer listboxes | Serial monitor stores incoming/outgoing traffic there; modern System → Connection log reads `app.terminal` | Replace with bounded structured log storage and a modern read-only log view. Preserve error/reporting ordering and diagnostics export. Then remove TerminalPage widgets. |
| Editor frame / CNCList | Modern drawing, selection, undo and canvas operations call `app.editor`; 86 call sites in bmain and Plotter modules at review | Last major dependency: extract document selection and editing commands, then retire CNCList/EditorPage presentation. Keep geometry, GCode and undo behavior. |
| CAM tools frame | `Tools` data backs advanced CNC configuration and drag-knife compatibility; bmain still calls CAM population | Separate Tools/CNC/plugin settings from ToolsFrame. Keep header/footer and drag-knife configuration; remove CAM presentation after migrating its entry points. |
| Ribbon, status bars, hidden canvas toolbar | Page registration, layout persistence, events, progress variables and view settings still use these | Replace bindings and progress/view state, then stop constructing the shell. Remove stale layout keys through a compatibility reader. Keep canvas renderer and modern workspace. |

Do not replace these widgets with fake invisible widgets or dummy methods. The
end state is application state independent of Tk, with the visible GUI observing it.
Configuration and System remain in Advanced settings, as requested previously.

## What GRBL0 and GRBL1 currently mean

- `controllers/GRBL0.py` uses a legacy comma-delimited status regex and has no
  overrides. It assumes both machine/work positions in its expected report shape.
- `controllers/GRBL1.py` uses pipe-delimited reports, enables overrides, and uses
  `$J` jogging. Its comment says 1.0+, but a major version alone is insufficient to
  establish those capabilities.
- `_GenericController.parseLine()` already tries detection: after a Grbl or
  CarbideMotion banner it takes the first character of the version and chooses
  `GRBL0` or `GRBL1`. It does not negotiate a capability profile.
- `Sender.open()` toggles DTR, sleeps, clears input, sends blank lines and initializes
  the controller. This is a serial-era startup sequence even for socket URLs.
- `PlotterMachine` chooses jog/cancel behavior by the literal `GRBL1` name.

Concrete gaps to fix before claiming broad compatibility:

1. GRBL1 handles MPos but not WPos reports. It computes work position before a
   later WCO field is processed, potentially retaining an old offset for that
   update. Parse a report fully, then derive coordinates. Respect report units.
   Upstream permits either position form and varying optional field order.
   [GRBL interface](https://github.com/gnea/grbl/blob/master/doc/markdown/interface.md)
2. A connection without a welcome banner needs active identification and a
   handshake timeout. A socket opening successfully is not firmware readiness.
3. Version detection needs robust parsing, separate firmware identity and protocol
   capabilities, and an explicit unknown state. A fork version such as 1.2 or 1.3
   is not a new official GRBL protocol specification.
4. Settings parsing currently recognizes only numeric `$number=value` values.
   That cannot be a universal configuration model for extended firmware.
5. On a banner during a run, current generic code sends `$X` automatically.
   Change reset recovery to end the job, invalidate position/mat confirmation,
   and require deliberate recovery. Do not unlock/resume as part of detection.

## Firmware families and proposed treatment

The treatment column is our design recommendation, not verified current support.

| Family | Protocol evidence / relevant distinction | Proposed treatment |
| --- | --- | --- |
| Original GRBL 0.8 / 0.9 | Legacy status format and older sender interface | Retain a tested legacy parser for existing plotters; mark pre-1.1 support as legacy. Do not force an upgrade merely to connect. [Original interface](https://github.com/grbl/grbl/wiki/Interfacing-with-Grbl) |
| GRBL 1.0-era builds | 1.1 introduced sender-facing changes including jogging/overrides | Do not treat every 1.x build as 1.1. Require known transcript coverage or keep unsupported capabilities disabled. [1.1 changes](https://github.com/gnea/grbl/blob/master/doc/markdown/change_summary.md) |
| GRBL 1.1 | Standard modern reports, real-time controls and jogging | Primary baseline, shared modern parser. [Interface](https://github.com/gnea/grbl/blob/master/doc/markdown/interface.md) |
| Grbl-Mega / Mega-5X | Mega builds and extended axis variants | Same underlying protocol family where proven; accept extra report coordinates without offering extra cutting axes. Do not add a Mega-specific selector. [Mega](https://github.com/gnea/grbl-Mega), [Mega-5X](https://github.com/fra589/grbl-Mega-5X) |
| grblHAL and its board drivers | Configurable compatibility levels alter identity and extensions; level 0 identifies as GrblHAL | First-class family capability profile on shared GRBL parsing. Board-specific differences belong in discovered capabilities and machine configuration. [Compatibility levels](https://github.com/grblHAL/core/wiki/Compatibility-level), [Core](https://github.com/grblHAL/core) |
| Grbl_ESP32 | ESP32 port whose project points to FluidNC as its successor | Compatibility profile backed by real transcripts; no separate full sender implementation. [Project](https://github.com/bdring/Grbl_Esp32) |
| FluidNC | Maintains normal GRBL sender operations but largely replaces numeric settings with machine configuration files | Shared streaming plus a FluidNC identity/configuration adapter; do not expose GRBL settings writes as universally applicable. [Project documentation](https://github.com/bdring/FluidNC) |
| Servo/plotter forks | Firmware can repurpose spindle/laser output to drive a servo | Reuse protocol support; add an explicit tool-actuation profile and calibration. Identifying GRBL does not identify pressure or blade-lift semantics. [grbl-servo](https://github.com/cprezzi/grbl-servo) |
| Other GRBL-compatible implementations, e.g. µCNC | Independent implementation with GRBL-compatible communications and configurable tools | Experimental generic compatibility until fixture/hardware validation; add family extensions only for demonstrated differences. [µCNC](https://github.com/Paciente8159/uCNC) |
| Vendor/private forks and old processor ports | Identity alone cannot establish actual behavior | Save identity/transcripts, apply conservative capabilities, and certify individual tested profiles. Do not promise all-fork support. |

For grblHAL, upstream warns that native USB/network connections may produce no
welcome banner. Its sender guidance describes extended status and information
queries, extensible reports, and discoverable settings/error/alarm descriptions.
Use these when available with a baseline fallback. The guidance is explicitly a
draft; its speculative reset suggestions should not become automatic recovery.
[grblHAL sender guidance](https://github.com/grblHAL/core/wiki/For-sender-developers)

## Target architecture and user experience

Separate four concerns:

1. **Transport:** serial, raw TCP; WebSocket/telnet negotiation only if separately
   implemented. A `socket://` URL currently means a raw byte stream.
2. **Protocol:** framing, acknowledgements, status parsers, discovery, streaming.
3. **Capabilities:** jogging/cancel, overrides, coordinates, buffer limits,
   supported information/settings queries, extended real-time commands and states.
4. **Plotter profile:** XY working area, pressure range/actuator, lift commands,
   sensor mapping and drag-knife geometry. Never infer physical force from an S value.

Normal connection setup shows address, serial baud if relevant, autoconnect and
**Automatic firmware detection**. After connecting, show a readable identity such
as “grblHAL · detected” plus “Ready”, “Homing required”, or “Identification incomplete”.
Advanced connection options retain manual protocol overrides for troubleshooting:
Automatic / GRBL legacy / GRBL 1.1-compatible / grblHAL / FluidNC. These select
profiles, not independent duplicated controller classes. Unsupported profiles must
not be offered as working choices before their tests pass.

Proposed connection sequence:

- Open transport and collect incoming data; retain startup traffic.
- Use baseline status requests and a bounded timeout; inspect report dialect.
- Query build information when the reported state permits it. Once extension
  support is evidenced, request extended identity/capabilities.
- Commit a profile only after consistent evidence. A manual override does not
  bypass readiness or cause resets. Unknown capability stays unavailable.
- Keep connection/discovery apart from reset, unlock, homing, job startup and
  pressure actuation. Reset-on-connect may remain an explicit legacy serial option.
- Preserve ack-based streaming accounting. Do not use stale Bf telemetry as a
  substitute for acknowledgements or assume every firmware has the same buffer.

## Execution plan and acceptance criteria

1. Extract ConnectionPreferences, migrate the existing keys (including
   openserial), unify startup/manual connection, and delete SerialFrame. Test old
   configuration import, both transports, failed connects, autoconnect and shutdown.
2. Extract MachineState and diagnostic log; remove mat/DRO/state/control/terminal
   widget dependencies. Test telemetry, error recovery and Advanced Config/System.
3. Implement pure protocol parsers/discovery and transcript replay tests. Cover
   0.9, 1.0-era samples, 1.1, grblHAL compatibility modes, FluidNC, Mega extra axes,
   missing/partial/unknown fields, reordered WCO, WPos, report units, malformed
   banners and TCP with no banner. Never mark inferred support as hardware-tested.
4. Add capability-driven modern actions and Automatic selection. Verify failed
   discovery sends no movement, pressure, unlock or resume commands. Verify alarms,
   lost connections and mid-job resets stop the workflow consistently.
5. Extract selection/editing and tools configuration; remove the remaining hidden
   editor/CAM/ribbon/status shell. Preserve all document, undo, text, layers, cut
   preparation and header/footer tests. Assert retired widgets are not constructed.
6. Run full regressions, clean installed-package tests and small-screen QA. Validate
   an actual GRBL 1.1 plotter and grblHAL over both serial and TCP before declaring
   those profiles certified; add other families only with evidence.

Priority: connection and hidden mat panel first; protocol correctness/detection
next; editor/ribbon removal last. Two existing adapters are useful migration code,
but **one user-facing automatic GRBL connection with tested protocol capabilities**
is the intended product design.

## Implementation status — 2026-09-14

The hidden-GUI migration is now implemented. Removed source modules:
`ControlPage`, `EditorPage`, `FilePage`, `TerminalPage`, `ToolsPage`, `CNCList`,
`CNCRibbon` and `Ribbon`. Removed the old mat sensor/settings views, manual legacy
compensation entry point and hidden canvas toolbar. No replacement invisible
widgets are constructed.

Live responsibilities now belong to:

- `PlotterSession.ConnectionPreferences`: serial/TCP preferences and autoconnect;
  reads existing connection keys, defaults firmware mode to Automatic, removes
  retired layout keys when saving.
- `PlotterSession.DiagnosticLog`: bounded controller history used by System.
- `PlotterSelection.DocumentEditor`: document selection, clipboard and editing
  operations using existing document undo and the layer service.
- `PlotterTools`: configuration/plugin data separated from CAM presentation.
- `MachineSnapshot` and the existing machine service: coordinates, readiness and
  manual actions, with firmware capability checks rather than hidden widgets.

The implemented firmware scope follows the approved three families: GRBL 0.8/0.9,
GRBL 1.0/1.1 and grblHAL. FluidNC/ESP32-specific profiles are not part of this
implementation. The GRBL0/GRBL1 filenames remain small compatibility entry points;
both use shared report parsing and a per-connection Firmware capability model.

Automatic detection uses banners and build information, handles TCP without a
banner, and treats GRBL 1.0 jogging/overrides conservatively. Manual profiles remain
available for troubleshooting and are labelled as manual when used without identity
evidence. Reports support legacy commas and modern pipes, WPos/MPos/WCO in either
order, inches-to-mm conversion for cutting coordinates, and additional axes.
Incomplete byte-stream lines are retained across read timeouts; invalid reports
do not partially update position state.

grblHAL build identity, NEWOPT real-time capabilities and ENUMS descriptions are
consumed when advertised. Advanced settings use reported setting names/ranges/types;
controller-provided error descriptions accompany the existing friendly recovery
messages. GRBL 0.8 setting annotations override the 1.1 fallback labels.

Connection no longer explicitly toggles DTR, clears received banners, resumes,
resets or runs an initialization macro. The obsolete Connection initialization
field has been removed; job startup/header/footer remain available. A serial
adapter/board may still reset as a hardware effect of opening its port.
Automatic discovery sends information/status queries only while Idle and not
owned by an MPG. If identification cannot complete (including a locked controller
with no banner), the UI remains blocked and offers manual connection profiles or
explicit recovery through Advanced settings. No automatic unlock is attempted.

Validation: all 188 tests pass, including regression tests for the modern GUI, native projects and
recovery, source-file absence, selection/clipboard/undo, firmware transcripts,
fragmented input and a real local TCP sender handshake with simulated grblHAL.
Clean wheel verification passed, checking both absent retired modules and included
new services. The installed wheel also opened the modern connection dialog under
a virtual display. Physical controller/plotter certification remains outstanding; simulated
protocol tests do not establish driver-specific pressure or sensor calibration.

## Follow-up architecture cleanup

The subsequent cleanup removes the plugin registry and fake-editor compensation
bridge. Current adapters are in `PlotterAdapters`; blade geometry is in
`PlotterKnife` and document conversion in `PlotterCompensation`/`PlotterPath`.
The old local command shell, diagnostics-workspace branch and error-report GUI
are removed. See [current architecture and remaining scope](plotter-architecture.md)
for completed changes and the broader removals rejected by automatic review.
