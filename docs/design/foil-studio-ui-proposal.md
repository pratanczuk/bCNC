# Foil Studio — adaptive UI proposal

Review date: 15 September 2026. Status: design proposal, not an implemented redesign.

## Direction

Keep **Design → Prepare → Cut** as the product's backbone. Build a calm, precise workspace around the mat, with contextual tools, readable values and dependable machine feedback. Retain the existing teal identity. Modernization should reduce decisions and window switching, not merely change button corners.

Desktop supports sustained precision editing. Tablet supports the same workflow with fewer simultaneous panels. Phone supports the entire workflow through focused pages, including numeric editing and node selection; it must never be a shrunken desktop. Complex artwork is more comfortable on larger displays, but functionality must remain discoverable on phones.

## Review basis and limits

- Visually reviewed the 40 `foil-studio-*.png` repository screenshots, including editor tools, library, connection, settings, tool exchange and errors. Examined six principal screenshots at full size and the remaining screens in overview sheets.
- Cross-checked current UI construction in `PlotterWorkflow.py`, `PlotterDesign.py`, `PlotterStudio.py`, `PlotterLayersUI.py`, `PlotterLibraryUI.py`, `PlotterTrace.py`, `PlotterSettings.py`, `PlotterAdvanced.py`, `PlotterErrorDialog.py` and `PlotterTheme.py`.
- Screenshots include earlier iterations: for example, the Design screenshot says Save while current source says Save project and contains more tools. Source takes precedence for capability and naming. This is a source-and-screenshot review, not a live usability test or measured accessibility audit.
- Aligns with the repository's [five-platform proposal](../foil-studio-multiplatform-plan.md). The design is framework-independent; no runtime selection or rewrite is authorized by this document.
- The companion visual is an interactive concept with sample data. It illustrates layouts and selected transitions; it does not implement geometry, persistence, hardware communication or every detailed editor.

## Findings, in priority order

| Priority | Evidence in current UI | User consequence | Proposed correction |
| --- | --- | --- | --- |
| P1 | `PlotterWorkflow` fixes the sidebar at 330 px; Layers minimum is 880×620, Trace 820×680, Library 800×630 | Panels consume a small screen; dialogs cannot reflow to a phone | Content-based adaptive layouts; replace floating tool windows with inspectors or focused pages |
| P1 | Design mixes project management, creation, selection, layers and finishing tools in one column | Users scan a long command menu for every operation | Project menu, compact creation tools, layers panel and selection inspector |
| P1 | Multi-selection instruction is Ctrl / Shift; canvas tools read Move design and Select | Touch users lack an explicit selection route; moving the view and moving artwork are easy to confuse | Select / Pan modes, Select multiple toggle, object list, visible selection count and numeric transform controls |
| P1 | Advanced → Configuration → Application / Controller nests three levels of tabs; Machine control lives inside settings | Users must navigate configuration to position the machine; staged edits and immediate actions share a frame | Independent Machine workspace; flat Settings categories; explicit write-to-controller action |
| P1 | Job review and tool-change instructions occupy the same scrolling sidebar as setup | Readiness and the next physical action compete for space | Dedicated review, running, tool-change and fault presentations; persistent Pause / Stop region |
| P2 | Native Tk entries, lists, checkboxes and notebooks mix with flat custom buttons; colors also appear outside PlotterTheme | Control states, spacing and density vary between screens | Shared component recipes and semantic tokens, including focus, disabled, pending and error states |
| P2 | Arrange applies individual operations immediately; most preview tools stage changes until Apply | Similar-looking editors imply different commit behavior | Standard preview → Apply / Cancel for geometry tools, one undo record per application; inline transforms commit on Enter or deliberate field completion |
| P2 | Blue artwork on a dense dotted mat; selection and processing colors vary between previews | Visual meaning is inconsistent and thin outlines are difficult to acquire on touch | Adaptive grid, consistent geometry states, enlarged invisible hit regions, selection through Layers |
| P2 | Recovery is mixed into Projects; library profile saving and applying to layers are separate actions | Users may mistake a library edit for a change to the current job | Named save states and an explicit Use on selected layer action with before/after settings |
| Keep | Preview-first tools, units next to values, human-readable faults, separate pressure/blade settings and command-acknowledgement wording | These already improve comprehension | Preserve and standardize these patterns |

