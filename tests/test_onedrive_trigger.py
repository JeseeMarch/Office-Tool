from __future__ import annotations

from tools.onedrive_download_trigger import _hydrate_file, download_onedrive_files


def test_hydrate_reads_whole_file(tmp_path) -> None:
    existing = tmp_path / "a.txt"
    existing.write_bytes(b"x" * 4096)
    assert _hydrate_file(str(existing)) == 4096


def test_download_counts_only_readable_files(tmp_path) -> None:
    # 回归：旧实现用恒真重言式计数，downloaded 总等于 total，
    # 现在应只统计真正读完的文件；不可读的记为 failed。
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("data", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.txt").write_text("data", encoding="utf-8")

    total, downloaded, failed, total_bytes = download_onedrive_files(str(tmp_path))
    assert total == 4
    assert downloaded == 4
    assert failed == 0
    assert total_bytes == 4 * len("data")


def test_download_skips_system_junk(tmp_path) -> None:
    (tmp_path / "real.txt").write_text("data", encoding="utf-8")
    (tmp_path / "desktop.ini").write_text("junk", encoding="utf-8")
    (tmp_path / "Thumbs.db").write_text("junk", encoding="utf-8")

    total, downloaded, failed, _ = download_onedrive_files(str(tmp_path))
    assert total == 1
    assert downloaded == 1
    assert failed == 0


def test_download_reports_progress(tmp_path) -> None:
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("data", encoding="utf-8")

    calls: list[tuple[int, int]] = []
    download_onedrive_files(str(tmp_path), lambda value, maximum: calls.append((value, maximum)))
    # 首次回报建立进度条最大值，末次回报到达总数。
    assert calls[0] == (0, 3)
    assert calls[-1] == (3, 3)


def test_download_logs_total_and_progress(tmp_path) -> None:
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("data", encoding="utf-8")

    logs: list[str] = []
    download_onedrive_files(str(tmp_path), None, logs.append)
    joined = "\n".join(logs)
    # 先播报待下载总数，再有实时"已下载 X/Y"进度。
    assert "共发现 3 个文件需要下载。" in joined
    assert any(line.startswith("已下载 3/3") for line in logs)


def test_download_on_non_directory_is_empty(tmp_path) -> None:
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("x", encoding="utf-8")
    assert download_onedrive_files(str(not_a_dir)) == (0, 0, 0, 0)
