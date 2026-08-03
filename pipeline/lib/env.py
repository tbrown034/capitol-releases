"""
One .env loader for every pipeline script that needs it.

Four scripts grew their own copies of the same six-line parse loop, and
the copies diverged on the detail that mattered: whether surrounding
quotes are stripped from values. The unstripped variants shipped twice
as real incidents -- a quoted OPENAI_API_KEY produced 401s that looked
like a bad key (2026-07-30), and a quoted DATABASE_URL made psycopg2
reject the DSN outright (2026-08-02). This module strips quotes, and
callers stop copying the loop.

Precedence is the caller's: files are applied in the order given, and
os.environ.setdefault means the first file to define a key wins --
matching how every existing copy behaved. Real environment variables
always beat files.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repo root: pipeline/lib/env.py -> lib -> pipeline -> root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE_ENV = REPO_ROOT / "pipeline" / ".env"
ROOT_ENV_LOCAL = REPO_ROOT / ".env.local"
ROOT_ENV = REPO_ROOT / ".env"


def load_env(*paths: Path) -> None:
    """Load KEY=VALUE lines from each existing file, in order.

    Earlier files win over later ones; the process environment wins over
    everything. Values keep internal characters untouched -- only one
    layer of surrounding single or double quotes is removed.
    """
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)
