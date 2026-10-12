"""Имя с хвостом версии — ключ одной цепочки, а не новая карточка."""

import hashlib
import io
import sqlite3
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.files import (
    category_from_name,
    consolidate_versions,
    normalize_version_name,
    plan_version_consolidation,
)
from scripts.consolidate_versions import main
from tests.test_file_versions import AUTH, _create, _disk, _files_count, _history, _post_version

NAMES = [
    ("423_смета_салон_v6_2026-10-13.xlsx", "423_смета_салон.xlsx"),
    ("423_смета_салон_v6.xlsx", "423_смета_салон.xlsx"),
    ("423_смета_салон-v6.xlsx", "423_смета_салон.xlsx"),
    ("423_смета_салон v6.xlsx", "423_смета_салон.xlsx"),
    ("423_смета_салон_2026-10-13.xlsx", "423_смета_салон.xlsx"),
    ("423_смета_салон_v10_2026-01-02.xlsx", "423_смета_салон.xlsx"),
    ("Смета_Салон_V12.XLSX", "Смета_Салон.XLSX"),
    ("Отчёт_V3.DOCX", "Отчёт.DOCX"),
    ("plan.txt", "plan.txt"),
    ("file_v2_notes.xlsx", "file_v2_notes.xlsx"),
    ("report_2026-10-13_final.xlsx", "report_2026-10-13_final.xlsx"),
    ("My_File_v06.pdf", "My_File.pdf"),
]

CATEGORIES = [
    ("423_смета_салон_v6_2026-10-13.xlsx", "смета"),
    ("423_КП_салон_v1.pdf", "кп"),
    ("423_кп_объект.docx", "кп"),
    ("ведомость_работ.xlsx", "ведомость"),
    ("15_исходники_обмер.pdf", "план"),
    ("план_этажа.dwg", "план"),
    ("материалы.xlsx", "материалы"),
    ("договор_подряда.pdf", "договор"),
    ("фото_объекта.jpg", "фото"),
    ("photo.png", "прочее"),
    ("random.bin", "прочее"),
]


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    db_path = tmp_path / "crm.db"
    files_dir = tmp_path / "files"
    monkeypatch.setenv("CRM_FILES_DIR", str(files_dir))
    import backend.database as database
    import backend.files as files

    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setattr(files, "FILES_DIR", files_dir)
    return db_path, files_dir


@pytest.fixture()
def client(storage, monkeypatch):
    monkeypatch.delenv("CRM_BASIC_USER", raising=False)
    monkeypatch.delenv("CRM_BASIC_PASSWORD", raising=False)
    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("raw, expected", NAMES)
def test_normalize_version_name_strips_tail_and_keeps_case(raw, expected):
    assert normalize_version_name(raw) == expected
    assert normalize_version_name(expected) == expected


@pytest.mark.parametrize("raw, expected", CATEGORIES)
def test_category_from_name_prefix(raw, expected):
    assert category_from_name(raw) == expected


def test_consolidate_script_requires_lead_or_all():
    with pytest.raises(SystemExit) as caught:
        main([])
    assert caught.value.code == 2


