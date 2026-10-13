# Performance and Field Output subitems — 2026-10-11

This V0.2 performance note targets Windows + Abaqus/CAE 2021 + Python 2.7.
Measurements were collected during development on 2026-10-11.

## Observed timings

Measured in actual Abaqus/CAE 2021 noGUI on one local, read-only ODB of
180,318,784 bytes. These are individual wall-clock measurements, not a guarantee
for larger ODBs. GUI interaction/IPC overhead is excluded.

| Operation | Before this update | After this update |
| --- | ---: | ---: |
| Native PNG reference | 0.351 s | 0.303 s |
| Two-field plan, current Frame | 1.428 s | 0.018 s |
| Two-field plan, Every N | 1.244 s | 0.002 s |
| First Preview | 6.048 s | 1.729 s |
| Repeated Preview with metadata cached | not measured | 0.229 s |
| Two-field Export after Preview/Reset | 6.311 s | 0.928 s |
| Reset | 1.486 s | 0.001 s |

Preview uses a 240 x 180 thumbnail; the benchmark requests 320 x 240 final
images, Current view, separate-file output, and S/U. Native PNG uses Abaqus'
current image size. Mesh, GPU, field computation, multi-view canvas creation,
image dimensions, and first access to an uncached Frame can change these times.
The first metadata read remains dependent on the ODB. Repeated-preview and
post-preview export figures benefit from the bounded metadata cache.

## Changes

- Field catalog reads now run through the existing AFXGuiCommand kernel route,
  using a small JSON response. GUI code no longer walks ODB Frames or fields
  through kernelAccess to populate the selector.
- The selector includes available components/invariants, such as S11, S22,
  Mises, U1 and Magnitude. Filenames distinguish subitems. Native CAE 2021
  stress Mises was verified even for a surface tensor whose validInvariants
  metadata omitted MISES. Plain S uses that supported Mises default.
- Drag-selecting both S and S, Mises is de-duplicated. The equivalent U and
  U, Magnitude requests are also de-duplicated.
- Export-plan generation resolves filenames and Frame indices without reading
  every FieldOutput. Actual export still validates every selected field/subitem
  in every target Frame before writing images. An invalid field can therefore
  appear in the plan and is rejected when export is confirmed.
- Preview validates only the first field/Frame combination that it renders.
- Validated output-position/refinement descriptors are reused when applying
  batch settings. They do not hold native Frame or FieldOutput objects.
- The shared metadata cache holds at most eight Frames. Keys include the source
  path, file size and mtime; field-selector requests refresh the metadata. It
  retains no field values or mesh arrays. Explicit field selection refreshes
  are required after creating custom FieldOutputs in memory without changing
  the source file.
- Unchanged Step/Frame restoration is skipped. Primary-variable restoration
  first uses the saved CAE 2021 tuple; the previous ODB-based route remains a
  fallback. Native acceptance and exact tuple round-trips were tested.
- Combined export-plan filenames use the same Combined token as actual exports.

## Verification

Actual noGUI regression covers native component/invariant selection, S and U
component baseline restoration, Preview/Reset, eight images from four subitems
and two Frames, invalid-component rejection followed by successful export,
multi-view Combined canvas, temporary viewport removal, catalog-command JSON,
plan/actual Combined filenames, and the metadata-cache size bound. Generated
single and combined PNGs were visually inspected.

Python 2.7 syntax is compiled in the noGUI benchmark, including the GUI source
without importing abaqusGui into the kernel. These timings do not include GUI
click-through measurements or a performance benchmark on a larger ODB.

## Reproduce

From the repository root in PowerShell, with a licensed Abaqus installation:

```powershell
$env:SFE_BENCHMARK_ODB = 'D:\path\to\a\test.odb'
abaqus cae noGUI=diagnostics/performance_components.py
abaqus cae noGUI=diagnostics/components_regression.py
```

The component regression expects S11/S22 and U1/Magnitude and at least two
Frames. The source ODB is opened read-only. Generated images, timing JSON and
cProfile reports are in diagnostics/performance_output, which is gitignored.
The installer creates timestamped backups in the installation directory.

## Field-selector GUI follow-up

The first GUI integration had a Python 2 string-boundary bug: `json.load`
returns a Unicode catalog note, while the Abaqus 2021 native `FXLabel` requires
a byte string. A real GUI probe reproduced `TypeError: not a string`.
The selector now encodes the note with the existing `_afx_string` helper.
The summary count is updated before opening the selector, so a construction
error is no longer overwritten by `No field filter (keep current output)`.
This follow-up changes only the GUI source, not kernel or performance logic.

ABAQUS GUI TESTED: PASS for the repaired selector in a separate Abaqus/CAE
2021 session, opening a local 634,369,788-byte test ODB read-only. Clicking
Choose Field Outputs opened the native dialog; selecting U1/U2/U3 and clicking
Use Selected updated the main form to three selected outputs. Reopening the
selector worked; scrolling showed S, Mises and S11/S22/S33 component rows.
Screenshots are retained locally under diagnostics/performance_output as
field_selector_applied_gui.png, field_selector_reopened_gui.png and
field_selector_stress_gui.png. This is selector acceptance, not a new Preview
or Export performance measurement. Other open CAE sessions were left unchanged.
Reloading the installed GUI requires restarting Abaqus.
