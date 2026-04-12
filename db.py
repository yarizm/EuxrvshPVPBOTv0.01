from __future__ import annotations

from euxrvsh_core.runtime import build_legacy_runtime

_runtime = build_legacy_runtime()
connection_pool = _runtime.repository.connection_pool


def get_cursor(commit: bool = False):
    return _runtime.repository.cursor(commit=commit)
