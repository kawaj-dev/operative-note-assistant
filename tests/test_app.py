import json
import re

import pytest

from app import create_app
from db import get_db, init_db
from fields import demo_payload
from validation import ValidationError, duration_minutes


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "test-only", "DATABASE": str(tmp_path / "test.sqlite3")})
    with app.app_context():
        init_db()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def save(client, payload=None, raw=None):
    client.get("/notes/new")
    with client.session_transaction() as session:
        token = session["csrf"]
    return client.post("/notes", data=raw if raw is not None else json.dumps(payload or demo_payload()), content_type="application/json", headers={"X-CSRF-Token": token})


def test_pages(client):
    assert client.get("/").status_code == 200
    page = client.get("/notes/new")
    assert page.status_code == 200
    assert page.text.count('data-panel=') == 10
    assert "実在する患者・症例の情報は入力しないでください" in page.text
    assert "frame-ancestors 'none'" in page.headers["Content-Security-Policy"]
    config = json.loads(re.search(r'id="diagram-config">(.*?)</script>', page.text).group(1))
    assert list(config["specs"]["hilum"]["layers"]) == ["base", "lesion", "device", "annotation"]


def test_save_and_detail(client, app):
    response = save(client)
    assert response.status_code == 201
    detail = client.get(response.json["url"])
    assert detail.status_code == 200
    assert "DEMO-001" in detail.text and "150 分" in detail.text
    assert "DEMO-001" in client.get("/").text
    with app.app_context():
        note = json.loads(get_db().execute("SELECT data_json FROM operative_notes").fetchone()[0])
        assert note["duration_minutes"] == 150
        assert get_db().execute("SELECT COUNT(*) FROM operative_diagrams").fetchone()[0] == 3
        assert get_db().execute("SELECT COUNT(*) FROM diagram_objects").fetchone()[0] == 3


@pytest.mark.parametrize("case_id", ["PATIENT-001", "001", "DEMO-1", "DEMO-１２３", "DEMO-1234", "DEMO-001'; DROP TABLE operative_notes;--"])
def test_invalid_case_id(client, case_id):
    payload = demo_payload()
    payload["note"]["case_id"] = case_id
    assert save(client, payload).status_code == 400


def test_duplicate_case_id(client, app):
    assert save(client).status_code == 201
    assert save(client).status_code == 409
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM operative_notes").fetchone()[0] == 1


@pytest.mark.parametrize("start,end,expected", [("09:00", "11:30", 150), ("23:40", "00:10", 30), ("00:00", "00:00", 0), ("", "", None)])
def test_duration(start, end, expected):
    assert duration_minutes(start, end) == expected


@pytest.mark.parametrize("start,end", [("24:00", "10:00"), ("09:60", "10:00"), ("09:00", ""), ("", "10:00"), ("9:00", "10:00")])
def test_invalid_duration(start, end):
    with pytest.raises(ValidationError):
        duration_minutes(start, end)


def test_diagram_round_trip(client):
    payload = demo_payload()
    diagram = payload["diagrams"][2]
    diagram["layers"]["lesion"]["visible"] = False
    diagram["base_transform"] = dict(x=10, y=-15, rotation=25)
    diagram["objects"].extend([
        dict(id="energy", type="ENERGY_DEVICE", x=320, y=140, rotation=-25, sequence=2),
        dict(id="pen", type="FREEHAND", x=20, y=30, rotation=15, points=[[0, 0], [10, 30], [90, 10]]),
        dict(id="text", type="TEXT", x=40, y=50, rotation=0, text="<img src=x onerror=alert(1)>"),
        dict(id="enclosure", type="ENCLOSURE", x=30, y=30, rotation=0, points=[[0, 0], [20, 30], [40, 0]]),
        dict(id="division", type="DIVISION_LINE", x=30, y=30, rotation=0, points=[[0, 0], [20, 30]]),
    ])
    diagram["next_sequence"] = 3
    payload["diagrams"][0]["objects"].append(dict(id="incision", type="INCISION", x=30, y=30, rotation=0, points=[[0, 0], [20, 30]]))
    response = save(client, payload)
    assert response.status_code == 201
    assert client.get(f'/notes/{response.json["id"]}/diagrams').json == payload["diagrams"]
    detail = client.get(response.json["url"]).text
    assert '<img src=x onerror=alert(1)>' not in detail
    assert '\\u003cimg' in detail


