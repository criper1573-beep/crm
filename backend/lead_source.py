# Источник лида и причина отказа. Коды стабильны для API и бота.

from __future__ import annotations

import re
import sqlite3

class LeadSourceError(ValueError):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


# Порядок — порядок в отчёте и в карточке.
LEAD_SOURCES: tuple[tuple[str, str], ...] = (
    ("avito", "Авито"),
    ("remontfranchiz", "сайт ремонтфраншиз.рф"),
    ("flowcabinet", "flowcabinet.ru"),
    ("telegram", "Telegram"),
    ("referral", "рекомендация/сарафан"),
    ("repeat_client", "повторный клиент"),
    ("tender", "тендер/генподрядчик"),
    ("other", "другое"),
)

REJECTION_REASONS: tuple[tuple[str, str], ...] = (
    ("price", "дорого/нашли дешевле"),
    ("timing", "сроки"),
    ("not_our_profile", "не наш профиль работ"),
    ("small_volume", "маленький объём"),
    ("no_response", "клиент пропал/не отвечает"),
    ("postponed", "отложили проект"),
    ("other_contractor", "выбрали другого подрядчика не по цене"),
    ("other", "другое"),
)

_SOURCE_BY_CODE = dict(LEAD_SOURCES)
_REASON_BY_CODE = dict(REJECTION_REASONS)
_SOURCE_BY_LABEL = {label.casefold(): code for code, label in LEAD_SOURCES}
_REASON_BY_LABEL = {label.casefold(): code for code, label in REJECTION_REASONS}

# Текст уже в casefold. «не авито» не считается сигналом Авито.
_TEXT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("avito", re.compile(r"(?<!не\s)\b(?:авито|avito)\b")),
    ("remontfranchiz", re.compile(r"ремонт[\s\-]*франшиз|remontfranch")),
    ("flowcabinet", re.compile(r"flowcabinet")),
    ("telegram", re.compile(r"телеграм|telegram|\bтг\b|\btg\b")),
    ("referral", re.compile(r"сарафан|рекомендац")),
    ("repeat_client", re.compile(r"повторн\w*\s+клиент|повторн\w*\s+обращен")),
    ("tender", re.compile(r"тендер|генподряд")),
)


def is_drain(status: str | None) -> bool:
    return str(status or "").startswith("drain")


def fields_set(model) -> set[str]:
    if hasattr(model, "model_fields_set"):
        return set(model.model_fields_set)
    return set(getattr(model, "__fields_set__", ()))


