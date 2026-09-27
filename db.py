import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS operative_notes (
    id INTEGER PRIMARY KEY,
    case_id TEXT UNIQUE,
    operation_date TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'completed' CHECK(status IN ('draft', 'completed')),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision INTEGER NOT NULL DEFAULT 1,
    creation_key TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS operative_diagrams (
    id INTEGER PRIMARY KEY,
    operative_note_id INTEGER NOT NULL REFERENCES operative_notes(id) ON DELETE CASCADE,
    diagram_type TEXT NOT NULL,
    base_template TEXT NOT NULL,
    state_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS diagram_objects (
    id INTEGER PRIMARY KEY,
    operative_diagram_id INTEGER NOT NULL REFERENCES operative_diagrams(id) ON DELETE CASCADE,
    object_type TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    data_json TEXT NOT NULL
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db():
    db = get_db()
    columns = {row["name"] for row in db.execute("PRAGMA table_info(operative_notes)")}
    diagram_unique = any(row["unique"] for row in db.execute("PRAGMA index_list(operative_diagrams)"))
    if (columns and "status" not in columns) or diagram_unique:
        # SQLite backup API captures a consistent snapshot, including any WAL pages.
        location = current_app.config["DATABASE"]
        if location != ":memory:":
            backup = Path(str(location) + ".pre-diagrams-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + ".bak")
            with sqlite3.connect(backup) as destination:
                db.backup(destination)
    if columns and "status" not in columns:
        # SQLite cannot remove NOT NULL in place. Keep IDs and child rows intact.
        db.execute("PRAGMA foreign_keys = OFF")
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE operative_notes_new (
                id INTEGER PRIMARY KEY, case_id TEXT UNIQUE,
                operation_date TEXT NOT NULL, data_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'completed' CHECK(status IN ('draft', 'completed')),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                revision INTEGER NOT NULL DEFAULT 1, creation_key TEXT UNIQUE
            )""")
            db.execute("""INSERT INTO operative_notes_new
                (id, case_id, operation_date, data_json, created_at, updated_at)
                SELECT id, case_id, operation_date, data_json, created_at, created_at FROM operative_notes""")
            db.execute("DROP TABLE operative_notes")
            db.execute("ALTER TABLE operative_notes_new RENAME TO operative_notes")
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("DB移行時の外部キー検証に失敗しました。")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.execute("PRAGMA foreign_keys = ON")
    if diagram_unique:
        db.execute("PRAGMA foreign_keys = OFF")
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE operative_diagrams_new (
                id INTEGER PRIMARY KEY,
                operative_note_id INTEGER NOT NULL REFERENCES operative_notes(id) ON DELETE CASCADE,
                diagram_type TEXT NOT NULL, base_template TEXT NOT NULL, state_json TEXT NOT NULL
            )""")
            db.execute("INSERT INTO operative_diagrams_new SELECT * FROM operative_diagrams")
            db.execute("DROP TABLE operative_diagrams")
            db.execute("ALTER TABLE operative_diagrams_new RENAME TO operative_diagrams")
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("手術図のDB移行に失敗しました。")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA)


class SaveConflict(ValueError):
    pass


def save_note(note, diagrams, status="completed", note_id=None, revision=None, step=0, creation_key=None):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data = json.dumps({**note, "_step": step}, ensure_ascii=False)
    with db:
        if note_id is None:
            note_id = db.execute("""INSERT INTO operative_notes
                (case_id, operation_date, data_json, status, updated_at, creation_key)
                VALUES (?, ?, ?, ?, ?, ?)""", (note["case_id"] or None, note["operation_date"], data, status, now, creation_key)).lastrowid
        else:
            result = db.execute("""UPDATE operative_notes SET case_id = ?, operation_date = ?,
                data_json = ?, status = ?, updated_at = ?, revision = revision + 1
                WHERE id = ? AND revision = ? AND status = 'draft'""",
                (note["case_id"] or None, note["operation_date"], data, status, now, note_id, revision))
            if result.rowcount != 1:
                raise SaveConflict("別の画面で更新されたか、既に完成しています。一覧から最新の記録を開き直してください。")
            db.execute("DELETE FROM operative_diagrams WHERE operative_note_id = ?", (note_id,))
        for diagram in diagrams:
            state = {k: v for k, v in diagram.items() if k not in ("objects", "diagram_type", "base_template")}
            diagram_id = db.execute("INSERT INTO operative_diagrams (operative_note_id, diagram_type, base_template, state_json) VALUES (?, ?, ?, ?)", (note_id, diagram["diagram_type"], diagram["base_template"], json.dumps(state, ensure_ascii=False))).lastrowid
            db.executemany("INSERT INTO diagram_objects (operative_diagram_id, object_type, sort_order, data_json) VALUES (?, ?, ?, ?)", [(diagram_id, obj["type"], index, json.dumps(obj, ensure_ascii=False)) for index, obj in enumerate(diagram["objects"])])
        saved = dict(db.execute("SELECT * FROM operative_notes WHERE id = ?", (note_id,)).fetchone())
    return saved


def load_diagrams(note_id):
    diagrams = []
    for row in get_db().execute("SELECT * FROM operative_diagrams WHERE operative_note_id = ? ORDER BY id", (note_id,)):
        diagram = json.loads(row["state_json"])
        diagram.update(diagram_type=row["diagram_type"], base_template=row["base_template"])
        diagram["objects"] = [json.loads(obj["data_json"]) for obj in get_db().execute("SELECT data_json FROM diagram_objects WHERE operative_diagram_id = ? ORDER BY sort_order", (row["id"],))]
        diagrams.append(diagram)
    return diagrams
