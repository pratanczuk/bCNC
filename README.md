# Foil Studio — Classic

Design → Prepare → Cut for foil and vinyl plotters. This is the maintained
Python/Tk application, derived from [bCNC](https://github.com/vlachoudis/bCNC)
by Vasilis Vlachoudis and contributors. Original copyright and license notices remain.

| Branch | Status | Releases |
| --- | --- | --- |
| `main` | Working Python/Tk application | `classic-v*` |
| [`next`](https://github.com/pratanczuk/FoilStudio/tree/next) | Flutter/Rust development | `next-v*` prereleases |

[Downloads](https://github.com/pratanczuk/FoilStudio/releases) ·
[Builds](https://github.com/pratanczuk/FoilStudio/actions) ·
[Workflow guide](docs/foil-studio-workflow.md) ·
[Development and releases](docs/development.md)

![Foil Studio](docs/screenshots/foil-studio-design.png)

## Run from source

Use Python 3.12 for wheel builds. On Ubuntu install `python3-tk`, then in a virtual environment:

```sh
python -m pip install -c packaging/constraints.txt .
foil-studio
```

The internal package remains `bCNC`; `bCNC` is retained as a command alias.
See [packaging](packaging/README.md) for OS dependencies and installers.
Use a supported machine profile; automatic material loading requires compatible firmware.

## Licensing and release status

See [LICENSE.md](LICENSE.md) and the [existing license review](docs/foil-studio-license-review.md).
Classic binary releases remain drafts until the recorded dependency/provenance questions
are resolved. A green CI run is not physical-cutting validation or license clearance.
