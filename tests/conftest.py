"""pytest setup that runs before test module imports.

web/jobs.py creates JOBS_DIR at import time. In production this is
/opt/clodex-check/web_data/jobs (root-owned), which a developer laptop or CI
container can't write to. We override the path with a per-session temp
dir so the import doesn't fail.
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "CLODEX_CHECK_JOBS_DIR",
    tempfile.mkdtemp(prefix="clodex-check-test-jobs-"),
)
os.environ.setdefault(
    "CLODEX_CHECK_WISHLIST_PATH",
    tempfile.mkstemp(prefix="clodex-check-test-wishlist-")[1],
)
