#!/usr/bin/env python3
"""Собрать разъехавшиеся карточки лида в одну историю версий.

Имена вида ``423_смета_салон_v6_2026-10-13.xlsx`` схлопываются в ключ
``423_смета_салон.xlsx``. Файлы на диске не копируются и не удаляются:
история ссылается на те же stored_name. Одинаковый sha256 внутри группы
остаётся одной версией.

На проде — из каталога CRM и тем же Python, что у сервиса (база data/crm.db,
файлы в CRM_FILES_DIR или data/files):

    cd /root/crm
    /root/crm/venv/bin/python scripts/consolidate_versions.py --lead 423 --dry-run
    /root/crm/venv/bin/python scripts/consolidate_versions.py --all --dry-run
    /root/crm/venv/bin/python scripts/consolidate_versions.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.files import consolidate_versions, format_consolidation_plan, init_table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Собрать файлы лида с хвостом версии в одну цепочку lead_file_versions."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--lead", type=int, metavar="N", help="Только этот лид")
    group.add_argument("--all", action="store_true", help="Все лиды, у которых есть файлы или версии")
    parser.add_argument("--dry-run", action="store_true", help="Напечатать план и ничего не менять")
    args = parser.parse_args(argv)
    if not args.dry_run:
        init_table()
    plans = consolidate_versions(
        args.lead,
        all_leads=bool(args.all),
        dry_run=bool(args.dry_run),
    )
    print(format_consolidation_plan(plans, dry_run=bool(args.dry_run)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