def test_v7_under_old_name_joins_the_same_chain(client, storage):
    _db_path, files_dir = storage
    lead_id = _create(client, "Салон")

    first = _post_version(
        client,
        lead_id,
        b"v6",
        upload_name="423_смета_салон_v6_2026-10-13.xlsx",
        filename="423_смета_салон_v6_2026-10-13.xlsx",
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["skipped"] is False
    assert body["filename"] == "423_смета_салон.xlsx"
    assert body["version"] == 1
    assert body["original_name"] == "423_смета_салон_v6_2026-10-13.xlsx"
    assert body["comment"] == "423_смета_салон_v6_2026-10-13.xlsx"

    second = _post_version(
        client,
        lead_id,
        b"v7",
        upload_name="ignored.xlsx",
        filename="423_смета_салон_v7.xlsx",
        comment="правка",
    )
    assert second.status_code == 200, second.text
    assert second.json()["version"] == 2
    assert second.json()["filename"] == "423_смета_салон.xlsx"
    assert second.json()["comment"] == "правка"
    assert second.json()["original_name"] == "423_смета_салон_v7.xlsx"

    third = _post_version(
        client, lead_id, b"dash", upload_name="a.xlsx", filename="423_смета_салон-v8.xlsx"
    )
    fourth = _post_version(
        client, lead_id, b"space", upload_name="a.xlsx", filename="423_смета_салон v9.xlsx"
    )
    fifth = _post_version(
        client,
        lead_id,
        b"date",
        upload_name="a.xlsx",
        filename="423_смета_салон_2026-12-01.xlsx",
    )
    assert third.json()["version"] == 3
    assert fourth.json()["version"] == 4
    assert fifth.json()["version"] == 5
    assert third.json()["filename"] == fourth.json()["filename"] == fifth.json()["filename"]
    assert fifth.json()["filename"] == "423_смета_салон.xlsx"

    skipped = _post_version(
        client,
        lead_id,
        b"date",
        upload_name="a.xlsx",
        filename="423_смета_салон_v10_2026-12-02.xlsx",
    )
    assert skipped.json() == {"skipped": True, "version": 5}
    assert len(_disk(files_dir, lead_id)) == 5

    listed = client.get(f"/api/leads/{lead_id}/files").json()
    salon = [item for item in listed if item["original_name"] == "423_смета_салон.xlsx"]
    assert len(salon) == 1
    assert client.get(salon[0]["url"]).content == b"date"
    assert _files_count(client, lead_id) == 1

    history = _history(client, lead_id, filename="423_смета_салон_v7.xlsx")
    assert [item["version"] for item in history] == [5, 4, 3, 2, 1]
    assert client.get(f"/api/leads/{lead_id}/files/versions/{history[-1]['id']}/raw", auth=AUTH).content == b"v6"

    other = _post_version(
        client, lead_id, b"kitchen", upload_name="a.xlsx", filename="423_смета_кухня_v1.xlsx"
    )
    assert other.json()["filename"] == "423_смета_кухня.xlsx"
    assert other.json()["version"] == 1
    assert _files_count(client, lead_id) == 2

    ui = client.post(
        f"/api/leads/{lead_id}/files",
        files=[("files", ("423_смета_салон_v11.xlsx", b"from-ui", "application/octet-stream"))],
    )
    assert ui.status_code == 200, ui.text
    assert ui.json()[0]["original_name"] == "423_смета_салон.xlsx"
    assert _files_count(client, lead_id) == 2
    ui_row = next(item for item in _history(client, lead_id, filename="423_смета_салон.xlsx") if item["author"] == "ui")
    assert ui_row["version"] == 6
    assert ui_row["original_name"] == "423_смета_салон_v11.xlsx"
    assert client.get(salon[0]["url"]).content == b"from-ui"

    again = client.post(
        f"/api/leads/{lead_id}/files",
        files=[("files", ("423_смета_салон_v12.xlsx", b"from-ui", "application/octet-stream"))],
    )
    assert again.status_code == 200, again.text
    assert again.json()[0]["id"] == ui.json()[0]["id"]
    assert len(_history(client, lead_id, filename="423_смета_салон_v12_2026-10-13.xlsx")) == 6
    assert len(_disk(files_dir, lead_id)) == 7
    assert _files_count(client, lead_id) == 2


def test_ui_upload_writes_version_and_skips_same_hash(client, storage):
    _db_path, files_dir = storage
    lead_id = _create(client, "Договор")
    uploaded = client.post(
        f"/api/leads/{lead_id}/files",
        files=[("files", ("15_договор_v2_2026-10-01.pdf", b"contract", "application/pdf"))],
    )
    assert uploaded.status_code == 200, uploaded.text
    card = uploaded.json()[0]
    assert card["original_name"] == "15_договор.pdf"
    assert client.get(card["url"]).content == b"contract"
    assert _files_count(client, lead_id) == 1
    history = _history(client, lead_id)
    assert len(history) == 1
    assert history[0]["author"] == "ui"
    assert history[0]["filename"] == "15_договор.pdf"
    assert history[0]["original_name"] == "15_договор_v2_2026-10-01.pdf"
    assert history[0]["comment"] == "15_договор_v2_2026-10-01.pdf"
    assert history[0]["category"] == "договор"
    assert history[0]["version"] == 1
    assert len(_disk(files_dir, lead_id)) == 1

    same = client.post(
        f"/api/leads/{lead_id}/files",
        files=[("files", ("15_договор_v3.pdf", b"contract", "application/pdf"))],
    )
    assert same.status_code == 200, same.text
    assert same.json()[0]["id"] == card["id"]
    assert len(_history(client, lead_id)) == 1
    assert len(_disk(files_dir, lead_id)) == 1
    assert _files_count(client, lead_id) == 1

    nxt = client.post(
        f"/api/leads/{lead_id}/files",
        files=[("files", ("15_договор v4.pdf", b"contract-2", "application/pdf"))],
    )
    assert nxt.status_code == 200, nxt.text
    assert nxt.json()[0]["id"] == card["id"]
    assert nxt.json()[0]["original_name"] == "15_договор.pdf"
    assert client.get(card["url"]).content == b"contract-2"
    versions = _history(client, lead_id, filename="15_договор_v4.pdf")
    assert [item["version"] for item in versions] == [2, 1]
    assert versions[0]["author"] == "ui"
    assert _files_count(client, lead_id) == 1
    assert len(_disk(files_dir, lead_id)) == 2
    assert client.get(
        f"/api/leads/{lead_id}/files/versions/{versions[1]['id']}/raw", auth=AUTH
    ).content == b"contract"


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _stored(number: int) -> str:
    return f"{number:032x}"


def _write(files_dir: Path, lead_id: int, stored: str, content: bytes) -> None:
    folder = files_dir / str(lead_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / stored).write_bytes(content)


def _dump(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        files = conn.execute("SELECT * FROM lead_files ORDER BY id").fetchall()
        versions = conn.execute("SELECT * FROM lead_file_versions ORDER BY id").fetchall()
        leads = conn.execute("SELECT id, updated_at FROM leads ORDER BY id").fetchall()
    finally:
        conn.close()
    return {"files": files, "versions": versions, "leads": leads}


def _bytes_map(files_dir: Path, lead_id: int) -> dict[str, bytes]:
    folder = files_dir / str(lead_id)
    return {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}


def test_consolidate_orders_by_version_number_before_created_at(client, storage):
    db_path, files_dir = storage
    lead_id = _create(client, "Порядок")
    later = _stored(1)
    earlier = _stored(2)
    _write(files_dir, lead_id, later, b"from-v1")
    _write(files_dir, lead_id, earlier, b"from-v2")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO lead_files (lead_id, original_name, stored_name, mime_type, size, created_at, sha256)
        VALUES (?, 'doc_v1.txt', ?, 'text/plain', 8, '2026-06-01 00:00:00', ?)
        """,
        (lead_id, later, _sha(b"from-v1")),
    )
    conn.execute(
        """
        INSERT INTO lead_files (lead_id, original_name, stored_name, mime_type, size, created_at, sha256)
        VALUES (?, 'doc_v2.txt', ?, 'text/plain', 8, '2026-01-01 00:00:00', ?)
        """,
        (lead_id, earlier, _sha(b"from-v2")),
    )
    conn.commit()
    conn.close()

    consolidate_versions(lead_id)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        SELECT version, original_name FROM lead_file_versions
        WHERE lead_id = ? ORDER BY version
        """,
        (lead_id,),
    ).fetchall()
    card = conn.execute(
        "SELECT original_name, version, sha256 FROM lead_files WHERE lead_id = ?",
        (lead_id,),
    ).fetchone()
    conn.close()
    assert rows == [(1, "doc_v1.txt"), (2, "doc_v2.txt")]
    assert card[0] == "doc.txt"
    assert card[1] == 2
    assert card[2] == _sha(b"from-v2")
    assert _bytes_map(files_dir, lead_id) == {later: b"from-v1", earlier: b"from-v2"}


def test_consolidate_lead_423_shape_and_dry_run(client, storage):
    """Как лид 423: v1–v6 сметы, v1–v3 КП, дубли по хешу и ещё две карточки."""
    db_path, files_dir = storage
    lead_id = _create(client, "423")
    smeta = {
        0: b"smeta-existing",
        1: b"smeta-v1",
        2: b"smeta-v2",
        3: b"smeta-v3",
        5: b"smeta-v5",
        6: b"smeta-v6",
    }
    kp = {1: b"kp-v1", 2: b"kp-v2", 3: b"kp-v3"}
    contract = b"dogovor-bytes"
    photo = b"photo-salon"

    names = {
        1: "423_смета_салон_v1_2026-09-01.xlsx",
        2: "423_смета_салон_v2_2026-09-05.xlsx",
        3: "423_смета_салон_v3_2026-09-10.xlsx",
        4: "423_смета_салон_v4_2026-09-12.xlsx",
        5: "423_смета_салон_v5_2026-09-20.xlsx",
        6: "423_смета_салон_v6_2026-10-13.xlsx",
    }
    stamps = {
        1: "2026-09-01 10:00:00",
        2: "2026-09-05 10:00:00",
        3: "2026-09-10 10:00:00",
        4: "2026-09-12 10:00:00",
        5: "2026-09-20 10:00:00",
        6: "2026-10-13 10:00:00",
    }
    stored = {number: _stored(number) for number in range(1, 16)}
    # 1..6 смета (4 — дубль v2), 7..10 КП, 11 договор, 12 фото, 13 уже существующая версия сметы.
    for number in (1, 2, 3, 5, 6):
        _write(files_dir, lead_id, stored[number], smeta[number])
    _write(files_dir, lead_id, stored[4], smeta[2])
    for number, content in ((7, kp[1]), (8, kp[2]), (9, kp[3]), (10, kp[3])):
        _write(files_dir, lead_id, stored[number], content)
    _write(files_dir, lead_id, stored[11], contract)
    _write(files_dir, lead_id, stored[12], photo)
    _write(files_dir, lead_id, stored[13], smeta[0])

    conn = sqlite3.connect(db_path)
    for number in (1, 2, 3, 5, 6):
        conn.execute(
            """
            INSERT INTO lead_files
                (lead_id, original_name, stored_name, mime_type, size, created_at, sha256)
            VALUES (?, ?, ?, 'application/vnd.ms-excel', ?, ?, ?)
            """,
            (lead_id, names[number], stored[number], len(smeta[number]), stamps[number], _sha(smeta[number])),
        )
    conn.execute(
        """
        INSERT INTO lead_files
            (lead_id, original_name, stored_name, mime_type, size, created_at, sha256)
        VALUES (?, ?, ?, 'application/vnd.ms-excel', ?, ?, NULL)
        """,
        (lead_id, names[4], stored[4], len(smeta[2]), stamps[4]),
    )
    kp_rows = [
        (7, "423_КП_салон_v1.pdf", kp[1], "2026-08-01 10:00:00"),
        (8, "423_КП_салон_v2.pdf", kp[2], "2026-08-02 10:00:00"),
        (9, "423_КП_салон_v3_2026-10-01.pdf", kp[3], "2026-08-03 10:00:00"),
        (10, "423_КП_салон_v3.pdf", kp[3], "2026-08-04 10:00:00"),
    ]
    for number, name, content, stamp in kp_rows:
        conn.execute(
            """
            INSERT INTO lead_files
                (lead_id, original_name, stored_name, mime_type, size, created_at, sha256)
            VALUES (?, ?, ?, 'application/pdf', ?, ?, ?)
            """,
            (lead_id, name, stored[number], len(content), stamp, _sha(content)),
        )
    conn.execute(
        """
        INSERT INTO lead_files
            (lead_id, original_name, stored_name, mime_type, size, created_at, sha256)
        VALUES (?, '423_договор.pdf', ?, 'application/pdf', ?, '2026-07-01 10:00:00', ?)
        """,
        (lead_id, stored[11], len(contract), _sha(contract)),
    )
    conn.execute(
        """
        INSERT INTO lead_files
            (lead_id, original_name, stored_name, mime_type, size, created_at, sha256)
        VALUES (?, '423_фото_салона.jpg', ?, 'image/jpeg', ?, '2026-07-02 10:00:00', ?)
        """,
        (lead_id, stored[12], len(photo), _sha(photo)),
    )
    conn.execute(
        """
        INSERT INTO lead_file_versions
            (lead_id, filename, version, category, author, comment, original_name,
             sha256, size, stored_name, created_at)
        VALUES (?, '423_смета_салон.xlsx', 1, 'чертёж', 'бот', 'уже в истории',
                '423_смета_салон.xlsx', ?, ?, ?, '2026-08-15 09:00:00')
        """,
        (lead_id, _sha(smeta[0]), len(smeta[0]), stored[13]),
    )
    conn.execute(
        """
        INSERT INTO lead_file_versions
            (lead_id, filename, version, category, author, comment, original_name,
             sha256, size, stored_name, created_at)
        VALUES (?, '423_КП_салон_v1.pdf', 1, 'прочее', 'бот', '',
                '423_КП_салон_v1.pdf', ?, ?, ?, '2026-08-01 10:00:00')
        """,
        (lead_id, _sha(kp[1]), len(kp[1]), stored[7]),
    )
    conn.commit()
    conn.close()

    before_rows = _dump(db_path)
    before_bytes = _bytes_map(files_dir, lead_id)
    assert len(before_bytes) == 13

    plan = consolidate_versions(lead_id, dry_run=True)
    assert _dump(db_path) == before_rows
    assert _bytes_map(files_dir, lead_id) == before_bytes
    changed = [item for item in plan if item["changed"]]
    assert len(changed) == 4
    assert all(item["card"] for item in changed)
    smeta_plan = next(item for item in plan if item["filename"] == "423_смета_салон.xlsx")
    kp_plan = next(item for item in plan if item["filename"] == "423_КП_салон.pdf")
    assert smeta_plan["category"] == "смета"
    assert [item["original_name"] for item in smeta_plan["kept"]] == [
        "423_смета_салон.xlsx",
        names[1],
        names[2],
        names[3],
        names[5],
        names[6],
    ]
    assert [item["original_name"] for item in smeta_plan["collapsed"]] == [names[4]]
    assert kp_plan["category"] == "кп"
    assert [item["original_name"] for item in kp_plan["kept"]] == [
        "423_КП_салон_v1.pdf",
        "423_КП_салон_v2.pdf",
        "423_КП_салон_v3_2026-10-01.pdf",
    ]
    assert [item["original_name"] for item in kp_plan["collapsed"]] == ["423_КП_салон_v3.pdf"]

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert main(["--lead", str(lead_id), "--dry-run"]) == 0
    printed = buffer.getvalue()
    assert "dry-run" in printed
    assert "423_смета_салон.xlsx" in printed
    assert "423_КП_салон.pdf" in printed
    all_buffer = io.StringIO()
    with redirect_stdout(all_buffer):
        assert main(["--all", "--dry-run"]) == 0
    assert "423_смета_салон.xlsx" in all_buffer.getvalue()
    assert "dry-run" in all_buffer.getvalue()
    assert _dump(db_path) == before_rows
    assert _bytes_map(files_dir, lead_id) == before_bytes

    consolidate_versions(lead_id)
    assert _bytes_map(files_dir, lead_id) == before_bytes
    assert _files_count(client, lead_id) == 4

    conn = sqlite3.connect(db_path)
    cards = conn.execute(
        """
        SELECT original_name, version, sha256, category FROM lead_files
        WHERE lead_id = ?
        """,
        (lead_id,),
    ).fetchall()
    smeta_versions = conn.execute(
        """
        SELECT version, original_name, author, comment, sha256, stored_name
        FROM lead_file_versions
        WHERE lead_id = ? AND filename = ?
        ORDER BY version
        """,
        (lead_id, "423_смета_салон.xlsx"),
    ).fetchall()
    kp_versions = conn.execute(
        """
        SELECT version, original_name, author, category, sha256, stored_name
        FROM lead_file_versions
        WHERE lead_id = ? AND filename = ?
        ORDER BY version
        """,
        (lead_id, "423_КП_салон.pdf"),
    ).fetchall()
    version_total = conn.execute(
        "SELECT COUNT(*) FROM lead_file_versions WHERE lead_id = ?", (lead_id,)
    ).fetchone()[0]
    conn.close()

    assert set(cards) == {
        ("423_договор.pdf", 1, _sha(contract), "договор"),
        ("423_КП_салон.pdf", 3, _sha(kp[3]), "кп"),
        ("423_смета_салон.xlsx", 6, _sha(smeta[6]), "смета"),
        ("423_фото_салона.jpg", 1, _sha(photo), "фото"),
    }
    assert version_total == 11
    assert [(row[0], row[1], row[2]) for row in smeta_versions] == [
        (1, "423_смета_салон.xlsx", "бот"),
        (2, names[1], "consolidate"),
        (3, names[2], "consolidate"),
        (4, names[3], "consolidate"),
        (5, names[5], "consolidate"),
        (6, names[6], "consolidate"),
    ]
    assert smeta_versions[0][3] == "уже в истории"
    assert smeta_versions[0][4] == _sha(smeta[0])
    assert smeta_versions[5][4] == _sha(smeta[6])
    assert smeta_versions[2][5] == stored[2]
    assert kp_versions[0][2] == "бот"
    assert kp_versions[0][3] == "кп"
    assert kp_versions[0][5] == stored[7]
    assert [(row[0], row[1]) for row in kp_versions] == [
        (1, "423_КП_салон_v1.pdf"),
        (2, "423_КП_салон_v2.pdf"),
        (3, "423_КП_салон_v3_2026-10-01.pdf"),
    ]
    assert all(row[3] == "кп" for row in kp_versions)

    listed = client.get(f"/api/leads/{lead_id}/files").json()
    assert len(listed) == 4
    card = next(item for item in listed if item["original_name"] == "423_смета_салон.xlsx")
    assert client.get(card["url"]).content == smeta[6]
    photo_card = next(item for item in listed if item["original_name"] == "423_фото_салона.jpg")
    assert client.get(photo_card["url"]).content == photo
    history = _history(client, lead_id, filename="423_смета_салон_v6_2026-10-13.xlsx")
    assert [item["version"] for item in history] == [6, 5, 4, 3, 2, 1]
    assert client.get(f"/api/leads/{lead_id}/files/versions/{history[0]['id']}/raw", auth=AUTH).content == smeta[6]
    assert client.get(f"/api/leads/{lead_id}/files/versions/{history[-1]['id']}/raw", auth=AUTH).content == smeta[0]

    settled = _dump(db_path)
    again = consolidate_versions(lead_id)
    assert again
    assert all(not item["changed"] for item in plan_version_consolidation(lead_id))
    assert _dump(db_path) == settled
    assert _bytes_map(files_dir, lead_id) == before_bytes
