import json
import secrets
import sqlite3
from pathlib import Path

import click
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from db import SaveConflict, close_db, get_db, init_db, load_diagrams, save_note
from fields import DIAGRAMS, OBJECT_LAYERS, STEPS, LEGACY_FIELDS, blank_note, demo_payload, display_value, field_visible, normalize_note
from validation import ValidationError, validate_payload
from diagram_specs import TEMPLATES, GUIDES


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.json.sort_keys = False
    app.jinja_env.policies["json.dumps_kwargs"] = {"sort_keys": False}
    app.config.from_mapping(SECRET_KEY=secrets.token_hex(32), DATABASE=str(Path(app.instance_path) / "notes.sqlite3"), MAX_CONTENT_LENGTH=512 * 1024, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")
    if test_config:
        app.config.update(test_config)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)

    @app.context_processor
    def common():
        return dict(steps=STEPS, diagram_specs=DIAGRAMS, object_layers=OBJECT_LAYERS, diagram_templates=TEMPLATES, diagram_guides=GUIDES, field_visible=field_visible, display_value=display_value, legacy_fields=LEGACY_FIELDS)

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        notes = []
        for row in get_db().execute("SELECT * FROM operative_notes ORDER BY updated_at DESC, id DESC"):
            item = dict(row)
            data = normalize_note(json.loads(row["data_json"]))
            item["procedure"] = data["procedure_other"] if data["procedure"] == "その他（自由入力）" else data["procedure"]
            notes.append(item)
        return render_template("index.html", notes=notes)

    @app.get("/notes/new")
    def new_note():
        session.setdefault("csrf", secrets.token_hex(32))
        return render_template("new.html", note=blank_note(), diagrams=[], csrf=session["csrf"], editor_state=dict(id=None, revision=None, step=0, creation_key=secrets.token_hex(16), updated_at=None))

    @app.get("/notes/<int:note_id>/edit")
    def edit_note(note_id):
        row = find_note(note_id)
        if row["status"] == "completed":
            return redirect(url_for("detail", note_id=note_id))
        session.setdefault("csrf", secrets.token_hex(32))
        note = normalize_note(json.loads(row["data_json"]))
        return render_template("new.html", note=note, diagrams=load_diagrams(note_id), csrf=session["csrf"], editor_state=dict(id=note_id, revision=row["revision"], step=note.get("_step", 0), creation_key=row["creation_key"], updated_at=row["updated_at"]))

    @app.post("/notes")
    def create_note():
        return persist_note()

    @app.put("/notes/<int:note_id>")
    def update_note(note_id):
        return persist_note(note_id)

    def saved_response(note_id, code, replayed=False, row=None):
        row = row if row is not None else find_note(note_id)
        return jsonify(id=note_id, status=row["status"], revision=row["revision"], updated_at=row["updated_at"], replayed=replayed,
                       url=url_for("detail" if row["status"] == "completed" else "edit_note", note_id=note_id)), code

    def persist_note(note_id=None):
        token = request.headers.get("X-CSRF-Token", "")
        if not session.get("csrf") or not secrets.compare_digest(token.encode(), session["csrf"].encode()):
            return jsonify(error="画面を再読み込みしてから保存してください。"), 403
        if not request.is_json:
            return jsonify(error="JSON形式で送信してください。"), 400
        try:
            payload = request.get_json()
            status = payload.get("status", "completed") if isinstance(payload, dict) else "completed"
            note, diagrams = validate_payload(payload, status)
            creation_key = payload.get("creation_key")
            if note_id is None and creation_key:
                existing = get_db().execute("SELECT id FROM operative_notes WHERE creation_key = ?", (creation_key,)).fetchone()
                if existing:
                    return saved_response(existing["id"], 200, replayed=True)
            if note_id is not None:
                find_note(note_id)
                if type(payload.get("revision")) is not int or not 1 <= payload["revision"] < 2**63 - 1:
                    raise ValidationError("更新番号が不正です。画面を再読み込みしてください。")
            creating = note_id is None
            saved = save_note(note, diagrams, status, note_id, payload.get("revision"), payload.get("step", 0), creation_key)
            note_id = saved["id"]
        except (BadRequest, RecursionError):
            return jsonify(error="不正JSONです。"), 400
        except ValidationError as error:
            return jsonify(error=str(error)), 400
        except SaveConflict as error:
            return jsonify(error=str(error), conflict=True), 409
        except sqlite3.IntegrityError:
            if note_id is None and creation_key:
                existing = get_db().execute("SELECT id FROM operative_notes WHERE creation_key = ?", (creation_key,)).fetchone()
                if existing:
                    return saved_response(existing["id"], 200, replayed=True)
            return jsonify(error="この症例IDは既に保存されています。別のDEMO IDを使用してください。"), 409
        return saved_response(note_id, 201 if creating else 200, row=saved)

    def find_note(note_id):
        row = get_db().execute("SELECT * FROM operative_notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            abort(404)
        return row

    @app.get("/notes/<int:note_id>")
    def detail(note_id):
        row = find_note(note_id)
        if row["status"] == "draft":
            return redirect(url_for("edit_note", note_id=note_id))
        return render_template("detail.html", note=normalize_note(json.loads(row["data_json"])), diagrams=load_diagrams(note_id))

    @app.get("/notes/<int:note_id>/diagrams")
    def diagram_data(note_id):
        find_note(note_id)
        return jsonify(load_diagrams(note_id))

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", message="指定されたページ・症例は見つかりません。"), 404

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        return jsonify(error="保存データは512 KiB以内にしてください。描画点や注記を減らしてください。"), 413

    @app.cli.command("init-db")
    def init_command():
        init_db()
        click.echo("DBを初期化しました（既存データは保持）。")

    @app.cli.command("seed-demo")
    def seed_command():
        note, diagrams = validate_payload(demo_payload())
        if get_db().execute("SELECT id FROM operative_notes WHERE case_id = ?", (note["case_id"],)).fetchone():
            click.echo("DEMO-001は既に存在します。変更しません。")
        else:
            save_note(note, diagrams)
            click.echo("完全架空のDEMO-001を作成しました。")

    return app
