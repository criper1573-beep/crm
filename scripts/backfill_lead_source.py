#!/usr/bin/env python3
"""Проставить источник старым лидам, если он угадывается однозначно.

Смотрит комментарий, описание, заметки, ссылку Авито и avito_chat_id.
Несколько разных сигналов или пустой текст — source остаётся пустым.
Уже заполненный source не перезаписывается. Повторный запуск ничего не меняет.

По умолчанию dry-run: печатает план и базу не трогает. Запись только с --apply.
На проде не запускать, пока не посмотрен dry-run и не сделан бэкап.

    cd /root/crm
    /root/crm/venv/bin/python scripts/backfill_lead_source.py
    /root/crm/venv/bin/python scripts/backfill_lead_source.py --dry-run
    /root/crm/venv/bin/python scripts/backfill_lead_source.py --apply
    /root/crm/venv/bin/python scripts/backfill_lead_source.py --db /root/crm/data/crm.db --apply
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import DB_PATH
from backend.lead_source import LeadSourceError, apply_backfill_plan, format_backfill_plan, read_backfill_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Бэкфилл поля leads.source по тексту лида.")
    parser.add_argument("--dry-run", action="store_true", help="Напечатать, что будет проставлено, и не писать в базу")
    parser.add_argument("--apply", action="store_true", help="Записать source в пустые строки")
    parser.add_argument("--db", default="", help="Путь к crm.db. По умолчанию data/crm.db проекта")
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        print("Укажите либо --apply, либо --dry-run", file=sys.stderr)
        return 2
    dry_run = not args.apply
    path = Path(args.db) if args.db else DB_PATH
    if not path.exists():
        print(f"База не найдена: {path}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(path)
    try:
        try:
            plan = read_backfill_plan(conn)
        except LeadSourceError as exc:
            print(exc.detail, file=sys.stderr)
            return 1
        applied = None
        if not dry_run:
            applied = apply_backfill_plan(conn, plan)
    finally:
        conn.close()
    print(format_backfill_plan(plan, dry_run=dry_run, applied=applied))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
