#!/usr/bin/env python3
"""Topic operations module."""

import sys
from pathlib import Path

# Resolve the directory containing this script (topic_ops.py)
_scripts_root = str(Path(__file__).parent.parent)

# Add scripts root to sys.path to ensure relative imports work correctly
if _scripts_root not in sys.path:
    sys.path.insert(0, _scripts_root)


from HTTPService.api_app import load_instances
