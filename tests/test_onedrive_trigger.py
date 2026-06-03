from __future__ import annotations

from tools.onedrive_download_trigger import download_onedrive_files, touch_file


def test_touch_file_reports_success_and_failure(tmp_path) -> None:
    existing = tmp_path / "a.txt"
    existing.write_text("x", encoding="utf-8")
    assert touch_file(str(existing)) is True
    assert touch_file(str(tmp_path / "missing.txt")) is False


def test_download_counts_only_readable_files(tmp_path) -> None:
    # 回归：旧实现用恒真重言式计数，triggered 总等于 count，
    # 现在应只统计真正读到的文件。
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("data", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.txt").write_text("data", encoding="utf-8")

    count, triggered = download_onedrive_files(str(tmp_path))
    assert count == 4
    assert triggered == 4


def test_download_rejects_non_directory(tmp_path) -> None:
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("x", encoding="utf-8")
    assert download_onedrive_files(str(not_a_dir)) == (0, 0)
