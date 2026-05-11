import os
import sys
import warnings

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMessageBox,
)


def _load_audio_segment():
    try:
        import imageio_ffmpeg
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "缺少 ffmpeg，请先安装：pip install imageio-ffmpeg"
        ) from exc

    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    if not os.path.exists(ffmpeg_path):
        raise RuntimeError(f"找不到 ffmpeg 可执行文件：{ffmpeg_path}")

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Couldn't find ffmpeg or avconv.*",
                category=RuntimeWarning,
            )
            from pydub import AudioSegment
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "缺少音频转换依赖，请先安装：pip install pydub imageio-ffmpeg"
        ) from exc

    AudioSegment.converter = ffmpeg_path
    AudioSegment.ffmpeg = ffmpeg_path
    return AudioSegment


def convert_wav_to_mp3(input_path: str) -> str:
    output_path = os.path.splitext(input_path)[0] + ".mp3"
    AudioSegment = _load_audio_segment()
    audio = AudioSegment.from_wav(input_path)
    audio.export(output_path, format="mp3")
    return output_path


def run_wav_to_mp3() -> str:
    app = QApplication.instance() or QApplication(sys.argv)

    files, _ = QFileDialog.getOpenFileNames(
        None, "选择 WAV 文件", "", "WAV 文件 (*.wav)"
    )
    if not files:
        return "已取消：WAV 转 MP3。"

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
        return "已生成：" + " ".join(outputs)
    return "WAV 转 MP3 未生成文件。"


if __name__ == "__main__":
    run_wav_to_mp3()