def _canonical(value: str, by_code: dict[str, str], by_label: dict[str, str], unknown: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if text in by_code:
        return text
    folded = text.casefold()
    for code in by_code:
        if code.casefold() == folded:
            return code
    label_code = by_label.get(folded)
    if label_code:
        return label_code
    raise LeadSourceError(unknown)


def canonical_source(value: str) -> str:
    return _canonical(value, _SOURCE_BY_CODE, _SOURCE_BY_LABEL, "Unknown source")


def canonical_reason(value: str) -> str:
    return _canonical(value, _REASON_BY_CODE, _REASON_BY_LABEL, "Unknown rejection_reason")


def _merged(lead, previous: dict | None, name: str, canonical) -> str:
    """Явно переданное значение нормализуется. Пропущенное на PUT не затирает уже записанное."""
    if previous is not None and name not in fields_set(lead):
        return str(previous.get(name) or "").strip()
    return canonical(str(getattr(lead, name, "") or ""))


def apply_to_lead(lead, previous: dict | None) -> None:
    """Проверяет источник и причину отказа и записывает нормальные коды в модель.

    Причина обязательна, когда лид переводят в слив (drain_*). Старый слив с пустой
    причиной можно по-прежнему редактировать. «другое» требует непустой comment.
    """
    source = _merged(lead, previous, "source", canonical_source)
    reason = _merged(lead, previous, "rejection_reason", canonical_reason)
    comment = str(getattr(lead, "comment", "") or "")
    status = str(getattr(lead, "status", "") or "")
    prev_status = str((previous or {}).get("status") or "")
    prev_reason = str((previous or {}).get("rejection_reason") or "").strip()
    if reason == "other" and not comment.strip():
        raise LeadSourceError("comment is required when rejection_reason is other")
    if is_drain(status) and not reason:
        legacy = previous is not None and is_drain(prev_status) and not prev_reason
        if not legacy:
            raise LeadSourceError("rejection_reason is required")
    lead.source = source
    lead.rejection_reason = reason


def source_label(code: str) -> str:
    if not code:
        return "не указан"
    return _SOURCE_BY_CODE.get(code, code)


def reason_label(code: str) -> str:
    if not code:
        return "не указана"
    return _REASON_BY_CODE.get(code, code)


def attribution_counts(leads: list[dict]) -> dict:
    """Счётчики по уже отобранным лидам. Договор — client или repeat. Отказ — слив."""
    lead_counts: dict[str, int] = {}
    contract_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    contracts_total = 0
    rejections_total = 0
    for lead in leads:
        source = str(lead.get("source") or "").strip()
        lead_counts[source] = lead_counts.get(source, 0) + 1
        if lead.get("status") in ("client", "repeat"):
            contracts_total += 1
            contract_counts[source] = contract_counts.get(source, 0) + 1
        if is_drain(lead.get("status")):
            rejections_total += 1
            reason = str(lead.get("rejection_reason") or "").strip()
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    source_rows = []
    seen_sources: set[str] = set()
    for code, label in LEAD_SOURCES:
        seen_sources.add(code)
        source_rows.append({
            "source": code,
            "label": label,
            "leads": lead_counts.get(code, 0),
            "contracts": contract_counts.get(code, 0),
        })
    for code in sorted(key for key in lead_counts if key and key not in seen_sources):
        source_rows.append({
            "source": code,
            "label": code,
            "leads": lead_counts.get(code, 0),
            "contracts": contract_counts.get(code, 0),
        })
    if lead_counts.get(""):
        source_rows.append({
            "source": "",
            "label": "не указан",
            "leads": lead_counts[""],
            "contracts": contract_counts.get("", 0),
        })

    reason_rows = []
    seen_reasons: set[str] = set()
    for code, label in REJECTION_REASONS:
        seen_reasons.add(code)
        reason_rows.append({
            "reason": code,
            "label": label,
            "count": reason_counts.get(code, 0),
        })
    for code in sorted(key for key in reason_counts if key and key not in seen_reasons):
        reason_rows.append({
            "reason": code,
            "label": code,
            "count": reason_counts[code],
        })
    if reason_counts.get(""):
        reason_rows.append({
            "reason": "",
            "label": "не указана",
            "count": reason_counts[""],
        })

    return {
        "leads_total": len(leads),
        "contracts_total": contracts_total,
        "rejections_total": rejections_total,
        "leads_by_source": source_rows,
        "rejections_by_reason": reason_rows,
    }


def guess_source(lead: dict, notes: list[str] | None = None) -> tuple[str | None, str, list[str]]:
    """Один однозначный источник или ничего.

    Возвращает (код или None, откуда сигнал, все совпавшие коды).
    Несколько разных сигналов — не угадываем. «другое» само не ставится.
    """
    found: dict[str, str] = {}

    def add(code: str, why: str) -> None:
        found.setdefault(code, why)

    if str(lead.get("avito_chat_id") or "").strip():
        add("avito", "avito_chat_id")
    link = str(lead.get("avito_link") or "").casefold()
    if "avito" in link or "авито" in link:
        add("avito", "avito_link")

    parts = [lead.get("comment"), lead.get("description")]
    if notes:
        parts.extend(notes)
    blob = "\n".join(str(part) for part in parts if part).casefold()
    for code, pattern in _TEXT_RULES:
        if pattern.search(blob):
            add(code, "текст")

    codes = list(found)
    if len(codes) == 1:
        code = codes[0]
        return code, found[code], codes
    return None, "", codes


def plan_backfill(leads: list[dict], notes_by_lead: dict | None = None) -> dict:
    """Только пустой source. Уже заполненные строки не входят в updates."""
    notes_by_lead = notes_by_lead or {}
    updates = []
    ambiguous = []
    unchanged_empty = 0
    already_set = 0
    for lead in leads:
        current = str(lead.get("source") or "").strip()
        if current:
            already_set += 1
            continue
        lead_id = lead.get("id")
        notes = notes_by_lead.get(lead_id) or []
        code, why, codes = guess_source(lead, notes)
        if code:
            updates.append({
                "id": lead_id,
                "name": lead.get("name") or "",
                "source": code,
                "why": why,
            })
        elif len(codes) > 1:
            ambiguous.append({
                "id": lead_id,
                "name": lead.get("name") or "",
                "sources": codes,
            })
        else:
            unchanged_empty += 1
    return {
        "updates": updates,
        "ambiguous": ambiguous,
        "unchanged_empty": unchanged_empty,
        "already_set": already_set,
    }


def format_backfill_plan(plan: dict, *, dry_run: bool, applied: int | None = None) -> str:
    lines = []
    if dry_run:
        lines.append("dry-run, база не изменена")
    else:
        lines.append(f"записано {applied if applied is not None else len(plan['updates'])}")
    for row in plan["updates"]:
        lines.append(f"#{row['id']} {row['name']}: source={row['source']} ({row['why']})")
    for row in plan["ambiguous"]:
        joined = ", ".join(row["sources"])
        lines.append(f"неоднозначно #{row['id']} {row['name']}: {joined}")
    verb = "будет проставлено" if dry_run else "проставлено"
    lines.append(
        f"итого: {verb} {len(plan['updates'])}, неоднозначно {len(plan['ambiguous'])}, "
        f"без догадки {plan['unchanged_empty']}, уже заполнено {plan['already_set']}"
    )
    return "\n".join(lines)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def read_backfill_plan(conn: sqlite3.Connection) -> dict:
    columns = _table_columns(conn, "leads")
    if "source" not in columns:
        raise LeadSourceError("Нет колонки leads.source. Сначала миграция при старте CRM.")
    leads = []
    for row in conn.execute(
        """SELECT id, name, source, comment, description, avito_link, avito_chat_id
           FROM leads ORDER BY id"""
    ):
        leads.append({
            "id": row[0],
            "name": row[1] or "",
            "source": row[2] or "",
            "comment": row[3] or "",
            "description": row[4] or "",
            "avito_link": row[5] or "",
            "avito_chat_id": row[6] or "",
        })
    notes: dict[int, list[str]] = {}
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "notes" in tables:
        for lead_id, text in conn.execute("SELECT lead_id, text FROM notes"):
            notes.setdefault(lead_id, []).append(text or "")
    return plan_backfill(leads, notes)


def apply_backfill_plan(conn: sqlite3.Connection, plan: dict) -> int:
    """Пишет source только в пустые строки. Повторный запуск ничего не меняет."""
    applied = 0
    for row in plan["updates"]:
        cur = conn.execute(
            """UPDATE leads SET source = ?
               WHERE id = ? AND (source IS NULL OR TRIM(source) = '')""",
            (row["source"], row["id"]),
        )
        applied += cur.rowcount
    conn.commit()
    return applied