def test_unsupported_object_type(client):
    payload = demo_payload()
    payload["diagrams"][0]["objects"][0]["type"] = "SCRIPT"
    response = save(client, payload)
    assert response.status_code == 400
    assert "object type" in response.json["error"]


@pytest.mark.parametrize("raw", ["{", "[]", "null", '{"note":{},"diagrams":null}', '{"note":[],"diagrams":[]}'])
def test_invalid_json(client, raw):
    assert save(client, raw=raw).status_code == 400


@pytest.mark.parametrize("value", [True, "10", -1, 801, float("nan"), float("inf"), 10**300])
def test_invalid_coordinates(client, value):
    payload = demo_payload()
    payload["diagrams"][0]["objects"][0]["x"] = value
    assert save(client, payload).status_code == 400


def test_size_limit(client):
    assert save(client, raw='{"padding":"' + 'x' * (512 * 1024) + '"}').status_code == 413


def test_object_count_limit(client):
    payload = demo_payload()
    payload["diagrams"][0]["objects"] *= 201
    assert save(client, payload).status_code == 400


def test_invalid_diagrams_leave_no_rows(client, app):
    payload = demo_payload()
    payload["diagrams"][2]["layers"]["base"]["locked"] = "false"
    assert save(client, payload).status_code == 400
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM operative_notes").fetchone()[0] == 0
        assert get_db().execute("SELECT COUNT(*) FROM operative_diagrams").fetchone()[0] == 0
        assert get_db().execute("SELECT COUNT(*) FROM diagram_objects").fetchone()[0] == 0


@pytest.mark.parametrize("mutation", [
    lambda p: p["diagrams"][0].update(next_port=1),
    lambda p: p["diagrams"][0].update(base_template="../../secret"),
    lambda p: p["diagrams"][0].update(position="右側臥位"),
    lambda p: p["diagrams"][1]["objects"][0].update(size=999),
    lambda p: p["diagrams"][1]["objects"][0].update(note="x" * 501),
    lambda p: p["diagrams"][1]["objects"][0].update(unexpected="value"),
    lambda p: p["note"].update(surgeon="実在名を入力しない"),
    lambda p: p["note"].update(patient_name="unsupported"),
    lambda p: p["note"].update(operation_date="2026-02-30"),
    lambda p: p["note"].update(blood_loss="-1"),
    lambda p: p["note"].update(findings="x" * 4001),
])
def test_invalid_fields(client, mutation):
    payload = demo_payload()
    mutation(payload)
    assert save(client, payload).status_code == 400


def test_html_escaped(client):
    payload = demo_payload()
    payload["note"]["findings"] = '<script>alert("test")</script>'
    response = save(client, payload)
    html = client.get(response.json["url"]).text
    assert '<script>alert("test")</script>' not in html
    assert '&lt;script&gt;' in html


def test_csrf_and_content_type(client):
    assert client.post("/notes", json=demo_payload()).status_code == 403
    client.get("/notes/new")
    with client.session_transaction() as session:
        token = session["csrf"]
    assert client.post("/notes", data="x", headers={"X-CSRF-Token": token}).status_code == 400
    assert client.post("/notes", json=demo_payload(), headers={"X-CSRF-Token": "é"}).status_code == 403


def test_unknown_note(client):
    assert client.get("/notes/9999").status_code == 404
    assert client.get("/notes/9999/diagrams").status_code == 404


def test_cli_seed_is_idempotent(app):
    runner = app.test_cli_runner()
    assert runner.invoke(args=["init-db"]).exit_code == 0
    assert runner.invoke(args=["seed-demo"]).exit_code == 0
    assert runner.invoke(args=["seed-demo"]).exit_code == 0
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM operative_notes").fetchone()[0] == 1


