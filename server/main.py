"""
main.py — V6.0 dispatcher / shim.

Bu dosya SADECE worktree branch'inde (claude/v5.8-abstract-bases) shim'dir.
Main branch'teki main.py V5.7 production'ı (devine-laughter) için orijinal
kalır, dokunulmadı.

Sebep: Railway dashboard'da bazen 'uvicorn main:app' komutu otomatik
inject ediliyor (Procfile auto-detect). Dashboard ayarını manuel
silemediğimiz durumda, main.py'i shim yaparak dashboard cmd'sinin
de doğru app'i yüklemesini sağlıyoruz.

Davranış:
  MERIDIAN_MODULE=equity (default)  → equity_preview_app.app
  MERIDIAN_MODULE=crypto              → crypto_preview_app.app
  MERIDIAN_MODULE=v5_7_legacy         → main_v57_archive.app (V5.7 backward)

Dockerfile.equity ve Dockerfile.crypto'nun CMD'leri zaten doğru app'i
çağırır. Bu shim sadece dashboard override'ı için sigorta.

Merge sırasında: main branch'e merge ederken main.py için manuel karar:
  - V5.7 production main'de kalsın → main branch'in main.py'sini koru
  - Bu shim'i main_dispatcher.py olarak rename et
"""

import os

_module = os.getenv("MERIDIAN_MODULE", "equity").lower()

if _module == "crypto":
    from crypto_preview_app import app  # noqa: F401
elif _module == "v5_7_legacy":
    from main_v57_archive import app  # noqa: F401
else:
    # Default: equity V6.0
    from equity_preview_app import app  # noqa: F401
