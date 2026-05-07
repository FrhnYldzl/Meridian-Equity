# ═══════════════════════════════════════════════════════════════════
# Dockerfile — Meridian Capital · Equity V6.0
# ═══════════════════════════════════════════════════════════════════
# Bu branch (equity/v6.0) SADECE equity modülünü içerir. Crypto kodu
# bu branch'te yoktur (crypto kendi branch'inde / repo'sunda kaldı).
#
# main.py = shim, equity_preview_app:app yükler.
# Eski V5.7 main.py logic'i main_v57_archive.py'de.
# ═══════════════════════════════════════════════════════════════════

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Tüm proje kodu — crypto yok bu branch'te, sadece equity
COPY server/ ./server/

ENV PYTHONPATH=/app/server
ENV PORT=8000
EXPOSE 8000

WORKDIR /app/server

# Equity V6.0 entrypoint — main shim equity_preview_app:app yükler
# JSON array form (signal handling clean, Docker linter warning-free)
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
