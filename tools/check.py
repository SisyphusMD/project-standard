#!/usr/bin/env python3
"""Convenience wrapper: check a consumer from the standard repo.

The real implementation is `shared/packaging/check-standard-sync.py`, because it is vendored INTO
each consumer and run by that project's CI. Keeping one implementation means the checker cannot
drift from the thing it checks.

    tools/check.py ../whiskerless
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "shared" / "packaging" / "check-standard-sync.py"

if __name__ == "__main__":
    sys.argv = [str(TARGET), *sys.argv[1:]]
    runpy.run_path(str(TARGET), run_name="__main__")
