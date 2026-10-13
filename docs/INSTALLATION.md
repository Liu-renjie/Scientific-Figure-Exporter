# Installation and updating 安装与更新

## English

Verified environment: Windows, Abaqus/CAE 2021, embedded Python 2.7. A separate
Python 2.7 or Python 3 can run the installer; no pip packages are required.

1. Close Abaqus/CAE. Back up any local customizations to your old plug-in.
2. Download `Scientific-Figure-Exporter-V0.2.zip` from the
   [V0.2 release](https://github.com/Liu-renjie/Scientific-Figure-Exporter/releases/tag/v0.2).
3. Extract the ZIP. Open a terminal **in the folder containing
   `install_plugin.py`**, then run `python install_plugin.py`.
4. The default destination is
   `%USERPROFILE%\abaqus_plugins\ScientificFigureExporter`. Files replaced by
   the installer receive `.bak_<timestamp>` backups in that directory.
5. Restart CAE. Open **Plug-ins > Scientific Figure Exporter...**.

If Python is not on PATH, use its full executable path or install manually.
Alternatively, from an appropriate Abaqus Command environment with Abaqus 2021
available, run `abaqus python install_plugin.py` in the extracted folder. This
command was checked with Abaqus 2021's Python 2.7 installer in an isolated target.
Copy these six files together into the destination above, keeping their names:

```
scientificFigureExporter_plugin.py
scientificFigureExporter_form.py
scientificFigureExporter_kernel.py
scientificFigureExporter_state.py
scientificFigureExporter_jpeg.py
colorMaps.py
```

Do not install files from two releases into different plug-in search paths.
The manual, screenshots and diagnostics are not needed at runtime. If CAE was
open while updating, restart it so cached Python modules are not reused.

To remove the plug-in, close CAE and move this specific plug-in folder out of
the Abaqus plug-in search path. Do not remove your entire `abaqus_plugins`
directory. To roll back, reinstall a previous release with CAE closed.

Optional checksum verification in PowerShell:

```powershell
Get-FileHash .\Scientific-Figure-Exporter-V0.2.zip -Algorithm SHA256
```

Compare the result with `SHA256SUMS.txt` from the same release.

## 中文

验证环境为 Windows + Abaqus/CAE 2021（内置 Python 2.7）。安装器可由另行安装
的 Python 2.7 或 Python 3 运行，不需要安装 pip 依赖。

1. 关闭 Abaqus/CAE；如修改过旧插件，先自行备份修改内容。
2. 从 V0.2 发布页下载 `Scientific-Figure-Exporter-V0.2.zip` 并解压。
3. 在**包含 `install_plugin.py` 的文件夹**打开终端，运行：
   `python install_plugin.py`。
4. 默认安装到 `%USERPROFILE%\abaqus_plugins\ScientificFigureExporter`。
   安装器会为被替换文件创建 `.bak_<时间戳>` 备份。
5. 重启 Abaqus/CAE，从 **Plug-ins > Scientific Figure Exporter...** 打开。

若系统找不到 python，可用 Python 可执行文件的完整路径，或将上述六个运行
文件手动复制到安装目录。文件名保持不变，六个文件必须在同一文件夹。
也可在能够调用 Abaqus 2021 的 Abaqus Command 环境中，在解压目录运行
`abaqus python install_plugin.py`；该形式已用 Abaqus 2021 内置 Python 2.7
在独立测试目录验证安装成功。
不要在多个插件搜索目录混装不同版本。Word 手册、截图和诊断脚本不是运行依赖。

卸载时关闭 CAE，仅将本插件目录移出 Abaqus 插件搜索路径，不要删除整个
`abaqus_plugins` 文件夹。回退时关闭 CAE 后重新安装旧版本。可用上面的
PowerShell 命令计算 SHA-256，并与同一发布页的校验文件对比。
