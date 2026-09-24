"""Keeps the plugin self-contained: importable without installing, and invisible to the repo-wide `pytest` run.

Run this plugin's suite from the repo root with:  python3 -m pytest plugins/curves -q
(that picks up plugins/curves/pytest.ini, so config.rootpath is this directory).
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PLUGIN_ROOT.parents[1]  # plugins/curves -> repo root; only used for READ-ONLY `import engine.*` in audits

for _p in (PLUGIN_ROOT, REPO_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def pytest_ignore_collect(collection_path, config):
    """The repo-wide run (rootdir = repo root) must not collect this plugin's ~3000 tests and strict xfails."""
    if Path(config.rootpath).resolve() != PLUGIN_ROOT:
        return True
    return None
