#!/usr/bin/env python3
"""Run PDF Add Numbers directly from a source checkout."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

PROJECT_SOURCE = Path(__file__).resolve().parent / "src"
if str(PROJECT_SOURCE) not in sys.path:
    sys.path.insert(0, str(PROJECT_SOURCE))


if __name__ == "__main__":
    main = import_module("pdf_add_nmbrs.cli").main
    raise SystemExit(main())

