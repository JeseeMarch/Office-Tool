import importlib.util
import sys
from functools import partial
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


def load_tool(module_file: str, module_name: str, tools_root: Path | None = None) -> object:
    base = tools_root if tools_root is not None else Path(__file__).resolve().parent / "tools"
    tool_path = base / module_file
    if not tool_path.exists():
        raise FileNotFoundError(f"找不到工具脚本：{tool_path}")

    spec = importlib.util.spec_from_file_location(module_name, tool_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Office Tool 办公工具箱")
        self.resize(720, 560)
        self._project = Path(__file__).resolve().parent

        main_layout = QVBoxLayout()
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(140)

        tabs = QTabWidget()
        tabs.addTab(self._wrap_scroll(self._build_tab_pdf()), "PDF")
        tabs.addTab(self._wrap_scroll(self._build_tab_word()), "Word")
        tabs.addTab(self._wrap_scroll(self._build_tab_files()), "文件与目录")
        tabs.addTab(self._wrap_scroll(self._build_tab_other()), "其他")

        main_layout.addWidget(tabs)
        main_layout.addWidget(QLabel("日志"))
        main_layout.addWidget(self.log)
        self.setLayout(main_layout)

    def _wrap_scroll(self, inner: QWidget) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        return scroll

    def _build_tab_pdf(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout()
        tools = [
            (
                "PDF → 图片型 PDF（平铺水印，可调字号）",
                "pdf_to_images_pdf.py",
                "pdf_to_images_pdf",
                "process_pdf",
                "已打开：PDF 转图片型 PDF（水印）。",
            ),
            (
                "PDF → 每页导出 PNG/JPG",
                "pdf_to_pic.py",
                "pdf_to_pic",
                "run_pdf_to_images",
                "已打开：PDF 导出为图片。",
            ),
            (
                "PDF → 图片型 PDF（居中浅水印）",
                "pdf_to_image_pdf_hidden_watermark.py",
                "pdf_hidden_wm",
                "run_pdf_hidden_watermark",
                "已打开：PDF 居中浅水印。",
            ),
        ]
        for label, mod_file, mod_name, fn, ok in tools:
            b = QPushButton(label)
            b.clicked.connect(partial(self._run_tool, mod_file, mod_name, fn, ok, None))
            layout.addWidget(b)
        layout.addStretch()
        w.setLayout(layout)
        return w

    def _build_tab_word(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout()
        tools = [
            ("Word 加水印（页眉居中底层，输出 docx）", "word_watermark.py", "word_wm", "run_word_watermark", "已打开 Word 加水印。"),
            ("Word 加公司 Logo 水印（居中底层，输出 _logo.docx）", "word_logo_watermark.py", "word_logo_wm", "run_word_logo_watermark", "已打开 Logo 水印。"),
            ("Word 内容批量替换", "word_batch_replace.py", "word_br", "run_batch_replace", "已打开批量替换。"),
            ("Word → 图片型 PDF + 水印", "word_to_image_pdf_watermark.py", "word_img_wm", "batch_convert_to_image_pdf", "已打开 Word 转图片型 PDF（水印）。"),
            ("Word → 图片型 PDF（无水印）", "word_to_graphic_pdf_v2.py", "word_gpdf", "batch_convert_to_image_pdf", "已打开 Word 转图片型 PDF。"),
        ]
        for label, mod_file, mod_name, fn, ok in tools:
            b = QPushButton(label)
            b.clicked.connect(partial(self._run_tool, mod_file, mod_name, fn, ok, None))
            layout.addWidget(b)
        layout.addStretch()
        w.setLayout(layout)
        return w

    def _build_tab_files(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout()
        tools = [
            ("目录树导出为 Word", "directory_listing.py", "dir_list", "run_directory_listing_gui", "已打开目录树导出。"),
            ("子文件夹内文件扁平复制到同一目录", "flatten_copy_from_subfolders.py", "flat_copy", "run_flatten_copy", "已打开扁平复制。"),
            ("批量替换文件名（子串）", "batch_rename_filenames.py", "batch_rn", "run_batch_rename_filenames", "已打开批量重命名窗口。"),
            ("OneDrive 触发按需下载（遍历读文件）", "onedrive_download_trigger.py", "od_dl", "run_onedrive_download_trigger", "OneDrive 扫描已启动，请看控制台输出。"),
        ]
        for label, mod_file, mod_name, fn, ok in tools:
            b = QPushButton(label)
            b.clicked.connect(partial(self._run_tool, mod_file, mod_name, fn, ok, None))
            layout.addWidget(b)
        layout.addStretch()
        w.setLayout(layout)
        return w

    def _build_tab_other(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout()
        tools = [
            ("Markdown → Word", "markdown_to_docx.py", "md_docx", "run_markdown_to_docx", "已打开 Markdown 转换。"),
            ("按 URL 下载文件", "file_download.py", "url_dl", "run_url_download", "已打开 URL 下载。"),
            ("WAV → MP3", "wav_to_mp3.py", "wav_mp3", "run_wav_to_mp3", "已打开音频转换。"),
            ("PDF 密码暴力尝试（仅自有文件，长度勿过大）", "pdf_password_brute_force.py", "pdf_bf", "run_pdf_password_brute_force", "已打开密码尝试工具。"),
        ]
        for label, mod_file, mod_name, fn, ok in tools:
            b = QPushButton(label)
            b.clicked.connect(partial(self._run_tool, mod_file, mod_name, fn, ok, None))
            layout.addWidget(b)
        layout.addStretch()
        w.setLayout(layout)
        return w

    def _run_tool(
        self,
        module_file: str,
        module_name: str,
        function_name: str,
        success_text: str,
        tools_root: Path | None,
    ):
        self.log.append(f"调用 {module_file} :: {function_name}")
        try:
            tool = load_tool(module_file, module_name, tools_root)
            fn = getattr(tool, function_name, None)
            if not callable(fn):
                msg = f"模块 {module_file} 中未找到可调用函数 {function_name}。"
                self.log.append(msg)
                QMessageBox.warning(self, "调用失败", msg)
                return
            fn()
            self.log.append(success_text)
        except Exception as exc:
            msg = f"调用失败：{exc}"
            self.log.append(msg)
            QMessageBox.critical(self, "调用失败", msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
