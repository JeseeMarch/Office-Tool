# CLAUDE.md

办公自动化工具箱（Windows 桌面，Python 3.12，PySide6）。`main.py` 是 GUI 壳，`tools/` 下每个文件是一个自包含工具。打包成单目录 exe 分发。

## 架构：注册表 + 自包含工具（插件式）

`main.py` 不直接 import 工具，而是维护一张 `ToolSpec` 注册表，运行时按需动态加载：

- 工具按 Tab 分四组：`PDF_TOOLS` / `WORD_TOOLS` / `FILE_TOOLS` / `OTHER_TOOLS`，每条是
  `ToolSpec(label, module_file, function_name, success_text)`。
- 点按钮 → `load_tool()` 用 `importlib` **按文件路径**加载 `tools/<module_file>`（模块名带 mtime，每次都是新鲜加载，改完工具不用重启壳）→ 读可选 `TOOL_VERSION` → 调 `function_name`。
- **入口函数契约**：壳按参数名注入——签名含 `progress_callback` 则传入 `_update_progress(value, max)`；含 `log_callback` 则传入 `_log(text)`（执行途中往日志写字，如实时进度）。返回非空 `str` 会写进日志，否则用 `success_text`。异常会被壳捕获并弹框，工具内不用自己兜底崩溃。

### 加一个新工具（两步）
1. 写 `tools/xxx.py`，暴露入口函数 `run_xxx(progress_callback=None) -> str`（或无参，见下）。可选加 `TOOL_VERSION = "..."`。
2. 在 `main.py` 对应 Tab 列表加一条 `ToolSpec`。

打包时 `Office_Tool.spec` 用 `collect_submodules("tools")` 自动带上新模块；但若它**惰性 import** 了第三方库，可能要手动加 hiddenimports（见打包雷区）。

## ⚠️ 两套 GUI 框架并存（改工具前先认清）

工具不是统一用 PySide6——历史原因混用了两套，改某个工具时跟它原本的框架走，别混：

- **PySide6**（11 个，入口签名 `(progress_callback=None) -> str`）：所有 `pdf_*`、`word_*`、`batch_rename_filenames`、`flatten_copy_from_subfolders`、`wav_to_mp3`。
- **tkinter**（5 个，入口**无参** `() -> str`，自己弹 Tk 窗口）：`directory_listing`、`file_download`、`markdown_to_docx`、`onedrive_download_trigger`、`pdf_password_brute_force`。

只有 PySide6 工具能接进度条；tkinter 工具不接 `progress_callback`。

## 依赖 → 工具映射（含运行期雷区）

| 库 | 用在哪些工具 | 注意 |
|----|------------|------|
| `fitz` (PyMuPDF) | pdf_extract / pdf_merge / pdf_split / pdf_to_pic / pdf_to_images_pdf | PDF 主力 |
| `pdf2image` + **Poppler** | word_to_image_pdf_watermark | **Poppler 不打包，是运行期外部依赖**，目标机 PATH 必须有 |
| `win32com` / `pythoncom`（惰性） | word_to_image_pdf_watermark | Word→PDF 走 **COM 调本机 Word**，仅 Windows 且需装 Word |
| `python-docx` | directory_listing / word_watermark / word_batch_replace | |
| `pydub` + `imageio_ffmpeg`（惰性） | wav_to_mp3 | ffmpeg 由 imageio_ffmpeg 提供并打进包 |
| `markdown`（惰性）+ `bs4` | markdown_to_docx | 未装则该工具不可用 |
| `PyPDF2` | pdf_password_brute_force | |
| `requests` | file_download | |
| `PIL` | word_watermark / pdf_to_images_pdf / word_to_image_pdf_watermark | 水印渲染 |

> `word_to_image_pdf_watermark` 最重：COM(Word→PDF) + Poppler(PDF→图) + PIL(水印) 三段串联，排查崩溃从这三处入手。

## 水印逻辑分散三处

加水印的代码在 `word_watermark.py`、`word_to_image_pdf_watermark.py`、`pdf_to_images_pdf.py` 三个文件，改一处想另外两处。**改水印必走 `watermark-check` 流程**（见下）。

## 命令

```bash
python main.py              # 运行（开发）
python -m pytest            # 全部测试（offscreen Qt，无需显示器）
.\build_package.ps1         # 打包：PyInstaller → dist\Office_Tool + package\*.zip
```

## 约定

- 改业务逻辑后跑 `python -m pytest`（见 `AGENTS.md`）。新增依赖前先问。不谎报跑过的命令。
- 优先沿用既有代码风格，最小改动，不顺手大重构。

## 项目级 Skill（`.claude/skills/`）

- **watermark-check** — 任何水印改动收尾前的验收清单（跑 watermark 测试 + 用 `环聚医药` 4 字样本做视觉验收）。
- **build-release** — 打包并验证 exe 能跑，覆盖 Poppler/ffmpeg/COM 等打包雷区。
