# License inventory and release questions

Reviewed 2026-09-15. This is a source and installed Linux dependency audit, not a legal clearance or an inventory of future Windows/macOS/mobile binaries. Exact installed versions and notice paths are recorded in [license-inventory-linux.json](license-inventory-linux.json). Requirements use ranges, so release artifacts need their own locked inventory.

## Code and dependencies actually used

| Component | License evidence | Use / qualification |
| --- | --- | --- |
| bCNC / Foil Studio application | `LICENSE.md`: GPL version 2; `setup.py`: GPLv2 | Main application and inherited geometry. Do not assume every inherited file permits GPLv3 merely because the license text contains a sample “or later” notice. |
| `lib/svgcode.py` | Explicit GPLv2+ file header | SVG import adapter |
| CERN/Vlachoudis geometry, DXF, undo utilities | Copyright/disclaimer notices in `lib/bpath.py`, `bmath.py`, `dxf.py`, `undo.py`, `log.py`, `Unicode.py` | Several files refer to external flair documentation or have no complete standalone license grant. Retain notices; verify provenance before changing licensing. |
| `lib/spline.py` | David F. Rogers copyright notices on algorithms | Verify the original permission/provenance; the notices alone do not establish a separate permissive license. |
| pyserial 3.5 | BSD (project uses BSD-3-Clause) | Serial and `socket://` transports |
| svgelements 1.9.6 | MIT | Active SVG importer; added missing entry to requirements.txt to match setup.py |
| fonttools 4.63.0 | MIT plus `LICENSE.external` | Font outlines / text insertion; external notice file includes OFL-1.1 test fonts; check whether those test assets are actually shipped |
| Pillow 12.3.0 | MIT-CMU | Image loading and preview; bundled image libraries have additional notices |
| NumPy 2.5.1 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 metadata | Array operations; wheel additionally includes OpenBLAS/LAPACK BSD notices and GCC runtime GPL-3.0-or-later WITH GCC-exception-3.1 and libquadmath LGPL-2.1-or-later. Preserve the exception, not just “GPL”. |
| OpenCV Python 5.0.0.93 | Apache-2.0 metadata; `cv2/LICENSE.txt`, `LICENSE-3RD-PARTY.txt` | Image tracing. Its bundled notices identify FFmpeg under LGPL-2.1, Qt 5 under LGPL-3.0 in non-headless Linux/macOS wheels, libvpx BSD, and further codec/library notices. Inventory the chosen wheel, not just the Python wrapper. |
| Shapely 2.1.2 | BSD-3-Clause; bundled GEOS LGPL-2.1 | Boolean operations and offsets. GEOS has its own license and distribution obligations. |
| Python / Tcl / Tk | PSF and Tcl/Tk license families | Runtime and current UI; include runtime notices when bundled. Not pinned by application requirements. |
| PyObjC packages (macOS-only setup dependencies) | MIT upstream | Declared by setup.py; not installed or verified in this Linux environment. No direct Quartz/PyObjC import found in current application. Reassess these packaging dependencies in a macOS build. |
| Fonts selected by users | Font-specific | FontTools licensing does not cover input fonts or permission to redistribute them. No single license can be assigned to all system fonts. |
| Icons / screenshots / artwork | Repository provenance and any embedded notices | No comprehensive per-asset attribution manifest found; do not presume every asset is MIT. |

`LICENSE.MIT` names the previously vendored meshcut and svg.path code; `LICENSE.BSD3` names numpy-stl and python-utils. Those vendored directories are absent from the current tree. These notices are historical evidence, not proof those components are still runtime dependencies. They have been retained rather than deleting attribution during cleanup.

The LGPL-3.0 Qt component is another reason to inspect the OpenCV binary choice against GPLv2-only code. This application does not use OpenCV windows; evaluating a headless wheel could remove the incidental Qt GUI dependency, but does not resolve OpenCV's Apache-2.0 compatibility question.

## Decisions needed before a release

1. **Resolve GPL version scope and OpenCV compatibility.** Apache-2.0 is compatible with GPLv3, not GPLv2-only. The repository-wide “GPLv2” declaration is insufficient evidence that we can upgrade every file. Verify grants from the relevant authors; if GPLv2-only code remains, assess a compatible tracing replacement. Do not simply change setup.py to GPLv3. [Apache's compatibility explanation](https://www.apache.org/licenses/GPL-compatibility), [GNU compatibility guidance](https://www.gnu.org/licenses/license-compatibility.en.html).
2. Preserve license texts, copyright notices and corresponding-source provisions for distributed GPL code; inspect native LGPL library obligations for each binary build. [GPLv2 terms](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html).
3. Confirm the provenance of the inherited utility algorithms and artwork. Keep unresolved items visible rather than assigning guessed SPDX identifiers.
4. Generate a locked dependency graph, binary inventory and bundled notices for each target OS/architecture. The Linux JSON here is a reproducible starting point, not a complete transitive SBOM.
5. Review Apple distribution terms against the final licensing arrangement before committing to App Store delivery. A rewritten interface or separate process does not automatically remove obligations for copied or combined GPL-derived code. [GNU GPL FAQ](https://www.gnu.org/licenses/gpl-faq.html), [Apple review guidelines](https://developer.apple.com/app-store/review/guidelines/).

No project license was changed by this review.
