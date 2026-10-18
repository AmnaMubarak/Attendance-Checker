"""Pytest configuration at the project root.

Adding this file (even empty) makes the project root the pytest ``rootdir``
and places it on ``sys.path``, so ``from attendance_checker import ...``
works without needing an editable install.
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
