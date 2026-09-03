"""Compatibility entry point for the unified Ski Predictor backend."""

from __future__ import annotations

import sys
from pathlib import Path


API_SOURCE = Path(__file__).resolve().parents[2] / "services" / "api" / "src"
sys.path.insert(0, str(API_SOURCE))

from server import main  # noqa: E402


if __name__ == "__main__":
    main()
