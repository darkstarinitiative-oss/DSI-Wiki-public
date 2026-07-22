from __future__ import annotations

import os
import sys

def add_parent_dir():
    """Add the project root directory to sys.path so relative imports resolve correctly."""
    # Determine the parent of the current script's directory (i.e., _Python)
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

# Run once when this module is imported
add_parent_dir()
