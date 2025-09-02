#!/usr/bin/env python3
"""Test runner for pyinj."""

import sys
import os
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Run pytest
import pytest

if __name__ == "__main__":
    # Run tests
    exit_code = pytest.main([
        "tests/",
        "-v",
        "--tb=short",
        "--color=yes",
        "-p", "no:cacheprovider",  # Disable cache
        "--no-cov",  # Disable coverage
    ])
    
    sys.exit(exit_code)