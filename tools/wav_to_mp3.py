import os
from tkinter import Tk, filedialog, messagebox

from pydub import AudioSegment


def convert_wav_to_mp3(input_path: str) -> str:
    output_path = os.path.splitext(input_path)[0] + ".mp3"
    audio = AudioSegment.from_wav(input_path)
    audio.export(output_path, format="mp3")
    return output_path


def run_wav_to_mp3() -> None:
    root = Tk()
    root.withdraw()

    files = filedialog.askopenfilenames(
        title="选择 WAV 文件",
        filetypes=[("WAV 文件", "*.wav")],
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
        messagebox.showwarning("部分失败", "\n".join(failed))
    if outputs:
        messagebox.showinfo("完成", "已生成：\n" + "\n".join(outputs))


if __name__ == "__main__":
    run_wav_to_mp3()
