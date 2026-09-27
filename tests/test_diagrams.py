"""Step 08 persistence, validation, approved assets, and non-destructive migration."""
import copy
import json
import re
import sqlite3

import pytest

from app import create_app
from db import get_db, init_db, load_diagrams
from diagram_specs import GUIDES, TEMPLATES
from fields import demo_payload
from test_app import app, client, draft_payload, save, update


def diagram(kind="blank", guide="none", order=0, objects=None):
    return dict(version=2, diagram_type=kind, base_template="guide-v2", guide_type=guide,
                guide_visible=guide != "none", order=order, next_port=2, objects=objects or [])


def objects():
    return [dict(id="port", type="port", x=20, y=30, number=1),
            dict(id="incision", type="incision", x1=40, y1=50, x2=80, y2=90),
            dict(id="lesion", type="lesion", x=90, y=100, size=24, note="架空病変"),
            dict(id="area", type="resection_area", points=[[10, 10], [90, 30], [70, 90], [20, 50]]),
            dict(id="staple", type="staple_line", x1=100, y1=100, x2=200, y2=150),
            dict(id="energy", type="energy_device", x=250, y=200, device_type="ultrasonic", note="架空メモ"),
            dict(id="finding", type="finding", target_x=310, target_y=200, label_x=350, label_y=180, text="架空の位置所見"),
            dict(id="text", type="text", x=400, y=300, text="<script>alert(1)</script>"),
            dict(id="free", type="freehand", points=[[50, 70], [80, 100], [120, 70]])]


@pytest.mark.parametrize("kind,guide", [(k, g) for k, spec in TEMPLATES.items() for g in spec["guides"]])
def test_template_guides_roundtrip(client, kind, guide):
    payload = draft_payload()
    payload["diagrams"] = [diagram(kind, guide)]
    response = save(client, payload)
    assert response.status_code == 201
    assert client.get(f'/notes/{response.json["id"]}/diagrams').json == payload["diagrams"]
    page = client.get(response.json["url"]).text
    assert json.loads(re.search(r'id="initial-diagrams">(.*?)</script>', page).group(1)) == payload["diagrams"]


def test_new_starts_empty_and_all_templates_available(client):
    page = client.get('/notes/new').text
    assert json.loads(re.search(r'id="initial-diagrams">(.*?)</script>', page).group(1)) == []
    config = json.loads(re.search(r'id="diagram-config">(.*?)</script>', page).group(1))
    assert config['templates'] == TEMPLATES
    assert config['guides'] == GUIDES
    # Step 08 has no duplicate procedure / target inputs.
    panel = page.split('data-panel="7"')[1].split('</section>')[0]
    assert 'name="procedure"' not in panel and 'name="lobe"' not in panel


def test_zero_diagrams_draft_to_completed(client, app):
    payload = draft_payload()
    payload['diagrams'] = []
    payload['step'] = 8
    response = save(client, payload)
    assert response.status_code == 201
    assert client.get(response.json['url']).status_code == 200
    completed = demo_payload()
    completed['diagrams'] = []
    completed['status'] = 'completed'
    response = update(client, response.json['id'], completed, response.json['revision'])
    assert response.status_code == 200 and response.json['status'] == 'completed'
    assert client.get(response.json['url']).status_code == 200
    with app.app_context():
        assert get_db().execute('SELECT COUNT(*) FROM operative_diagrams').fetchone()[0] == 0


def test_duplicates_edit_delete_order_hide_resume_complete(client, app):
    payload = demo_payload()
    payload.update(status='draft', step=7, diagrams=[diagram('lung', 'right_lung'), diagram('lung', 'left_lung', 1), diagram(order=2, objects=objects())])
    response = save(client, payload)
    assert response.status_code == 201
    note_id, revision = response.json['id'], response.json['revision']
    original = copy.deepcopy(payload['diagrams'][2]['objects'])
    payload['diagrams'][0]['guide_visible'] = False
    payload['diagrams'][1]['guide_type'] = 'right_lung'
    payload['diagrams'][2]['objects'][4]['x2'] = 270
    response = update(client, note_id, payload, revision)
    assert response.status_code == 200
    assert client.get(f'/notes/{note_id}/diagrams').json == payload['diagrams']
    payload['diagrams'].pop(1)
    payload['diagrams'][1]['order'] = 1
    payload['diagrams'][1]['objects'].pop(0)
    response = update(client, note_id, payload, response.json['revision'])
    assert response.status_code == 200
    page = client.get(f'/notes/{note_id}/edit').text
    assert json.loads(re.search(r'id="initial-diagrams">(.*?)</script>', page).group(1)) == payload['diagrams']
    assert '<script>alert(1)</script>' not in page
    payload['status'] = 'completed'
    response = update(client, note_id, payload, response.json['revision'])
    assert response.status_code == 200
    assert client.get(f'/notes/{note_id}/diagrams').json == payload['diagrams']
    assert update(client, note_id, payload, response.json['revision']).status_code == 409
    with app.app_context():
        assert get_db().execute('SELECT COUNT(*) FROM operative_diagrams').fetchone()[0] == 2
        assert get_db().execute('SELECT COUNT(*) FROM diagram_objects').fetchone()[0] == len(original) - 1
        assert not get_db().execute('PRAGMA foreign_key_check').fetchall()


@pytest.mark.parametrize('obj', objects(), ids=lambda obj: obj['type'])
def test_each_object_roundtrip_with_guide_hidden(client, obj):
    payload = draft_payload()
    # Blank accepts every supported record type; visibility does not affect objects.
    payload['diagrams'] = [diagram(objects=[obj])]
    response = save(client, payload)
    assert response.status_code == 201
    assert client.get(f'/notes/{response.json["id"]}/diagrams').json == payload['diagrams']