## Information architecture

**Workspace:** Design, Prepare, Cut. These are destinations with an ordered task flow, not completion checkboxes. Navigation must not execute machine actions.

**Project menu:** New, Open, recent projects, Save project, Save as, Import artwork, Export prepared G-code, recovery copies.

**Utilities:** Materials & tools, Machine, Settings, Help. Desktop header menu or labeled rail; tablet menu; phone More page. Returning from a utility restores the previous selection, canvas view and draft.

**Design inspector:** Selection / Layers. Creation opens Text, Shape or Trace. More editing tools contains Combine, Offset, Layout, Contours, Weeding lines and Split outlines. Frequently used tools can be promoted later based on observation, not speculation.

**Settings:** Appearance & language; Mat & planning defaults; Job commands; Controller settings; Support & diagnostics. Current material/tool setup belongs to Prepare and the layer inspector. Machine motion belongs to Machine.

## Adaptive layouts

Breakpoints below are initial logical-pixel layout rules, to validate with real content and text scaling; they are not device detection.

| Available width | Design | Prepare / Cut | Secondary editors |
| --- | --- | --- | --- |
| Expanded, ≥1200 | 56 px tool rail, optional 240 px Layers panel, flexible canvas, 320 px inspector | Preview and 360–400 px setup/status column | Anchored inspector with live canvas; large Trace editor can use a workspace page |
| Medium, 840–1199 | Tool rail, canvas and one 300–320 px panel; Layers replaces inspector | Preview beside setup; critical controls outside scrolling content | One side panel at a time; preserve a useful preview area |
| Compact, 600–839 | Canvas with compact toolbar; one expandable inspector below or overlaying a bounded portion | Stacked summary and preview; ordered setup sections | Full-width sheet/page with Back and Apply; no stacked sheets |
| Phone, 320–599 | Compact project header; canvas; contextual action row; expandable inspector; bottom Design / Prepare / Cut navigation | Preparation is a linear form; Cut prioritizes job status, current tool and controls above expandable preview | Dedicated page, preview above fields, stable Apply area clear of keyboard and safe-area insets |

- At short heights (including 1024×600 landscape tablets), reduce header whitespace, let forms scroll, and keep the action bar visible. Do not shrink type or force whole-screen scrolling around Stop.
- Use 16 px outer spacing on phones, 24 px on desktop; 8 px gaps between controls. Avoid horizontal form scrolling. Convert tables to labeled rows on compact screens.
- A full-screen keyboard must not cover the edited field, error, Cancel or Apply. Restore canvas framing and selection after rotation.
- Touch targets remain large on a wide touchscreen. Input modality changes target size independently of width.
- Back exits a tool before leaving its workspace. Dirty staged edits use Discard changes / Keep editing; saveable project changes use Save / Discard / Cancel.

## Visual system

**Character:** precise, quiet, practical. Neutral surfaces, a restrained teal accent, thin dividers, clear typography and modest corners. Avoid heavy shadows, decorative gradients and a separate card around every row.

| Token | Light | Dark | Purpose |
| --- | --- | --- | --- |
| Workspace | `#F3F5F6` | `#151B20` | Canvas surround and app background |
| Surface | `#FFFFFF` | `#202930` | Panels, sheets and menus |
| Text | `#20313C` | `#EDF2F4` | Labels and essential values |
| Secondary text | `#526571` | `#B3C0C9` | Supporting text |
| Primary action | `#176B5B` | `#85D7C0` | One main action per task region; use white / dark text respectively |
| Selected surface | `#E2F0EA` | `#25483F` | Selected row or navigation destination |
| Divider | `#D7DFE3` | `#46545F` | Structural separation; not the sole cue for input boundaries |
| Input border | `#7A8993` | `#8597A3` | Discoverable field boundary |
| Focus | `#245FC0` | `#A7C8FF` | 2 px focus ring, 2 px offset |
| Error / stop | `#B42318` | `#FFB4AB` | Fault text or action; text and icon accompany color |
| Warning | `#845500` | `#F3CB7C` | Needs attention; not a disabled state |