def draft_payload():
    from fields import blank_note, empty_diagrams
    return dict(note=blank_note(), diagrams=empty_diagrams(''), status='draft', step=0)


def update(client, note_id, payload, revision):
    with client.session_transaction() as session:
        token = session['csrf']
    return client.put(f'/notes/{note_id}', json={**payload, 'revision': revision}, headers={'X-CSRF-Token': token})


def stored(app, note_id):
    with app.app_context():
        row = get_db().execute('SELECT * FROM operative_notes WHERE id = ?', (note_id,)).fetchone()
        return dict(row), json.loads(row['data_json'])


def test_new_step_layout(client):
    page = client.get('/notes/new').text
    panels = re.findall(r'<section class="card step" data-panel="\d".*?</section>', page, re.S)
    assert len(panels) == 10
    for name in ('case_id', 'operation_date', 'pre_diagnosis', 'post_diagnosis', 'start_time', 'end_time'):
        assert f'name="{name}"' in panels[0]
    assert 'id="duration"' in panels[0]
    for name in ('procedure', 'lobe', 'position'):
        assert f'name="{name}"' not in panels[0]
        assert f'name="{name}"' in panels[3]
    assert '術式詳細' in panels[3] and '合併切除' in panels[5] and '出血' in panels[6]
    assert 'hemostasis' not in page and 'drain' not in page
    assert 'name="blood_loss"' in panels[6] and 'name="start_time"' not in panels[6]
    status_bar = re.search(r'<div class="draft-bar">(.*?)</div>', page, re.S).group(1)
    assert all(f'id="{name}"' in status_bar for name in ('step-count', 'save-status', 'save-draft'))
    assert 'role="status"' in status_bar
    assert 'save-draft' in page
    index = client.get('/').text
    assert 'OPERATIVE NOTES' not in index and 'ガイド型入力・自由記載・手術図で' not in index
    assert '＋ 新規記録を作成' in index


def test_blank_drafts_and_listing(client, app):
    first = save(client, draft_payload())
    second = save(client, draft_payload())
    assert first.status_code == second.status_code == 201
    assert first.json['id'] != second.json['id']
    row, note = stored(app, first.json['id'])
    assert row['case_id'] is None and row['status'] == 'draft'
    assert row['updated_at'] and row['revision'] == 1
    assert note['duration_minutes'] is None
    assert '下書き' in client.get('/').text and '入力を再開' in client.get('/').text
    assert client.get(f"/notes/{row['id']}").status_code == 302
    assert client.get(first.json['url']).status_code == 200


def test_multiple_people_stations_round_trip(client, app):
    from fields import STATIONS
    payload = demo_payload()
    payload['note'].update(surgeon=['架空術者A', '架空術者B'], assistant=['架空助手B', '架空助手A'], lymph_done='あり', lymph_grade='ND2a-1', lymph_stations=[STATIONS[0], STATIONS[2]], combined_done='あり', combined_sites=['胸壁', '心膜'], combined_detail='架空の記録用箇所')
    response = save(client, payload)
    assert response.status_code == 201
    row, note = stored(app, response.json['id'])
    for name in ('surgeon', 'assistant', 'lymph_stations', 'combined_sites', 'combined_detail'):
        assert note[name] == payload['note'][name]
    html = client.get(response.json['url']).text
    assert '架空術者A、架空術者B' in html and '架空助手B、架空助手A' in html
    assert STATIONS[0] in html and STATIONS[2] in html
    assert 'ND2a-1' in html and '架空の記録用箇所' in html
    assert row['status'] == 'completed'


@pytest.mark.parametrize('name,value', [
    ('surgeon', ['架空術者A', '架空術者A']),
    ('assistant', ['未許可の人物']), ('surgeon', '架空術者A'),
    ('lymph_stations', ['#999']), ('lymph_stations', '#7'),
    ('lymph_stations', [True]), ('surgeon', ['', '', '']),
])
def test_invalid_arrays_in_draft(client, name, value):
    payload = draft_payload()
    payload['note'][name] = value
    assert save(client, payload).status_code == 400


