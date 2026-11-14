"""pytest bootstrap: make the `wt` package (tools/wt) importable.

The agent module computes its own repo-root paths, so tests never depend on
the CWD; this conftest only fixes the import path.
"""
from __future__ import annotations

import os
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