Use platform system sans-serif fonts with one tested fallback. Start at 16/24 body text, 14/20 secondary labels, 20/28 section headings and 24/32 page headings. Use regular and medium weights; tabular numerals for dimensions and machine coordinates. Font outline rendering is a separate document concern and must not silently substitute artwork fonts.

Spacing scale: 4, 8, 12, 16, 24, 32. Corners: 8 px controls, 12 px panels/sheets. Default control height: 44 px; touch-first fields/buttons: 48 px; running-job actions: 56 px. Fine-pointer dense tables may use 36 px rows, with a comfortable-density setting and touch overrides. Icons: one consistent outlined family, normally 20 px, paired with labels for less familiar actions.

Start with system-following light/dark appearance. Keep the material preview light by default when that reflects the material, even in dark mode; ensure geometry and selection remain readable on the chosen mat surface. Prototype colors and sizes are starting values, not a claim of completed accessibility certification.

## Shared control contracts

| Control | Standard behavior |
| --- | --- |
| Primary button | Filled teal, concrete verb: Add text, Apply changes, Review job. One dominant action in each active region |
| Secondary / quiet action | Bordered for common alternatives; text/icon for supporting actions. Delete artwork is ordinary contextual action with Undo; Stop job gets dedicated red treatment |
| Button states | Default, hover, pressed, keyboard focus, disabled with visible reason, and pending with retained label. Prevent repeat submission while pending |
| Numeric field | Label above, unit beside value, locale-aware decimal input, optional stepper, range validation beneath. Preserve invalid text for correction; no silent clamping or unit switching |
| Pressure | Display `500 / 1000 PWM`; helper: Machine scale, not grams. Slider may supplement an exact field; changing it stages a setting and never directly actuates the blade |
| Toggle / checkbox | Toggle for immediate UI preferences; checkbox for staged options and explicit physical confirmations. The full label row is tappable. No prechecked mat/tool confirmation |
| Select / segmented control | Segments for 2–4 mutually exclusive choices; searchable list for fonts, materials and tools. Long names wrap rather than truncate their distinguishing suffix |
| Layers / objects | Expandable rows, selected state and selection count; distinguish Included in job from Hidden in editor if visibility is added. Move up/down alternative to drag reorder |
| Preview editor | Title, target selection, preview, fields, dimensions/error, Cancel / Apply. Applying is one undoable transaction; Cancel leaves source unchanged |
| Dialog | Reserve modal dialogs for blocking choices. Restore focus to the trigger. Escape cancels only staged edits; it never silently stops or resumes a job |
| Feedback | Inline field validation; short nonblocking save/undo messages; persistent banner for connectivity; dedicated fault presentation for blocked machine execution |
| Progress | Show phase and current pass. Label command-based progress honestly. Never display fabricated remaining time or infer physical completion solely from 100% acknowledgements |
| Save | Distinguish Unsaved changes, Saving, Saved, Save failed. Recovery copy does not mean the user-selected file was saved |
| Help | Short helper near the decision; longer guidance under Learn more. Technical errors and logs live behind Details, with copy/export support |

### Canvas and precision interaction

- One-finger tap selects; dragging a selected object moves it in Select mode. Pan mode moves the view. Two-finger pan/pinch operates the view without modifying objects.
- Select multiple is an explicit mode with Done and a count; desktop retains Shift/Ctrl conventions. Empty-space tap clears selection. A second tap on overlapping geometry offers an object chooser.
- No selection means transforms are unavailable with a Select objects hint. Provide explicit Select all; remove the current implicit whole-design fallback for transforms.
- Resize handles have approximately 44 px effective hit regions on touch. When handles would overlap, show fewer handles plus numeric Width / Height / Rotation controls rather than oversized overlapping hit areas.
- Keep aspect lock next to Width / Height, showing locked/unlocked text or accessible state. Show X/Y position and dimensions in mm; label mat origin with a persistent marker.
- Zoom-dependent grid, stronger major intervals and a visible Grid option. Preview cut path, travel and selected geometry with different line patterns and a legend; selection color must not overwrite tool identity without another cue.
- Long press is a shortcut, never the only route. Undo/Redo, Fit mat, zoom buttons, layer selection, numeric positioning and node next/previous controls provide alternatives to gestures.

