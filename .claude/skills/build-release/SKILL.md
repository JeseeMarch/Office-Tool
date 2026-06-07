---
name: build-release
description: >-
  Build and verify the Windows release package for this project (PyInstaller →
  dist/Office_Tool + zip). Trigger when asked to build, package, make a release,
  produce the exe/zip, or verify that a packaged build still runs. Covers the
  project's known bundling gotchas (Poppler, ffmpeg, pywin32/COM, tools+assets
  datas). Does NOT apply to plain `python main.py` dev runs.
---

# 打包发布 (build-release)

把项目打成 Windows 单目录可执行包并验证它真的能跑。PyInstaller 打包这种带 Poppler/ffmpeg/COM 依赖的桌面程序最容易翻车——按这个流程走，别只看"打包成功"就收工。

## 标准流程

### 1. 先跑测试（打包前的闸门）

```bash
python -m pytest
```

全绿再打包。坏的代码打出来也是坏包。

### 2. 执行打包脚本

```powershell
.\build_package.ps1
```

这个脚本会：先杀掉正在运行的 `Office_Tool` 进程（否则文件占用导致打包失败）→ `python -m PyInstaller --clean --noconfirm Office_Tool.spec` → 把 `dist\Office_Tool\*` 压成 `package\Office_Tool_windows.zip`（带最多 5 次重试，规避杀软/索引锁文件）。

> 不要手动直接调 PyInstaller 跳过这个脚本——杀进程和重试压缩都是必要的。

### 3. 产物校验

- `dist\Office_Tool\Office_Tool.exe` 存在。
- `package\Office_Tool_windows.zip` 已更新（看修改时间）。
- `dist\Office_Tool\_internal\tools\` 和 `_internal\assets\` 都在（spec 里作为 datas 打包）。

### 4. 冒烟测试（关键，最容易被跳过）

启动打包后的 exe，**实际点开几个工具**，确认不是一启动就缺依赖崩溃：

```powershell
Start-Process "dist\Office_Tool\Office_Tool.exe"
```

至少验证主界面能起来、工具列表能加载。重点验下面这些"运行期才暴露"的依赖。

## 已知打包雷区（出问题先查这里）

| 依赖 | 用在哪 | 打包方式 / 排查点 |
|------|--------|-------------------|
| **Poppler** | `pdf2image` → Word 转图片型 PDF | **不随包打包**，是运行期外部依赖，必须在目标机 PATH 上有 poppler。打包机有、目标机没有 → 该功能崩。文档要写明。 |
| **ffmpeg** | `pydub` → WAV 转 MP3 | 由 `imageio_ffmpeg` 提供，spec 用 `collect_data_files("imageio_ffmpeg")` 打进包。验证 `_internal` 里有 ffmpeg 可执行文件。 |
| **pywin32 (win32com)** | Word 转 PDF 走 COM 调 Word | 在 spec 的 `optional_hiddenimports`（含 `pythoncom`/`pywintypes`/`win32com.client`）。**仅 Windows**，且目标机要装 Word。 |
| **tools / assets** | 工具脚本与资源 | spec 作为 `datas` 打包。新增工具或资源目录后，确认它们进了 `_internal`。 |
| **PySide6** | GUI 主框架 | 体量大；exe 用 UPX 压缩。若启动报 Qt plugin 缺失，检查 UPX 是否压坏了 Qt 插件。 |

## 新增依赖/工具后

- 新加第三方库：加进 `requirements.txt`，并视情况补到 spec 的 `optional_hiddenimports` 或 `collect_submodules`。
- 新加 `tools/xxx.py`：`collect_submodules("tools")` 会自动带上，但若它惰性 import 了某个库，该库可能要手动加 hiddenimports。
- 改完务必重打 + 重新冒烟，别假设 spec 自动覆盖。

## 收尾报告

说明：pytest 结果、产物路径（exe + zip）、冒烟测试实际点开了哪些工具、以及 Poppler/ffmpeg/COM 这几项是否验证过。**不要谎报跑过的命令**（项目 AGENTS.md 明确要求）。
