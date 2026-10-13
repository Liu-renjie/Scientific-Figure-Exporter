# V0.2 validation scope 验证范围

Target: Windows + Abaqus/CAE 2021 + embedded Python 2.7 only.

## Evidence available for this release

- Actual CAE 2021 noGUI checks covered component/invariant refinement,
  four subitems across two Frames (eight output images), Preview/Reset,
  invalid-component rejection followed by a successful export, Combined canvas
  naming, state restoration and the eight-Frame metadata cache bound.
- Actual CAE 2021 GUI checks covered opening the repaired Field Output selector,
  selecting U1/U2/U3, applying three selected outputs, reopening the selector,
  and displaying stress invariant/component rows. This was performed in a
  separate session with a read-only ODB. It is not a full GUI timing benchmark.
- Additional manual testing of the release build reported no obvious regression;
  this is supplementary feedback, not an instrumented regression test.
- Release preparation changes the public version metadata and documentation,
  not the tested runtime functionality. Python 2.7 syntax and package contents
  are checked separately during packaging.

Small local timing measurements are recorded in
[the performance note](PERFORMANCE_UPDATE_20261011.md). They exclude GUI/IPC
overhead, use a specific model and image size, and are not performance guarantees
for other ODBs, larger images or hardware. No other CAE version is claimed.

## Maintenance checks (2026-10-12)

Python 2.7 compilation and all eight refinement-classification assertions passed.
Both existing CAE 2021 noGUI diagnostics passed with a local read-only test ODB.
A separate native noGUI check deliberately rejected fast restoration and verified
exact primaryVariable and Frame round-trips for seven available refinements,
including Max. Principal and both in-plane principal values. Out-of-Plane Principal
was not available in that ODB; its classification was checked, not its native restore.
The installer/package smoke test passed. GUI TEST: NOT RUN for this maintenance
change; the selector GUI evidence above belongs to the original V0.2 release.

## Short manual regression checklist

1. Open, close with both Close and the window X, then reopen the plug-in.
2. Preview once; change several settings with Auto-update enabled.
3. Select a field, an available component/invariant and multiple Frames.
4. Export; review filenames in the plan, cancel once and confirm once.
5. Deliberately choose an unavailable output or invalid destination, then
   correct it and export again. Confirm controls are not permanently locked.
6. Reset and confirm the original Frame, field and camera are restored.
7. With Auto Fit disabled, check that manual zoom/pan is preserved.

## 中文

已区分实际 noGUI 检查与 GUI 检查：前者覆盖分量、多帧出图、恢复、错误后重试
及合并画布等；后者专项验证场变量选择器的打开、多选、应用及重新打开。
发布版本的补充人工试用反馈无明显问题，但不作为自动化回归测试证据。
V0.2 发布整理未额外修改功能逻辑。

以上不是所有模型的性能保证，也不代表其他 Abaqus 版本已兼容。人工回归重点
为开关窗口、预览与自动更新、连续改设置、导出计划和实际导出、故意报错后重试、
Reset 以及 Close 后重新打开。保留手动视角时关闭 Auto Fit。