def test_draft_resume_and_complete(client, app):
    payload = draft_payload()
    payload['note']['start_time'] = '09:00'
    payload['note']['surgeon'] = ['架空術者B', '']
    payload['step'] = 3
    response = save(client, payload)
    note_id = response.json['id']
    html = client.get(response.json['url']).text
    restored = json.loads(re.search(r'id="initial-note">(.*?)</script>', html).group(1))
    editor_state = json.loads(re.search(r'id="editor-state">(.*?)</script>', html).group(1))
    assert restored['start_time'] == '09:00' and restored['surgeon'] == ['架空術者B', '']
    assert editor_state['step'] == 3
    incomplete = update(client, note_id, {**payload, 'status': 'completed'}, 1)
    assert incomplete.status_code == 400 and '症例ID' in incomplete.json['error']
    assert stored(app, note_id)[0]['status'] == 'draft'
    complete = update(client, note_id, {**demo_payload(), 'status': 'completed'}, 1)
    assert complete.status_code == 200 and complete.json['revision'] == 2
    assert complete.json['status'] == 'completed'
    assert client.get(f'/notes/{note_id}/edit').status_code == 302
    assert '完成' in client.get('/').text
    assert update(client, note_id, payload, 2).status_code == 409
    assert stored(app, note_id)[0]['status'] == 'completed'


def test_draft_diagram_update_and_conflict(client, app):
    payload = {**demo_payload(), 'status': 'draft'}
    response = save(client, payload)
    note_id = response.json['id']
    payload['diagrams'][0]['objects'][0]['x'] = 150
    payload['diagrams'][0]['layers']['access']['locked'] = True
    assert update(client, note_id, payload, 1).status_code == 200
    assert client.get(f'/notes/{note_id}/diagrams').json == payload['diagrams']
    payload['diagrams'][0]['objects'][0]['x'] = 500
    conflict = update(client, note_id, payload, 1)
    assert conflict.status_code == 409 and conflict.json['conflict']
    assert client.get(f'/notes/{note_id}/diagrams').json[0]['objects'][0]['x'] == 150
    assert stored(app, note_id)[0]['revision'] == 2
    payload['diagrams'][0]['objects'][0]['type'] = 'SCRIPT'
    assert update(client, note_id, payload, 2).status_code == 400
    assert stored(app, note_id)[0]['revision'] == 2


def test_create_retry_is_idempotent(client, app):
    payload = draft_payload()
    payload['creation_key'] = 'a' * 32
    first = save(client, payload)
    payload['note']['findings'] = '再送時に増えた内容'
    retry = save(client, payload)
    assert first.json['id'] == retry.json['id']
    assert retry.json['replayed'] is True
    assert stored(app, first.json['id'])[1]['findings'] == ''
    assert update(client, retry.json['id'], payload, retry.json['revision']).status_code == 200
    assert stored(app, first.json['id'])[1]['findings'] == '再送時に増えた内容'


@pytest.mark.parametrize('mutation', [
    lambda p: p['note'].update(case_id='PATIENT-001'),
    lambda p: p['note'].update(start_time='25:00'),
    lambda p: p['note'].update(operation_date='2026-02-30'),
    lambda p: p['note'].update(findings='x' * 4001),
    lambda p: p.update(status='published'),
    lambda p: p.update(step=10),
    lambda p: p.update(creation_key='not-a-key'),
])
def test_draft_safety(client, mutation):
    payload = draft_payload()
    mutation(payload)
    assert save(client, payload).status_code == 400


def test_duplicate_draft_case_id(client, app):
    assert save(client).status_code == 201
    draft = draft_payload()
    response = save(client, draft)
    draft['note']['case_id'] = 'DEMO-001'
    assert update(client, response.json['id'], draft, 1).status_code == 409
    assert stored(app, response.json['id'])[0]['case_id'] is None


