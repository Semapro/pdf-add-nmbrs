"""Create a line-numbered review copy of an existing PDF."""

from __future__ import annotations

import argparse
import io
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

MM = 72 / 25.4


class PdfLineNumberError(Exception):
    """Raised when a PDF cannot be numbered safely."""


@dataclass(frozen=True, slots=True)
class NumberedLine:
    """One line number at a PDF y-coordinate."""

    y: float
    number: int


def parse_color(value: str) -> tuple[float, float, float]:
    """Parse an RRGGBB color for ReportLab."""
    text = value.strip().lstrip("#")
    if len(text) != 6:
        raise argparse.ArgumentTypeError("color must use the form #RRGGBB")
    try:
        return (
            int(text[0:2], 16) / 255,
            int(text[2:4], 16) / 255,
            int(text[4:6], 16) / 255,
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError("color must use the form #RRGGBB") from exc


def group_line_tops(
    words: Iterable[dict[str, object]], tolerance: float
) -> list[float]:
    """Group words with approximately equal top coordinates into text lines."""
    positions: list[float] = []
    for word in words:
        top = word.get("top")
        if not isinstance(top, (int, float)):
            raise PdfLineNumberError(
                "detected PDF word does not have a numeric top coordinate"
            )
        positions.append(float(top))
    positions.sort()
    groups: list[list[float]] = []
    for top in positions:
        if not groups or top - (sum(groups[-1]) / len(groups[-1])) > tolerance:
            groups.append([top])
        else:
            groups[-1].append(top)
    return [sum(group) / len(group) for group in groups]


def detected_line_positions(
    source: Path | io.BytesIO,
    *,
    tolerance: float,
    top_margin: float,
    bottom_margin: float,
) -> list[list[float]]:
    """Return detected horizontal text-line positions for every page."""
    page_positions: list[list[float]] = []
    with pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            words = page.extract_words(
                x_tolerance=2,
                y_tolerance=2,
                keep_blank_chars=False,
                use_text_flow=False,
            )
            tops = group_line_tops(words, tolerance)
            positions = [
                float(page.height) - top - 7
                for top in tops
                if top_margin <= top <= float(page.height) - bottom_margin
            ]
            page_positions.append(positions)
    return page_positions


def grid_line_positions(
    reader: PdfReader,
    *,
    spacing: float,
    top_margin: float,
    bottom_margin: float,
) -> list[list[float]]:
    """Return fixed line positions for scans or PDFs without selectable text."""
    result: list[list[float]] = []
    for page in reader.pages:
        y = float(page.mediabox.height) - top_margin
        positions: list[float] = []
        while y >= bottom_margin:
            positions.append(y)
            y -= spacing
        result.append(positions)
    return result


def create_overlay(
    *,
    width: float,
    height: float,
    lines: list[NumberedLine],
    side: str,
    margin: float,
    font_size: float,
    color: tuple[float, float, float],
) -> bytes:
    """Create a transparent one-page PDF containing only line numbers."""
    buffer = io.BytesIO()
    overlay = canvas.Canvas(
        buffer,
        pagesize=(width, height),
        pageCompression=1,
    )
    overlay.setFont("Helvetica", font_size)
    overlay.setFillColorRGB(*color)

    for line in lines:
        text = str(line.number)
        y = line.y - font_size * 0.28
        if side in {"left", "both"}:
            overlay.drawRightString(margin, y, text)
        if side in {"right", "both"}:
            overlay.drawString(width - margin, y, text)

    overlay.save()
    return buffer.getvalue()


def add_line_numbers(args: argparse.Namespace) -> tuple[int, int]:
    """Add line-number overlays and return page and line-number counts."""
    source = args.input.expanduser().resolve()
    destination = args.output.expanduser().resolve()
    if source == destination:
        raise PdfLineNumberError("input and output must be different files")
    if not source.is_file():
        raise PdfLineNumberError(f"input PDF does not exist: {source}")
    if source.suffix.lower() != ".pdf":
        raise PdfLineNumberError(f"input file is not a PDF: {source}")
    if destination.exists() and not args.overwrite:
        raise PdfLineNumberError(
            f"output already exists: {destination}; use --overwrite to replace it"
        )

    reader = PdfReader(str(source))
    if reader.is_encrypted and reader.decrypt(args.password or "") == 0:
        raise PdfLineNumberError("the PDF is encrypted; supply --password")

    for page in reader.pages:
        if int(page.get("/Rotate", 0)) % 360:
            page.transfer_rotation_to_content()

    top_margin = args.top_margin * MM
    bottom_margin = args.bottom_margin * MM
    if args.mode == "text":
        detection_writer = PdfWriter()
        for page in reader.pages:
            detection_writer.add_page(page)
        detection_buffer = io.BytesIO()
        detection_writer.write(detection_buffer)
        detection_buffer.seek(0)
        positions = detected_line_positions(
            detection_buffer,
            tolerance=args.line_tolerance,
            top_margin=top_margin,
            bottom_margin=bottom_margin,
        )
    else:
        positions = grid_line_positions(
            reader,
            spacing=args.line_spacing * MM,
            top_margin=top_margin,
            bottom_margin=bottom_margin,
        )

    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    number = args.start
    total = 0
    for index, page in enumerate(writer.pages):
        if args.restart_each_page:
            number = args.start

        selected = positions[index][:: args.every]
        lines = [
            NumberedLine(y=y, number=number + offset)
            for offset, y in enumerate(selected)
        ]
        number += len(lines)
        total += len(lines)

        if lines:
            overlay_data = create_overlay(
                width=float(page.mediabox.width),
                height=float(page.mediabox.height),
                lines=lines,
                side=args.side,
                margin=args.margin * MM,
                font_size=args.font_size,
                color=args.color,
            )
            overlay = PdfReader(io.BytesIO(overlay_data)).pages[0]
            page.merge_page(overlay, over=True)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        with temporary.open("wb") as stream:
            writer.write(stream)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return len(reader.pages), total


def create_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description="Add line numbers to an existing PDF.")
    parser.add_argument("input", type=Path, help="Existing input PDF.")
    parser.add_argument("output", type=Path, help="New numbered PDF.")
    parser.add_argument(
        "--mode",
        choices=("text", "grid"),
        default="text",
        help="Detect text lines (default) or use a fixed grid.",
    )
    parser.add_argument(
        "--side",
        choices=("left", "right", "both"),
        default="left",
        help="Margin in which to place numbers (default: left).",
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=12,
        metavar="MM",
        help="Number position from the page edge (default: 12 mm).",
    )
    parser.add_argument(
        "--top-margin",
        type=float,
        default=15,
        metavar="MM",
        help="Unnumbered area at the top (default: 15 mm).",
    )
    parser.add_argument(
        "--bottom-margin",
        type=float,
        default=15,
        metavar="MM",
        help="Unnumbered area at the bottom (default: 15 mm).",
    )
    parser.add_argument(
        "--line-spacing",
        type=float,
        default=6,
        metavar="MM",
        help="Line spacing in grid mode (default: 6 mm).",
    )
    parser.add_argument(
        "--line-tolerance",
        type=float,
        default=3,
        metavar="PT",
        help="Vertical grouping tolerance in text mode (default: 3 pt).",
    )
    parser.add_argument(
        "--font-size",
        type=float,
        default=7,
        metavar="PT",
        help="Line-number font size (default: 7 pt).",
    )
    parser.add_argument(
        "--color",
        type=parse_color,
        default=parse_color("#666666"),
        metavar="#RRGGBB",
        help="Line-number color (default: #666666).",
    )
    parser.add_argument(
        "--start", type=int, default=1, help="First line number (default: 1)."
    )
    parser.add_argument(
        "--every",
        type=int,
        default=1,
        metavar="N",
        help="Number every Nth detected line (default: 1).",
    )
    parser.add_argument(
        "--restart-each-page",
        action="store_true",
        help="Restart at --start on every page.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output PDF.",
    )
    parser.add_argument("--password", help="Password for an encrypted input PDF.")
    return parser


def validate_arguments(args: argparse.Namespace) -> None:
    """Validate numeric command-line options."""
    positive = {
        "--margin": args.margin,
        "--top-margin": args.top_margin,
        "--bottom-margin": args.bottom_margin,
        "--line-spacing": args.line_spacing,
        "--line-tolerance": args.line_tolerance,
        "--font-size": args.font_size,
        "--every": args.every,
    }
    invalid = [name for name, value in positive.items() if value <= 0]
    if invalid:
        raise PdfLineNumberError(f"must be greater than zero: {', '.join(invalid)}")
    if args.start < 0:
        raise PdfLineNumberError("--start cannot be negative")


def main(argv: list[str] | None = None) -> int:
    """Run the command."""
    args = create_parser().parse_args(argv)
    try:
        validate_arguments(args)
        pages, line_numbers = add_line_numbers(args)
    except (PdfLineNumberError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Added {line_numbers} line numbers to {pages} page(s): {args.output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
