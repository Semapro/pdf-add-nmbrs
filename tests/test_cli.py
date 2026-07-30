from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from pdf_add_nmbrs.cli import (
    PdfLineNumberError,
    add_line_numbers,
    create_parser,
    group_line_tops,
    parse_color,
    validate_arguments,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def arguments(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "margin": 12.0,
        "top_margin": 15.0,
        "bottom_margin": 15.0,
        "line_spacing": 6.0,
        "line_tolerance": 3.0,
        "font_size": 7.0,
        "every": 1,
        "start": 1,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def create_test_pdf(path: Path) -> None:
    document = canvas.Canvas(str(path))
    document.drawString(100, 700, "First review line")
    document.drawString(100, 680, "Second review line")
    document.save()


def test_package_cli_help_is_available() -> None:
    result = subprocess.run(
        [sys.executable, "src/pdf_add_nmbrs/cli.py", "--help"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Add line numbers to an existing PDF" in result.stdout


def test_root_script_help_is_available() -> None:
    result = subprocess.run(
        [sys.executable, "pdf_line_numbers.py", "--help"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Add line numbers to an existing PDF" in result.stdout


def test_parse_color_accepts_hash_and_plain_rgb() -> None:
    assert parse_color("#000000") == (0.0, 0.0, 0.0)
    assert parse_color("FFFFFF") == (1.0, 1.0, 1.0)


@pytest.mark.parametrize("value", ("12345", "GG0000"))
def test_parse_color_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_color(value)


def test_group_line_tops_uses_configured_tolerance() -> None:
    words: list[dict[str, object]] = [
        {"top": 10.0},
        {"top": 11.0},
        {"top": 20.0},
    ]

    assert group_line_tops(words, tolerance=2.0) == [10.5, 20.0]


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("margin", 0),
        ("top_margin", 0),
        ("bottom_margin", 0),
        ("line_spacing", 0),
        ("line_tolerance", 0),
        ("font_size", 0),
        ("every", 0),
    ),
)
def test_validate_arguments_rejects_non_positive_values(
    name: str,
    value: float,
) -> None:
    with pytest.raises(PdfLineNumberError, match="greater than zero"):
        validate_arguments(arguments(**{name: value}))


def test_validate_arguments_rejects_negative_start() -> None:
    with pytest.raises(PdfLineNumberError, match="cannot be negative"):
        validate_arguments(arguments(start=-1))


def test_adds_line_numbers_without_overwriting_source(tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "numbered.pdf"
    create_test_pdf(source)
    original = source.read_bytes()

    args = create_parser().parse_args([str(source), str(output)])
    pages, numbers = add_line_numbers(args)

    assert pages == 1
    assert numbers == 2
    assert source.read_bytes() == original
    assert len(PdfReader(str(output)).pages) == 1
    assert "1" in (PdfReader(str(output)).pages[0].extract_text() or "")


def test_grid_mode_numbers_a_page(tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "grid.pdf"
    create_test_pdf(source)

    args = create_parser().parse_args(
        [str(source), str(output), "--mode", "grid", "--every", "5"]
    )
    pages, numbers = add_line_numbers(args)

    assert pages == 1
    assert numbers > 0
    assert output.is_file()


def test_existing_output_requires_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "numbered.pdf"
    create_test_pdf(source)
    output.write_bytes(b"existing")

    args = create_parser().parse_args([str(source), str(output)])

    with pytest.raises(PdfLineNumberError, match="use --overwrite"):
        add_line_numbers(args)

