#!/usr/bin/env python3
"""Однократная синхронизация: проставить created_at из last_contact для всех лидов."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.database import sync_created_at_from_last_contact

if __name__ == "__main__":
    n = sync_created_at_from_last_contact()
    print(f"Обновлено записей: {n}")
