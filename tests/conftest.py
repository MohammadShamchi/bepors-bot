"""
Shared pytest fixtures. Makes the project root importable so every test
can import `from i18n import t` etc. without path fiddling.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Ensure env vars are set before any test imports bot.py
os.environ.setdefault("TELEGRAM_TOKEN", "test:token")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("LOG_SALT", "test-salt")
os.environ.setdefault("DB_PATH", "/tmp/bepors-test.db")
