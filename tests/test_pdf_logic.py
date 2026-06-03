from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tools.pdf_extract import parse_page_spec
from tools.pdf_split import _parse_split_ranges, build_page_groups
from tools.pdf_to_images_pdf import (
    _looks_like_generated_output,
    _output_path,
    _single_line_text,
    _split_watermark_lines,
)


# --- pdf_extract.parse_page_spec：返回 0 起始、去重、夹紧到 [1, total] ---

def test_parse_page_spec_mixes_singles_and_ranges() -> None:
    assert parse_page_spec("1,3,5-7,10-", 12) == [0, 2, 4, 5, 6, 9, 10, 11]


def test_parse_page_spec_dedupes_while_preserving_order() -> None:
    assert parse_page_spec("3,1,1,2-3", 5) == [2, 0, 1]


def test_parse_page_spec_clamps_out_of_range() -> None:
    assert parse_page_spec("3-100", 5) == [2, 3, 4]


def test_parse_page_spec_open_ended_start_and_end() -> None:
    assert parse_page_spec("-3", 10) == [0, 1, 2]
    assert parse_page_spec("8-", 10) == [7, 8, 9]


def test_parse_page_spec_accepts_chinese_separators() -> None:
    assert parse_page_spec("1，2；3", 5) == [0, 1, 2]


def test_parse_page_spec_ignores_invalid_and_zero() -> None:
    assert parse_page_spec("0,abc,99", 5) == []
    assert parse_page_spec("   ", 5) == []


# --- pdf_split._parse_split_ranges：保留分组、组间不去重 ---

def test_parse_split_ranges_keeps_separate_groups() -> None:
    assert _parse_split_ranges("1-3,4-6,7-", 8) == [[0, 1, 2], [3, 4, 5], [6, 7]]


def test_parse_split_ranges_single_pages() -> None:
    assert _parse_split_ranges("2,4", 5) == [[1], [3]]


def test_parse_split_ranges_clamps_and_drops_empty() -> None:
    assert _parse_split_ranges("3-100, 100-200", 5) == [[2, 3, 4]]


# --- pdf_split.build_page_groups ---

def test_build_page_groups_every_page() -> None:
    assert build_page_groups("every_page", 0, "", 3) == [[0], [1], [2]]


def test_build_page_groups_every_n_with_remainder() -> None:
    assert build_page_groups("every_n", 2, "", 5) == [[0, 1], [2, 3], [4]]


def test_build_page_groups_custom_delegates_to_parser() -> None:
    assert build_page_groups("custom", 0, "1-2,3", 4) == [[0, 1], [2]]


# --- pdf_to_images_pdf 路径与文本辅助 ---

def test_output_path_appends_underscore_suffix() -> None:
    assert _output_path(os.path.join("dir", "report.pdf")).endswith(
        os.path.join("dir", "report_.pdf")
    )


def test_looks_like_generated_output_detects_tool_outputs() -> None:
    assert _looks_like_generated_output("report_.pdf") is True
    assert _looks_like_generated_output("report_(1).pdf") is True
    assert _looks_like_generated_output("report.pdf") is False


def test_single_line_text_collapses_newlines() -> None:
    assert _single_line_text("第一行\\n第二行") == "第一行 第二行"
    assert _single_line_text("  a \n\n b ") == "a b"


def test_split_watermark_lines_collapses_to_single_line() -> None:
    # 当前实现：分号/中文分号被并入同一行（见模块说明）。
    assert _split_watermark_lines("甲;乙；丙") == ["甲 乙 丙"]
    assert _split_watermark_lines("   ") == []
