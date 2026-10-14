"""Pytest configuration for DropLink tests."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def temp_data_dir():
    """Use a temporary directory for data during tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["DROPLINK_DATA_DIR"] = tmpdir
        yield tmpdir
        del os.environ["DROPLINK_DATA_DIR"]


@pytest.fixture
def data_dir(temp_data_dir):
    """Get the temporary data directory path."""
    return Path(temp_data_dir)
