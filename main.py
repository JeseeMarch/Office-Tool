from __future__ import annotations

import importlib.util
import inspect
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


MAIN_VERSION = "20260503-clean"


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


APP_DIR = _app_dir()
TOOLS_DIR = APP_DIR / "tools"


@dataclass(frozen=True)
class ToolSpec:
    label: str
    module_file: str
    function_name: str
    success_text: str


PDF_TOOLS = [
    ToolSpec(
        "PDF → 图片型 PDF（平铺水印，可调字号）",
        "pdf_to_images_pdf.py",
        "process_pdf",
        "已打开：PDF 转图片型 PDF（水印）。",
    ),
    ToolSpec("PDF → 每页导出 PNG/JPG", "pdf_to_pic.py", "run_pdf_to_images", "已打开：PDF 导出为图片。"),
    ToolSpec("PDF 分割（每页 / 每N页 / 自定义范围）", "pdf_split.py", "run_pdf_split", "已打开：PDF 分割。"),
    ToolSpec("PDF 页面提取（指定页码或范围）", "pdf_extract.py", "run_pdf_extract", "已打开：PDF 页面提取。"),
    ToolSpec("PDF 合并（多文件按序合并为一）", "pdf_merge.py", "run_pdf_merge", "已打开：PDF 合并。"),
]

WORD_TOOLS = [
    ToolSpec("Word 加水印（单行/多行/图片）", "word_watermark.py", "run_word_watermark", "已打开 Word 加水印。"),
    ToolSpec(
        "Word → 图片型 PDF（无水印/单行/多行/图片水印）",
        "word_to_image_pdf_watermark.py",
        "batch_convert_to_image_pdf",
        "已打开 Word 转图片型 PDF。",
    ),
    ToolSpec("Word 内容批量替换", "word_batch_replace.py", "run_batch_replace", "已打开批量替换。"),
]

FILE_TOOLS = [
    ToolSpec("目录树导出为 Word", "directory_listing.py", "run_directory_listing_gui", "已打开目录树导出。"),
    ToolSpec("子文件夹内文件扁平复制到同一目录", "flatten_copy_from_subfolders.py", "run_flatten_copy", "已打开扁平复制。"),
    ToolSpec("批量替换文件名（子串）", "batch_rename_filenames.py", "run_batch_rename_filenames", "已打开批量重命名窗口。"),
    ToolSpec(
        "OneDrive 触发按需下载（遍历读文件）",
        "onedrive_download_trigger.py",
        "run_onedrive_download_trigger",
        "OneDrive 扫描已启动，请看控制台输出。",
    ),
]

OTHER_TOOLS = [
    ToolSpec("Markdown → Word", "markdown_to_docx.py", "run_markdown_to_docx", "已打开 Markdown 转换。"),
    ToolSpec("按 URL 下载文件", "file_download.py", "run_url_download", "已打开 URL 下载。"),
    ToolSpec("WAV → MP3", "wav_to_mp3.py", "run_wav_to_mp3", "已打开音频转换。"),
    ToolSpec(
        "PDF 密码暴力尝试（仅自有文件，长度勿过大）",
        "pdf_password_brute_force.py",
        "run_pdf_password_brute_force",
        "已打开密码尝试工具。",
    ),
]


def _tool_path(module_file: str) -> Path:
    path = (TOOLS_DIR / module_file).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"找不到工具脚本：{path}")
    return path


def load_tool(module_file: str):
    path = _tool_path(module_file)
    module_name = f"office_tool_{path.stem}_{path.stat().st_mtime_ns}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载工具脚本：{path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Office Tool 办公工具箱 - {MAIN_VERSION}")
        self.resize(760, 600)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._wrap_scroll(self._build_tool_tab(PDF_TOOLS)), "PDF")
        tabs.addTab(self._wrap_scroll(self._build_tool_tab(WORD_TOOLS)), "Word")
        tabs.addTab(self._wrap_scroll(self._build_tool_tab(FILE_TOOLS)), "文件与目录")
        tabs.addTab(self._wrap_scroll(self._build_tool_tab(OTHER_TOOLS)), "其他")
        layout.addWidget(tabs)

        layout.addWidget(QLabel("日志"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(160)
        layout.addWidget(self.log)

        layout.addWidget(QLabel("进度"))
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self._log(f"主程序版本：{MAIN_VERSION}")
        self._log(f"工具目录：{TOOLS_DIR}")

    def _log(self, text: str) -> None:
        self.log.append(text)

    def _wrap_scroll(self, inner: QWidget) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        return scroll

    def _build_tool_tab(self, tools: list[ToolSpec]) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        for tool in tools:
            button = QPushButton(tool.label)
            button.clicked.connect(lambda checked=False, spec=tool: self._run_tool(spec))
            layout.addWidget(button)
        layout.addStretch()
        return tab

    def _reset_progress(self) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        QApplication.processEvents()

    def _update_progress(self, value: int, maximum: int) -> None:
        self.progress.setRange(0, max(1, maximum))
        self.progress.setValue(max(0, min(value, max(1, maximum))))
        QApplication.processEvents()

    def _run_tool(self, spec: ToolSpec) -> None:
        self._log(f"调用：{spec.module_file} :: {spec.function_name}")
        self._reset_progress()
        try:
            tool = load_tool(spec.module_file)
            loaded_path = Path(getattr(tool, "__file__", _tool_path(spec.module_file))).resolve()
            version = getattr(tool, "TOOL_VERSION", "无版本号")
            self._log(f"加载路径：{loaded_path}")
            self._log(f"工具版本：{version}")

            fn = getattr(tool, spec.function_name, None)
            if not callable(fn):
                message = f"模块 {spec.module_file} 中未找到可调用函数 {spec.function_name}。"
                self._log(message)
                QMessageBox.warning(self, "调用失败", message)
                return

            if "progress_callback" in inspect.signature(fn).parameters:
                result = fn(progress_callback=self._update_progress)
            else:
                result = fn()
            if isinstance(result, str) and result.strip():
                self._log(result)
            else:
                self._log(spec.success_text)
            self._update_progress(1, 1)
        except Exception as exc:
            details = traceback.format_exc()
            self._log(f"调用失败：{exc}")
            self._log(details)
            QMessageBox.critical(self, "调用失败", f"{exc}\n\n{details}")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
