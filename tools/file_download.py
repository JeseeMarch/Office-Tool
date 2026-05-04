from pathlib import Path
from tkinter import Tk, filedialog, messagebox, simpledialog
from urllib.parse import urlparse

import requests


def download_file(url: str, output_path: str) -> None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, stream=True, timeout=60)
    response.raise_for_status()

    with open(output_path, "wb") as file:
        for chunk in response.iter_content(chunk_size=1024 * 64):
            if chunk:
                file.write(chunk)


def run_url_download() -> str:
    root = Tk()
    root.withdraw()

    url = simpledialog.askstring("下载文件", "请输入文件 URL：")
    if not url:
        return "已取消：URL 下载。"

    parsed_name = Path(urlparse(url).path).name or "downloaded_file"
    output_path = filedialog.asksaveasfilename(title="保存为", initialfile=parsed_name)
    if not output_path:
        return "已取消：URL 下载。"

    try:
        download_file(url, output_path)
        return f"文件已下载：{output_path}"
    except Exception as exc:
        messagebox.showerror("下载失败", str(exc))
        return f"URL 下载失败：{exc}"


if __name__ == "__main__":
    run_url_download()
