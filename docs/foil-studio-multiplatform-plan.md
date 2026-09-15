# Five-platform migration recommendation

Analysis dated 2026-09-15. Target: Linux, Windows, macOS, Android and iOS, with the same projects, materials, tools and guided cutting workflow.

## Recommendation

Use **Flutter for a new adaptive interface**, with a separately owned plotter service. Retain the tested Python planning/protocol code initially on desktop and on an optional local network gateway. Make mobile a client of that gateway first. This is the lowest-risk route I recommend for this repository; it is an architectural judgment, not a measured benchmark.

Flutter supports all five targets and native integration. Its rendering model fits a zoomable mat, handles, touch gestures and a consistent interface, but the vector editor, text layout, accessibility and native adapters still require implementation. iOS builds require macOS tooling. [Supported platforms](https://docs.flutter.dev/reference/supported-platforms), [platform integration](https://docs.flutter.dev/platform-integration), [architecture](https://docs.flutter.dev/resources/architectural-overview).

**If mobile must work without any gateway**, this becomes a larger second phase: port the headless planner and execution engine to a mobile-compatible library (evaluate Rust with a stable C ABI), or prove an embedded Python/native-dependency build on every target. Do not promise that the existing NumPy/OpenCV/Shapely desktop stack can simply be packaged unchanged for iOS.

## Options compared

| Approach | Fit for this app | Cost / limiting factor |
| --- | --- | --- |
| Flutter + headless service | Recommended for equal desktop/mobile priority; one adaptive drawing UI | New Dart UI; service contract; native file/font/transport adapters |
| Qt Quick/QML + C++/Python | Strong alternative if desktop and Python reuse dominate | Mobile packaging of Python/native modules needs a proof of concept; module licensing must be checked; QML is still a UI rewrite |
| Tauri 2 + web editor + Rust | Strong alternative for a team experienced with TypeScript/SVG | WebView differences, native transport plugins and mobile execution ownership; desktop Python process approach cannot be assumed portable |
| Browser/PWA + local gateway | Fastest universal companion interface | Requires gateway for dependable hardware access; unsuitable as universal direct USB/raw-TCP plotter controller |
| Keep Tk and package separately | Useful interim desktop release | Does not solve the requested mobile/touch interface |

Qt supports the target desktop/mobile families, with licensing varying by module. Tauri supports desktop and mobile with web UI and native integration. Web Serial has limited browser availability. [Qt platforms](https://doc.qt.io/qt-6/supported-platforms.html), [Qt licensing](https://doc.qt.io/qt-6/licensing.html), [Tauri architecture](https://v2.tauri.app/start/), [Web Serial](https://developer.mozilla.org/en-US/docs/Web/API/Web_Serial_API).

## Connection and job ownership

| Target | Initial supported route | Additional work |
| --- | --- | --- |
| Linux / Windows / macOS | Local service → serial or `socket://host:port` | Package native dependencies; serial permissions/drivers; signing on Windows/macOS |
| Android | LAN gateway → plotter | Optional direct USB host adapter with permissions and chipset support; device must support USB host |
| iOS / iPadOS | LAN gateway → plotter | Local-network permissions/discovery; no promise of generic desktop-style USB serial support |

Android provides a USB host API but applications need device access permission and compatible hardware. Apple's External Accessory framework targets supported MFi accessories; it is not a general replacement for pyserial. [Android USB host](https://developer.android.com/develop/connectivity/usb/host), [Apple accessories](https://developer.apple.com/accessories/).

A TCP socket is possible in a native application, but it does not solve lifecycle reliability. A mobile UI must not be the sole source of a long GRBL command stream: background services are constrained on iOS. The gateway should receive and validate the complete immutable job, own acknowledgements, pause/stop and tool-exchange state, and report progress when the client reconnects. Existing firmware TCP streaming alone is not evidence that it can spool an entire job autonomously. [Apple background-service rules](https://developer.apple.com/app-store/review/guidelines/).

Define explicit disconnect policy: gateway continues only an already confirmed pass under its local safety policy; at a tool change it stays waiting. It never guesses that a tool has been fitted or restarts a failed pass. A physical stop remains available even when the phone is disconnected. Authenticate paired clients, permit one job owner, reject duplicate start commands, and keep raw GRBL sockets off the public internet.

## Boundaries to establish in this code

1. **Document domain:** paths, objects, layers, text source, tool/material snapshots, undo and versioned `.foil` serialization. Remove dependencies on Tk selection/widgets from mutations. Store units explicitly in mm; preserve imported paths and font identity.
2. **Planning:** `PlotterPlanning`, `PlotterProcesses`, `PlotterCompilation`, `PlotterKnife`, `PlotterSequence`. Return immutable plans, bounds and structured errors. Remove remaining reliance on process-global `CNC.vars` through explicit inputs.
3. **Machine service:** `PlotterMachine`, `PlotterMat`, `PlotterProtocol`, `Sender`. Own transport, status, homing, acknowledgements and job lifecycle independently of the Tk event loop. `bmain._monitorSerial` still participates in lifecycle orchestration and must move here.
4. **Adapters:** serial/TCP, settings, filesystem/font enumeration, image tracing and geometry libraries. `PlotterAdapters` already gives a useful starting seam; isolate native dependencies behind interfaces.
5. **Presentation:** Flutter owns responsive layout and interaction; consume structured events rather than parsing status strings. Keep Design → Prepare → Cut on desktop/tablet; use bottom navigation and focused panels on phones.

Use a versioned local API: project revision, compiled-job hash, firmware capabilities, machine status sequence, job ID, stage ID and error code/recovery actions. Commands include start/pause/stop/load/unload/confirm-tool; confirmations reference the exact waiting stage and expire on reset. A snapshot plus ordered events allows reconnect without duplicating motion. No arbitrary Python evaluation in the API.

## Delivery gates

1. Resolve the [license questions](foil-studio-license-review.md), define minimum OS/device versions, and decide gateway-required versus standalone mobile. Build a small Flutter editor/transport spike before a full rewrite.
2. Extract the service from Tk while keeping the present UI usable. Acceptance: existing fixtures produce equivalent plans; mocked alarms, reset, disconnect, mat sensor changes and pen/knife exchange tests pass without Tk.
3. Prove a vertical slice: open an existing `.foil`, edit an object, preview exact bounds, submit a simulated two-tool job and reconnect while waiting for a tool. Test touch selection, font fallback and 10,000-path performance on a real midrange tablet.
4. Ship desktop preview builds with read/write project compatibility and offline simulation. Then validate physical pen-before-knife jobs, X-only homing and origin preservation on supported firmware.
5. Add gateway clients on Android/iOS. Acceptance: lock phone, background/kill app, lose Wi-Fi, reconnect; no duplicated motion, lost tool confirmation, or automatic resume after alarm.
6. Only then evaluate standalone mobile execution if it is required. Establish CI for each OS/architecture, signed packages, per-artifact notices, upgrade/rollback tests and project migrations.

This proposal does not replace the working application or start a speculative rewrite. It identifies what can be reused and the proof required before choosing the final execution runtime.
