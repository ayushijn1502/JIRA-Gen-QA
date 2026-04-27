"""
Root-level conftest for the target_framework package.
Makes sure Python can import from target_framework.src.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