@pytest.mark.parametrize('procedure', ['区域切除術（Segmentectomy）', '部分切除術 / 楔状切除術（Wedge Resection）', '肺全摘術（Pneumonectomy）'])
def test_non_lobectomy_has_no_required_lobe(client, app, procedure):
    payload = demo_payload()
    payload['note'].update(procedure=procedure, lobe='', vein='非表示になる値', resection_note='架空の術式補足')
    response = save(client, payload)
    assert response.status_code == 201
    note = stored(app, response.json['id'])[1]
    assert note['vein'] == '' and note['resection_note'] == '架空の術式補足'
    html = client.get(response.json['url']).text
    assert '切除肺葉' not in html and '肺静脈の処理' not in html


@pytest.mark.parametrize('selector,extra', [('procedure', 'procedure_other'), ('lobe', 'lobe_other'), ('lymph_grade', 'lymph_grade_other')])
def test_other_fields(client, app, selector, extra):
    payload = demo_payload()
    payload['note'].update(lymph_done='あり')
    payload['note'][selector] = 'その他（自由入力）'
    assert save(client, payload).status_code == 400
    payload['note'][extra] = '架空の追加記載'
    response = save(client, payload)
    assert response.status_code == 201
    assert stored(app, response.json['id'])[1][extra] == '架空の追加記載'
    assert '架空の追加記載' in client.get(response.json['url']).text


def test_conditional_draft_retains_completed_clears(client, app):
    from fields import STATIONS
    payload = {**demo_payload(), 'status': 'draft'}
    payload['note'].update(lymph_done='なし', lymph_grade='ND1a', lymph_stations=[STATIONS[0]], lymph_note='切替前の下書き', combined_done='なし', combined_sites=['胸壁', '心膜'], combined_detail='切替前の箇所')
    response = save(client, payload)
    note_id = response.json['id']
    assert stored(app, note_id)[1]['lymph_stations'] == [STATIONS[0]]
    html = client.get(response.json['url']).text
    assert '切替前の下書き' in html
    assert stored(app, note_id)[1]['combined_sites'] == ['胸壁', '心膜']
    assert stored(app, note_id)[1]['combined_detail'] == '切替前の箇所'
    payload['status'] = 'completed'
    assert update(client, note_id, payload, 1).status_code == 200
    note = stored(app, note_id)[1]
    assert note['lymph_stations'] == [] and note['lymph_note'] == '' and note['combined_sites'] == [] and note['combined_detail'] == ''
    html = client.get(f'/notes/{note_id}').text
    assert '郭清度' not in html and 'その他・詳細' not in html


def test_update_requires_csrf_and_valid_revision(client):
    response = save(client, draft_payload())
    note_id = response.json['id']
    assert client.put(f'/notes/{note_id}', json=draft_payload()).status_code == 403
    assert update(client, note_id, draft_payload(), True).status_code == 400
    assert update(client, note_id, draft_payload(), 10**300).status_code == 400
    assert update(client, 9999, draft_payload(), 1).status_code == 404


