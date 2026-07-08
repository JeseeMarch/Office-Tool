import os
import sys

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
)

TOOL_VERSION = "3.0"

# 分块读取大小：整文件读完才算真正触发下载，read 会阻塞到 OneDrive 下载完成，
# 循环因此自然按下载速度节流，不会一次性把下载队列打爆导致中途卡停。
_CHUNK = 1024 * 1024  # 1 MiB

# 这些文件不值得下载（系统/占位垃圾），跳过以免浪费时间和流量。
_SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _collect_files(root_folder) -> list[str]:
    """遍历目录，收集所有待处理文件路径（仅读目录元数据，很快）。"""
    matches = []
    for root, _dirs, files in os.walk(root_folder):
        for file in files:
            if file.lower() in _SKIP_NAMES:
                continue
            matches.append(os.path.join(root, file))
    return matches


def _hydrate_file(file_path) -> int:
    """
    整文件分块读完，强制 OneDrive 把按需文件下载到本地。
    返回读取的字节数；出错抛异常由调用方捕获。
    """
    total = 0
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            total += len(chunk)
    return total


def download_onedrive_files(root_folder, progress_callback=None, log_callback=None) -> tuple[int, int, int, int]:
    """
    返回 (总数, 成功下载数, 失败数, 已下载字节数)。
    单个文件失败只记账并跳过，绝不中断整轮。
    log_callback(text) 用于把总数与实时进度直接写进壳的日志。

    纯逻辑、不碰任何 GUI 控件，因此可安全地在后台线程里运行。
    """
    log = log_callback or print

    log("正在统计文件数量…")
    files = _collect_files(root_folder)
    total = len(files)
    log(f"共发现 {total} 个文件需要下载。")
    if progress_callback:
        progress_callback(0, total)

    if total == 0:
        return 0, 0, 0, 0

    downloaded = 0
    failed = 0
    total_bytes = 0
    # 每处理约 5% 播报一次进度，保证无论文件多寡日志都有 ~20 条更新、不刷屏。
    interval = max(1, total // 20)

    for index, file_path in enumerate(files, start=1):
        try:
            total_bytes += _hydrate_file(file_path)
            downloaded += 1
        except FileNotFoundError:
            failed += 1  # 占位符尚未就绪/被移动
        except PermissionError:
            failed += 1  # 权限问题
        except OSError:
            failed += 1  # 网络/下载中断等，跳过不阻塞后续
        finally:
            if progress_callback:
                progress_callback(index, total)

        if index % interval == 0 or index == total:
            log(f"已下载 {downloaded}/{total}（跳过/失败 {failed}，累计 {_human_size(total_bytes)}）")

    return total, downloaded, failed, total_bytes


class _DownloadWorker(QObject):
    """在后台线程里跑 download_onedrive_files，用信号把进度/日志投回主线程。"""

    progress = Signal(int, int)
    log = Signal(str)
    finished = Signal(int, int, int, int)

    def __init__(self, folder: str) -> None:
        super().__init__()
        self._folder = folder

    @Slot()
    def run(self) -> None:
        result = download_onedrive_files(
            self._folder,
            progress_callback=lambda value, maximum: self.progress.emit(value, maximum),
            log_callback=lambda text: self.log.emit(text),
        )
        self.finished.emit(*result)


class _Bridge(QObject):
    """住在主线程，负责把 worker 的跨线程信号安全地转调给壳的回调（更新控件）。"""

    def __init__(self, progress_callback, log_callback) -> None:
        super().__init__()
        self._progress_callback = progress_callback
        self._log_callback = log_callback

    @Slot(int, int)
    def on_progress(self, value: int, maximum: int) -> None:
        if self._progress_callback:
            self._progress_callback(value, maximum)

    @Slot(str)
    def on_log(self, text: str) -> None:
        self._log_callback(text)


def run_onedrive_download_trigger(progress_callback=None, log_callback=None) -> str:
    log = log_callback or print
    app = QApplication.instance() or QApplication(sys.argv)

    folder = QFileDialog.getExistingDirectory(None, "选择 OneDrive 文件夹")
    if not folder:
        return "已取消：OneDrive 下载触发。"

    if not os.path.isdir(folder):
        return "OneDrive 下载已取消：选择的不是有效文件夹。"

    log(f"开始扫描：{folder}")

    # 下载放后台线程，主线程只刷 UI —— 单个大文件/慢网络再久也不会卡死界面。
    thread = QThread()
    worker = _DownloadWorker(folder)
    worker.moveToThread(thread)

    # Bridge 在主线程创建 → 跨线程信号走队列连接，回调始终在主线程执行（可安全动控件）。
    bridge = _Bridge(progress_callback, log)
    worker.progress.connect(bridge.on_progress)
    worker.log.connect(bridge.on_log)

    result: dict[str, tuple] = {}
    worker.finished.connect(lambda *r: result.__setitem__("value", r))
    worker.finished.connect(thread.quit)
    thread.started.connect(worker.run)

    thread.start()
    # 主线程边等边泵事件：GUI 保持响应，队列信号得以送达。
    while thread.isRunning():
        app.processEvents()
        thread.wait(30)
    app.processEvents()  # 收尾，确保最后一批信号送达
    worker.deleteLater()

    total, downloaded, failed, total_bytes = result.get("value", (0, 0, 0, 0))
    return (
        f"OneDrive 下载完成：共 {total} 个文件，"
        f"成功下载 {downloaded} 个，跳过/失败 {failed} 个，"
        f"合计 {_human_size(total_bytes)}。"
    )


if __name__ == "__main__":
    run_onedrive_download_trigger()