## Every screen and editor

All rows use the adaptive patterns above. “New” means a proposed presentation or capability, not current implementation.

| Screen / existing entry | Proposed content and main action | Desktop / tablet | Phone |
| --- | --- | --- | --- |
| Projects & recovery | Recent projects with filename, thumbnail, modified state; New / Open. Recovery copies identify source and timestamp; Recover as copy | Project page or panel; preview selected item | Full page; list → project detail; native file picker |
| Empty Design / import | Empty mat with Import artwork, Text, Shape; show supported formats at picker. Oversized import offers explicit Scale to fit or Keep size and fix | Same editor shell as populated state | Compact canvas and Add menu; no empty inspector |
| Design / selection | Mat, object count, name, position, size, aspect lock, rotation, align, duplicate, delete, Undo / Redo | Contextual inspector; optional Layers | Canvas plus expandable selection panel; one section at a time |
| Text & font | Wording, font search/style, size in mm, real outline dimensions, unavailable-font state; Add text / Update text | Inspector or wide preview page | Full page; text input first; preview survives keyboard dismissal |
| Text spacing & curve | Letter/line spacing, alignment and curve settings from current editor; explain size versus outline bounds | Secondary section in Text editor | Same page accordion; exact numeric controls |
| Shapes | Shape picker; relevant dimensions, star points as applicable; live outline; Add shape | Small inspector | Focused page with preview and relevant fields only |
| Trace Basics / Refine | Image chooser, original/outline comparison, size, threshold; advanced smoothing/speck/method options; Add to mat | Wide preview with side controls | Preview above collapsible controls; explicit Original / Outline switch |
| Arrange | Width/height, aspect lock, X/Y, rotation, flip, alignment target; apply transforms consistently | Primary selection inspector | Numeric sections and labeled alignment grid |
| Combine | Union, subtract, intersect, exclude overlap, combine outlines; visible operand order, result preview; Apply | Inspector over unchanged mat context | Page with preview and operand reorder buttons |
| Split outlines | Explicit selected-object count and preview of result count; Apply | Selection action | More editing tools; undo feedback |
| Offset & weeding border | Mode, distance/margin, corner style, preview; Add outlines | Inspector | Focused editor; same field vocabulary |
| Layout & repeat | Alignment target, rows, columns, gaps, packing margin; copies count and fit check; Apply | Wide mat preview and inspector | Page with numeric layout controls and zoomable preview |
| Contours & nodes | Operation, contour, selected node, X/Y, previous/next node, large selection handles; Apply | Detailed canvas mode with inspector | Dedicated precision page; numeric movement and list selection are first-class |
| Weeding lines | Spacing, clearance, margin; show cuts and excluded areas; Add weed lines | Inspector and mat preview | Preview page; clear distinction from design outlines |
| Layers | Name/color, order, inclusion, operation, tool, material and passes; selection count | Docked tree with contextual layer properties | Full-height list → layer detail; no horizontally scrolling tree table |
| Objects in layer | Rename, move layer, passes, include/exclude, duplicate, delete, attach/detach; preserve undo | Same inspector, selected-object mode | Detail page; explicit Move up/down and Move to layer |
| Prepare overview | Three sections: Plotter, Layer setups, Mat & origin; Review job | Preview next to form; show blockers near footer | Ordered vertical sections with status summaries |
| Connect plotter | Separate USB and Network choices; port picker/refresh or host+port fields, firmware Automatic, remembered connection; Connect | Sheet opened from status or Prepare | Full page; gateway pairing route when available; hide unsupported transports with explanation |
| Material settings | Preset, speed, PWM pressure, passes; distinguish current job override from saved preset; Apply to layer/job | Prepare section or library picker | Focused form, no nested dialog |
| Blade / pen settings | Tool type; blade offset, overcut, compensation or pen properties; show incompatible setup before apply | Tool subsection tied to affected layer | Same conditional form; no disabled knife field wall for pens |
| Mat settings | Width/height, usable bounds, loading method and origin diagram; Apply mat setup | Prepare section / defaults in Settings | Focused page; explicit reconfirmation after geometry changes |
| Manual mat loading | Position instructions, Machine positioning, Set origin here, then Mat loaded and aligned confirmation | Prepare checklist with diagram | Linear steps; do not imply Unload causes motion in manual mode |
| Automatic mat loading | Capability-supported Load / Unload; loading, cancelling, failed states; sensor separate from alignment | Mat section with persistent Stop movement | Dedicated movement state with Stop movement always visible |
| Test cut / first-cut guide | Resumable Connect → Material & tool → Mat → Create test → Inspect result; protect existing work; Create test job | Guided panel; returns to ordinary Cut review | Step pages; creating test artwork never starts motion |
| Material library | Search/list, name, speed, PWM pressure, thickness reference, passes, compatibility, notes; Save preset / Use on layer | Master-detail workspace | List → detail; Save and Use remain distinct |
| Tool library | Type-specific fields, name, knife angle/offset/overcut or pen width/color, notes; Save tool | Same library components | Same list-detail pattern |
| Cut sequence preview | Exact prepared geometry, travel legend, ordered passes, inner-first option, selected contour index; Done | Canvas mode with ordered pass panel | Preview above pass list; no misleading simulated machine animation |
| Cut review | Project/setup snapshot, included layers, pass order, bounds, readiness; Start job | Preview plus concise review column | Status and checklist first, preview expandable, Start in action region |
| Running / paused | Current pass/tool, acknowledgements, machine execution state, Pause / Resume and Stop job | Persistent job strip across workspace destinations | Persistent job controls above bottom navigation; cannot be hidden by editor pages |
| Tool exchange | Previous pass complete, required next tool, keep mat unchanged, unchecked fitted/aligned confirmation; Continue with tool | Prominent panel replacing review controls | Dedicated task page; Continue gated, Stop job available |
| Completed / stopped | Distinguish physical completion, stopping, stopped and interrupted. Unload according to loading mode; Return to design | Cut result panel; retain design | Result page; re-run requires fresh readiness review |
| Machine control | Coordinates, step size, speed, directional jog, stop movement, home, set origin, release blade; connected machine identity | Dedicated utility workspace | Large tap-to-step pad; separate reset/unlock section; no gesture-only jogging |
| Job G-code | Header/footer with monospace editor, applies-to-current-job scope and opt-in new-project defaults; Save job commands | Settings category with ample editor width | Dedicated page with code fields and explicit scope |
| Application configuration | Planning dimensions, feeds and other existing fields grouped by meaning; Save defaults | Settings list-detail | Category list → form; show units and changed values |
| Controller configuration | Read settings, selected value, old/new comparison; Send to controller, read-back result | Separate category with immediate-write semantics | Detail page; no global Apply ambiguity |
| System / support | Language, proposed appearance/density, version, connection log, configuration, copy/export details | Flat settings category | Native-style settings list; readable selectable logs |
| Connection loss | Persistent Unknown machine state, last update, reconnect; retain job ID when service supports it | Banner plus job state | Dedicated status on Cut; cannot offer Resume from stale state |
| Alarm / emergency-stop state | Specific cause and machine inspection/recovery action; Details; no auto-resume | Fault panel that preserves machine controls | Fault page; actual physical-stop state clearly labeled |
| Internal / validation error | What failed, whether edits were applied, corrective action, Details | Inline for correctable inputs; dialog for blocked task | Same hierarchy, full-width readable copy |
| Unsaved / export / recovery conflict | Exact filename and consequences; Save / Discard / Cancel; overwrite explicit | Standard dialog | Standard sheet; native file selection where available |

