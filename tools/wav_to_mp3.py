import os
import sys

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMessageBox,
)


def convert_wav_to_mp3(input_path: str) -> str:
    try:
        from pydub import AudioSegment
    except ModuleNotFoundError as exc:
        raise RuntimeError("缺少音频转换依赖，请先安装：pip install pydub，并确保 ffmpeg 可用。") from exc

    output_path = os.path.splitext(input_path)[0] + ".mp3"
    audio = AudioSegment.from_wav(input_path)
    audio.export(output_path, format="mp3")
    return output_path


def run_wav_to_mp3() -> None:
    app = QApplication.instance() or QApplication(sys.argv)

    files, _ = QFileDialog.getOpenFileNames(
        None, "选择 WAV 文件", "", "WAV 文件 (*.wav)"
    )
    if not files:
        return

    outputs = []
    failed = []
    for path in files:
        try:
            outputs.append(convert_wav_to_mp3(path))
        except Exception as exc:
            failed.append(f"{path}: {exc}")

    if failed:
        QMessageBox.warning(None, "部分失败", "\n".join(failed))
    if outputs:
        QMessageBox.information(None, "完成", "已生成：\n" + "\n".join(outputs))


if __name__ == "__main__":
    run_wav_to_mp3()