def test_legacy_schema_migration_preserves_all_data(tmp_path):
    import sqlite3
    from db import SCHEMA, load_diagrams
    path = tmp_path / 'legacy.sqlite3'
    connection = sqlite3.connect(path)
    connection.execute('''CREATE TABLE operative_notes (
        id INTEGER PRIMARY KEY, case_id TEXT NOT NULL UNIQUE,
        operation_date TEXT NOT NULL, data_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    connection.executescript(SCHEMA)
    original = demo_payload()
    original['note']['duration_minutes'] = 150
    original['note'].update(procedure='右上葉切除術', surgeon='架空術者A', assistant='架空助手A・B', lymph_done='実施', lymph_extent='旧範囲', hemostasis='確認済み', drain='旧ドレーン記載')
    raw = json.dumps(original['note'], ensure_ascii=False)
    connection.execute('INSERT INTO operative_notes (id,case_id,operation_date,data_json) VALUES (?,?,?,?)', (7, 'DEMO-001', '2026-01-01', raw))
    for diagram in original['diagrams']:
        state = {k: v for k, v in diagram.items() if k not in ('objects', 'diagram_type', 'base_template')}
        diagram_id = connection.execute('INSERT INTO operative_diagrams (operative_note_id,diagram_type,base_template,state_json) VALUES (?,?,?,?)', (7, diagram['diagram_type'], diagram['base_template'], json.dumps(state))).lastrowid
        for index, obj in enumerate(diagram['objects']):
            connection.execute('INSERT INTO diagram_objects (operative_diagram_id,object_type,sort_order,data_json) VALUES (?,?,?,?)', (diagram_id, obj['type'], index, json.dumps(obj)))
    connection.commit()
    connection.close()
    app = create_app({'TESTING': True, 'DATABASE': str(path)})
    with app.app_context():
        init_db()
        init_db()
        row = get_db().execute('SELECT * FROM operative_notes WHERE id = ?', (7,)).fetchone()
        assert row['status'] == 'completed' and row['data_json'] == raw
        assert load_diagrams(7) == original['diagrams']
        assert not get_db().execute('PRAGMA foreign_key_check').fetchall()
    html = app.test_client().get('/notes/7').text
    assert '架空助手A、架空助手B' in html and '旧ドレーン記載' in html and '旧範囲' in html
    assert '150 分' in html


@pytest.mark.parametrize('value', [['未許可の部位'], ['胸壁', '胸壁'], '胸壁', None, {}, [True]])
def test_combined_sites_invalid(client, value):
    payload = demo_payload()
    payload['note'].update(combined_done='あり', combined_sites=value)
    assert save(client, payload).status_code == 400


def test_combined_fields_use_generic_controls(client):
    from fields import COMBINED_RESECTION_SITES, STEPS
    fields = STEPS[5][2]
    assert [f['name'] for f in fields] == ['combined_done', 'combined_sites', 'combined_detail']
    assert fields[1]['kind'] == 'repeat' and fields[1]['options'] == COMBINED_RESECTION_SITES
    assert all(f['when'] == {'combined_done': 'あり'} for f in fields[1:])
    page = client.get('/notes/new').text
    assert 'id="combined_sites-rows"' in page and 'data-add="combined_sites"' in page
    assert 'name="combined_detail"' in page and 'name="combined_site"' not in page


@pytest.mark.parametrize('status', ['draft', 'completed'])
def test_legacy_combined_text_read_without_db_rewrite(client, app, status):
    from fields import FIELDS, normalize_note
    payload = {**demo_payload(), 'status': status}
    payload['note']['combined_done'] = 'あり'
    response = save(client, payload)
    note_id = response.json['id']
    row, data = stored(app, note_id)
    data.pop('combined_sites')
    data.pop('combined_detail')
    legacy = '  胸壁の一部を切除\n完全架空の記録  '
    data['combined_site'] = legacy
    raw = json.dumps(data, ensure_ascii=False)
    with app.app_context():
        db = get_db()
        db.execute('UPDATE operative_notes SET data_json=? WHERE id=?', (raw, note_id))
        db.commit()
    normalized = normalize_note(data)
    assert normalized['combined_detail'] == legacy
    assert normalized['combined_sites'] == []  # Never infer sites from prose.
    assert 'combined_detail' not in data
    page = client.get(response.json['url']).text
    assert legacy in page
    current, _ = stored(app, note_id)
    assert current['data_json'] == raw and current['revision'] == row['revision']
    if status == 'draft':
        payload['note'] = {f['name']: normalized[f['name']] for f in FIELDS}
        assert update(client, note_id, payload, row['revision']).status_code == 200
        saved = stored(app, note_id)[1]
        assert saved['combined_detail'] == legacy and saved['combined_sites'] == []
        assert 'combined_site' not in saved


@pytest.mark.parametrize('detail', ['', '新しい詳細'])
def test_combined_new_detail_takes_precedence(detail):
    from fields import normalize_note
    data = {'combined_site': '旧文章', 'combined_detail': detail, 'combined_sites': ['心膜']}
    normalized = normalize_note(data)
    assert normalized['combined_detail'] == detail
    assert normalized['combined_sites'] == ['心膜']