## Machine-state interaction specification

| State | Primary action | Always available / restriction |
| --- | --- | --- |
| Disconnected | Connect plotter | Offline editing; Start disabled with reason |
| Connected, not ready | Fix first blocker | Direct links to material, tool or mat setup |
| Ready | Start job | Bind review to project revision and current setup; prevent duplicate start |
| Starting | Starting… | Pending indication; no second start |
| Running | Pause | Stop job available outside scrollable panels |
| Pause requested | Pausing… | Do not call machine Paused before acknowledgement; Stop remains available |
| Paused | Resume | Only when current authoritative machine state permits |
| Waiting for tool | Continue with named tool | Requires fresh tool confirmation; no prechecked checkbox; Stop available |
| Stopping | Stopping… | Do not report Stopped until confirmed |
| Link lost | Reconnect | Show state unknown, last-seen data clearly stale; no queued/replayed Start or Resume |
| Alarm | Review machine | Preserve fault detail; recovery never automatically resumes |
| Commands all acknowledged | Waiting for machine to finish | Completion still depends on execution/idle confirmation |
| Completed | Unload mat / removal instructions | Re-run returns to review and checks readiness again |

Stop job is an application command, not a physical emergency stop. Do not label it Emergency stop or imply it works across a broken connection. A rejected or unconfirmed stop must be visibly reported. Do not put a confirmation dialog in front of Pause or Stop. Reset/unlock/controller writes belong to explicit machine actions with consequences explained at the point of use.

