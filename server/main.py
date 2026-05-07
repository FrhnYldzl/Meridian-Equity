"""
main.py — Meridian Equity V6.0 dispatcher.

Bu dosya equity/v6.0 branch'i içindir. Sadece equity_preview_app'ı
yükler — crypto kodu BU BRANCH'TE YOKTUR.

Eski V5.7 main.py logic'i main_v57_archive.py'de saklanıyor.
İhtiyaç olursa LEGACY_V57_MODE=true env var ile çağrılabilir.
"""

import os

_legacy_mode = os.getenv("LEGACY_V57_MODE", "false").lower() in ("true", "1", "yes")

if _legacy_mode:
    # V5.7 backward compatibility (rare)
    from main_v57_archive import app  # noqa: F401
else:
    # V6.0 default: equity preview app
    from equity_preview_app import app  # noqa: F401