def test_guide_off_keeps_lung_objects_and_step04(client, app):
    payload = demo_payload()
    obj = objects()[2]
    payload.update(status='draft', diagrams=[diagram('lung', 'right_lung', objects=[obj])])
    response = save(client, payload)
    payload['diagrams'][0]['guide_visible'] = False
    response = update(client, response.json['id'], payload, response.json['revision'])
    assert response.status_code == 200
    actual = client.get(f'/notes/{response.json["id"]}/diagrams').json[0]
    assert not actual['guide_visible'] and actual['objects'] == [obj]
    with app.app_context():
        note = json.loads(get_db().execute('SELECT data_json FROM operative_notes').fetchone()[0])
        assert note['procedure'] == payload['note']['procedure'] and note['lobe'] == payload['note']['lobe']


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(guide_type='../../secret'),
    lambda d: d.update(guide_type=[]),
    lambda d: d.update(guide_visible='false'),
    lambda d: d.update(guide_visible=True),  # blank must remain blank
    lambda d: d.update(order=1),
    lambda d: d.update(version=True),
    lambda d: d.update(objects=[dict(id='bad', type='SELECT')]),
    lambda d: d['objects'][0].update(x=float('nan')),
    lambda d: d['objects'][0].update(x=True),
    lambda d: d['objects'][0].update(number=2),
    lambda d: d['objects'][5].update(device_type='laser'),
    lambda d: d['objects'][6].update(text=' '),
    lambda d: d['objects'][3].update(points=[[1, 2], [2, 3]]),
    lambda d: d['objects'][8].update(points=[[1, 2], [801, 3]]),
    lambda d: d['objects'].append(copy.deepcopy(d['objects'][0])),
])
def test_invalid_new_diagram_atomic(client, app, mutation):
    payload = draft_payload()
    payload['diagrams'] = [diagram(objects=objects())]
    mutation(payload['diagrams'][0])
    response = save(client, payload)
    assert response.status_code == 400
    with app.app_context():
        assert get_db().execute('SELECT COUNT(*) FROM operative_notes').fetchone()[0] == 0


def test_diagram_limit_and_incompatible_tools(client):
    payload = draft_payload()
    payload['diagrams'] = [diagram(order=i) for i in range(31)]
    assert save(client, payload).status_code == 400
    payload['diagrams'] = [diagram('approach', 'supine', objects=[objects()[2]])]
    assert save(client, payload).status_code == 400


def test_migration_keeps_every_old_row_and_backup(tmp_path):
    dbpath = tmp_path / 'legacy.sqlite3'
    testapp = create_app({'TESTING': True, 'DATABASE': str(dbpath)})
    from db import SCHEMA
    legacy_schema = SCHEMA.replace('state_json TEXT NOT NULL\n', 'state_json TEXT NOT NULL,\n    UNIQUE(operative_note_id, diagram_type)\n')
    connection = sqlite3.connect(dbpath)
    connection.executescript(legacy_schema)
    original = demo_payload()
    connection.execute("INSERT INTO operative_notes(id,case_id,operation_date,data_json) VALUES(7,?,?,?)", ('DEMO-001','2026-01-01',json.dumps(original['note'])))
    for i, d in enumerate(original['diagrams'], 10):
        state = {k: v for k, v in d.items() if k not in ('diagram_type','base_template','objects')}
        connection.execute('INSERT INTO operative_diagrams VALUES(?,?,?,?,?)',(i,7,d['diagram_type'],d['base_template'],json.dumps(state)))
        for order, obj in enumerate(d['objects']):
            connection.execute('INSERT INTO diagram_objects(operative_diagram_id,object_type,sort_order,data_json) VALUES(?,?,?,?)',(i,obj['type'],order,json.dumps(obj)))
    connection.commit()
    tables = ('operative_notes','operative_diagrams','diagram_objects')
    before = {t: connection.execute(f'SELECT * FROM {t} ORDER BY id').fetchall() for t in tables}
    connection.close()
    with testapp.app_context():
        init_db()
        init_db()
        db = get_db()
        for table in tables:
            assert [tuple(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY id')] == before[table]
        assert load_diagrams(7) == original['diagrams']
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        db.execute("INSERT INTO operative_diagrams(operative_note_id,diagram_type,base_template,state_json) VALUES(7,'approach','guide-v2','{}')")
        db.rollback()
    backups = list(tmp_path.glob('*.bak'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        for table in tables:
            assert backup.execute(f'SELECT * FROM {table} ORDER BY id').fetchall() == before[table]


def test_mixed_legacy_and_new_and_deleting_legacy(client):
    payload = demo_payload()
    payload.update(status='draft')
    payload['diagrams'].append(diagram('lung', 'left_lung', 3))
    response = save(client, payload)
    assert response.status_code == 201
    payload['diagrams'].pop(0)
    payload['diagrams'][-1]['order'] = 2
    response = update(client, response.json['id'], payload, response.json['revision'])
    assert response.status_code == 200
    assert client.get(f'/notes/{response.json["id"]}/diagrams').json == payload['diagrams']


def test_assets_available_and_local(client):
    for guide in GUIDES.values():
        if guide['file']:
            response = client.get('/static/images/diagram-guides/'+guide['file'])
            assert response.status_code == 200 and response.mimetype == 'image/png'
            assert response.data.startswith(b'\x89PNG\r\n\x1a\n')
