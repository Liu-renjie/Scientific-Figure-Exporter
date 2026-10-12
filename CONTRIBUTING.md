# Contributing 参与反馈

Bug reports and small, well-scoped improvements are welcome. The supported
target is Windows + Abaqus/CAE 2021 + Python 2.7. Keep runtime code compatible
with Python 2.7 and preserve the existing GUI/Form/Kernel workflow.

For a bug report, provide your CAE and Windows versions, reproduction steps,
expected versus actual behavior, relevant Error Log text, and whether the
problem affects Preview, Export, or both. For performance issues, include ODB
size, selected fields/Frames/views, output resolution, and elapsed time.

Remove personal paths and proprietary details. Do not attach CAE/ODB model
files or licensed Abaqus files to public issues. Mark noGUI checks separately
from real GUI checks; do not claim other Abaqus versions are supported without
testing them. Please discuss substantial changes in an issue before a large PR.

欢迎提交问题和小范围改进。请提供环境、复现步骤、预期与实际表现以及错误日志；
性能问题请补充 ODB 大小、批次规模、视图、分辨率和耗时。公开附件前移除个人
路径及专有数据，不要上传模型或 Abaqus 授权文件。修改保持 Python 2.7 兼容，
明确区分 noGUI 检查和真实 GUI 测试，大改动请先通过 Issue 讨论。

## Release workflow 发布流程

The `Publish release` workflow runs when `VERSION` changes on main, or when a
maintainer starts it manually. Before a new release, update the plug-in's
registration version, `VERSION`, release notes, README and manual, then verify
the tested runtime. The builder in `scripts/build_release.py` uses Python 3
standard library only and must be updated if documentation/asset names change.
This build tool is not loaded by Abaqus.

The workflow creates a fresh tag and draft, uploads the allowlisted install
ZIP, Word guide and checksums, then publishes. It refuses to replace any
existing release or tag. The job requests only repository contents write
permission through GitHub's automatic token; no personal token is required.

发布时更新 VERSION、插件注册版本和文档，再进行验证。main 上 VERSION 的变更
会触发打包发布，也可手动运行。已有标签和发布不会被覆盖。若上传中断留下草稿，
先检查草稿及附件，不要通过移动旧标签强行重试。
