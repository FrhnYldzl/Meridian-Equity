"""
main.py — Meridian Equity V6.0 dispatcher.

Default: equity_preview_app:app yükler.
LEGACY_V57_MODE=true env var ile main_v57_archive:app yüklenebilir
(V5.7 legacy fallback).
"""

import os

_legacy_mode = os.getenv("LEGACY_V57_MODE", "false").lower() in ("true", "1", "yes")

if _legacy_mode:
    # V5.7 backward compatibility (rare)
    from main_v57_archive import app  # noqa: F401
else:
    # V6.0 default: equity preview app
    from equity_preview_app import app  # noqa: F401
