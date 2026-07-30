# PDF Add Numbers

PDF Add Numbers creates a review copy of an existing PDF with line numbers in
the page margin. It can detect selectable text lines or place numbers on a
fixed grid for scanned documents.

The application is fully standalone and does not depend on another project.
It can be installed as a Python command or built as a single executable for
customers who do not have Python installed.

## Requirements

- Python 3.11 or newer when running from source
- No external programs at runtime

## Development installation

Create a virtual environment and install the project:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

On Windows, activate the environment with:

```powershell
.venv\Scripts\activate
```

## Usage

Detect horizontal text lines and number them in the left margin:

```bash
pdf-line-numbers input.pdf numbered.pdf
```

The root script provides the same interface:

```bash
python pdf_line_numbers.py input.pdf numbered.pdf
```

Put numbers in both margins and restart numbering on every page:

```bash
pdf-line-numbers input.pdf numbered.pdf \
  --side both \
  --restart-each-page
```

Use a fixed vertical grid for scans or PDFs without selectable text:

```bash
pdf-line-numbers scan.pdf numbered.pdf \
  --mode grid \
  --line-spacing 6
```

The source PDF is never overwritten. An existing output is preserved unless
`--overwrite` is supplied. The output is first written to a temporary file, so
a failed operation does not leave a partial PDF.

Run `pdf-line-numbers --help` for all options.

## Build a standalone executable

Install the development dependencies and run:

```bash
python scripts/build_executable.py
```

The executable and its SHA-256 checksum are written to a platform-specific
directory below `dist/executables/`. PyInstaller builds only for the operating
system on which it runs, so Windows releases must be built on Windows and macOS
releases on macOS.

The executable contains Python and all required packages. Customers can use it
without installing Python.

## Quality checks

```bash
pytest
ruff check .
mypy src
```

## License

No public license has been selected yet. Add an appropriate software license
before distributing the project for customer use.

