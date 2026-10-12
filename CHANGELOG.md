# Changelog

## V0.2 - 2026-10-12

Public tag: `v0.2`. This release includes the previously unpublished internal
v1.2 batch-export work. The existing v0.1 release is unchanged.

### Highlights / 更新摘要

- Batch ODB Field Outputs, including discovered components and invariants;
  batch current/first/last/every-N/specified Frames within one Step.
- Compact/Standard dialog sizing, persistent preview, and a pre-export plan.
- Faster metadata-only planning and bounded Frame metadata reuse; native
  Abaqus contour/render time remains model dependent.
- Fix the Abaqus 2021 Unicode field-selector error, initial dialog height,
  and false contour-route errors when contour controls are disabled.
- Add refreshed illustrated Word instructions, bilingual release notes,
  installation instructions, an installable ZIP and SHA-256 checksums.
- 新增动态场变量及分量/不变量选择、多帧静态批量出图、导出前计划确认表；
  改进紧凑界面和元数据读取效率，修复场变量选择器及非等值线导出问题。
- 本轮仅统一发布版本标识及整理文档，不额外修改已验证的功能逻辑。

### Fixes and performance details

- Encode the JSON field-catalog note before passing it to the Abaqus 2021
  FXLabel widget (Python 2 Unicode previously raised `TypeError: not a string`
  and prevented the selector from opening). Do not overwrite selector-creation
  errors with the normal selected-field count.
- Add ODB-discovered component/invariant rows to the Field Output selector and
  include each chosen subitem in its filename and native primary-variable
  refinement. Read the catalog through the existing kernel command route.
- Generate the export plan without loading every FieldOutput; validate all
  requested outputs before the actual export. Preview checks only the first
  combination that it renders.
- Reuse validated per-Frame output positions/refinements within the command
  instead of reloading Frames when applying the same batch to canvas panels.
- Restore primary-variable selection from the Abaqus 2021 snapshot tuple with
  the original ODB-based route as fallback; skip unchanged Step/Frame restores.
- Keep a bounded eight-Frame metadata cache, keyed by ODB path and source
  file size/mtime; field catalog requests explicitly refresh metadata. No field
  values, mesh data or native Frame objects are retained in the cache.
- Match Combined canvas plan filenames to the actual Combined export token.
- Make the initial ODB Field Output selector scan only the selected Step's
  current Frame; add an explicit Scan all Frames action for sparse outputs
  while retaining full per-target-Frame validation during export.
- Avoid repeating the first viewport's FieldOutput validation while building an
  export plan or starting an export; additional target viewports remain checked.
- Reuse each target Frame's FieldOutput key list while resolving multiple
  selected variables, without changing the per-Frame availability check.
- Treat contour settings as a no-op when the form has disabled them because the
  target is not an active ODB contour plot, avoiding a false contour-route
  failure on otherwise valid exports.
- Keep the compact dialog's native content height instead of forcing a smaller
  initial height that can make the lower controls appear collapsed.
- Add Compact/Standard UI density presets, reduce the preview pane's fixed
  minimum footprint, and wrap long explanatory labels so the dialog can be
  resized more usefully on a single screen.
- Add a read-only pre-export plan table listing every resolved Field Output,
  Step, Frame, viewport/view, and output filename before any export command is
  issued. No post-export CSV is generated.
- Route export-plan resolution through the Abaqus kernel command instead of
  importing the kernel module from the GUI process.
- Remove the optional Tight layout control and its temporary viewport-geometry
  mutation; Combined canvas continues to use the existing viewport layout.

### Batch export additions (formerly internal v1.2)

- Replace the five fixed Field Output checkboxes with an ODB-aware selector
  that scans the selected Step and supports extended mouse range selection.
- Reduce the dialog's fixed preview pane and thumbnail dimensions to make the
  main window's minimum footprint smaller; keep the existing resize decoration.
- Select multiple available ODB Field Outputs and export each with the same
  view, display, background, annotation, resolution, and format settings.
- Select one Step and export the current, first, last, every-N, or specified
  0-based Frame indices.
- Add `{field}`, `{step}`, and `{frame}` naming-template values, with safe
  automatic insertion for batch dimensions when the legacy template omits
  them.
- Preserve the original ODB Step/Frame and primary-variable state after each
  batch export and after Preview > Reset.
- Keep the in-dialog preview static and representative: it renders the first
  field/frame combination; Export writes the complete batch.

## v0.1 - 2026-09-14

Initial public release of Scientific Figure Exporter for the verified target environment: Windows with Abaqus/CAE 2021 and its embedded Python 2.7.

- View selection, viewport scope, separate-file and combined-canvas output.
- Display and supported ODB contour styling, annotation toggles, and viewport backgrounds.
- In-dialog rendered PNG preview, including automatic preview refresh.
- PNG, TIFF, SVG, and Windows JPG export, plus an installer and Chinese user guide.
- Bilingual English/Chinese repository documentation.