Mobile reconnection requires the separately owned job service described in the architecture proposal. This UI must consume authoritative snapshots; a phone going to sleep must not fabricate a successful pause or finish. Job ownership and reconnect behavior are dependencies, not capabilities created by this visual proposal.

## Accessibility and acceptance

Use 48 px touch targets as our design target. WCAG 2.2 AA's minimum target criterion is 24×24 CSS px with exceptions; meeting that minimum alone would not make this editor comfortable on a tablet. [W3C target-size guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).

Target at least 4.5:1 text contrast for normal text and 3:1 for large text. Verify component/focus visibility separately against actual surfaces. Do not use color alone to distinguish selected, excluded, warning or completed. [W3C text contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).

Every drag-based operation needs a single-pointer alternative: numeric placement, Move up/down, Select all and node lists. [W3C dragging guidance](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html).

Before implementation acceptance:

1. Exercise every screen at 320, 390, 600, 768, 840, 1024, 1280 and 1440 px widths, including 1024×600 and phone landscape; no clipped labels or inaccessible footer actions.
2. Verify touch, keyboard, mouse and screen-reader flows; explicit focus order, selected state, field labels and error announcement. Test 200% text scaling and longer Polish labels.
3. Complete import → select multiple → resize → assign tools → prepare → review → simulated two-tool job on desktop, tablet and phone. No keyboard modifier or hover may be required.
4. Verify invalid values, no selection, missing fonts, oversized artwork, empty trace, save failure, missing connection, mat invalidation and changed tool settings.
5. Verify running, pause pending, paused, stop pending, stopped, tool exchange, link loss and alarm. Critical controls remain accessible at all sizes, and no stale state enables Start/Resume.
6. Confirm geometry tools apply one reversible transaction; Cancel preserves the document; library edits do not silently alter saved layer setups.
7. Test actual midrange tablet canvas performance with dense artwork. Measure interaction latency rather than infer it from a mockup.

## Delivery sequence

1. **Foundation:** approve navigation, vocabulary, state contracts and component tokens. Capture fresh screenshots of current source as a comparison baseline.
2. **Editor vertical slice:** adaptive shell + mat + Layers + selection inspector + Text. Prove precision and multi-selection on touch before porting the remaining editors.
3. **Prepare and job execution:** clear setup scope, connection, mat handling, review/running/exchange/fault states. Use simulated machine events first, then controlled hardware validation.
4. **Complete secondary screens:** all geometry tools, libraries, projects/recovery, flat Settings and Machine pages; shared components, no one-off styling.
5. **Device qualification:** keyboard/screen-reader/text scaling, short landscape tablet, phone keyboard, reconnect/lifecycle and dense-artwork testing.

The main design decision to validate first is the **single contextual panel**: does it let users find a tool and return to the mat faster while retaining precise control? Observe real first-cut and multi-layer tasks before expanding permanent navigation.

## Concept verification

The companion concept passed JavaScript syntax checking. Browser inspection covered the desktop editor, phone preparation and tablet running layout. The simulated flow was checked for disabled Start before mat confirmation, Prepare → Review → Start, Pause, disabled Continue before tool confirmation, and transition to the knife pass. These are concept checks, not validation of the production application. The inline presentation expands vertically to remain readable in conversation; fixed viewport action bars, virtual keyboard behavior, real gestures, file handling and the full device matrix remain implementation work.
