"""Final UX: read-time legacy migration and optional drawing attributes."""
import copy
import json
import re

import pytest

from db import get_db
from fields import FIELDS, LOBECTOMY, SEGMENTECTOMY, merge_narrative, normalize_note
from test_app import app, client, draft_payload, save, stored, update
from test_diagrams import diagram, objects


def test_step09_single_field_and_old_text_read_migration(client, app):
    payload=draft_payload()
    payload['note'].pop('narrative',None)
    payload['note'].update(findings='  旧所見\n二行目  ',course='旧経過\n続き')
    response=save(client,payload)
    note_id=response.json['id']
    # Simulate a pre-upgrade row; opening it must not rewrite its JSON or revision.
    with app.app_context():
        db=get_db()
        data=json.loads(db.execute('SELECT data_json FROM operative_notes WHERE id=?',(note_id,)).fetchone()[0])
        data.pop('narrative')
        raw=json.dumps(data,ensure_ascii=False)
        db.execute('UPDATE operative_notes SET data_json=? WHERE id=?',(raw,note_id));db.commit()
    page=client.get(f'/notes/{note_id}/edit').text
    panel=page.split('data-panel="8"')[1].split('</section>')[0]
    assert panel.count('<textarea')==1 and 'name="narrative"' in panel
    assert 'name="findings"' not in panel and 'name="course"' not in panel
    assert '旧所見' in panel and '旧経過' in panel
    with app.app_context():
        assert get_db().execute('SELECT data_json FROM operative_notes WHERE id=?',(note_id,)).fetchone()[0]==raw
    payload['note']={k:v for k,v in normalize_note(data).items() if k in {f['name'] for f in FIELDS}}
    payload['step']=9
    response=update(client,note_id,payload,response.json['revision'])
    assert response.status_code==200
    assert stored(app,note_id)[1]['narrative']==merge_narrative(data)
    page=client.get(response.json['url']).text
    config=json.loads(re.search(r'id="field-config">(.*?)</script>',page).group(1))
    assert [(f['name'],f['label']) for f in config[8][2]]==[('narrative','手術所見・手術経過')]


@pytest.mark.parametrize('old',[{}, {'findings':'所見だけ'}, {'course':'経過だけ'}, {'findings':'同じ文','course':'同じ文'}, {'findings':'x'*4000,'course':'y'*4000}])
def test_narrative_read_conversion_lossless(old):
    original=copy.deepcopy(old)
    result=normalize_note(old)['narrative']
    for value in old.values():assert value in result
    assert old==original
    assert normalize_note({**old,'narrative':result})['narrative']==result
    assert normalize_note({**old,'narrative':''})['narrative']==''


def test_narrative_save_resume_complete_and_clear(client,app):
    from fields import demo_payload
    payload=demo_payload();payload.update(status='draft',diagrams=[])
    payload['note']={k:v for k,v in payload['note'].items() if k not in ('findings','course')}
    payload['note']['narrative']='所見と経過を統合した架空文章\n<script>fake</script>'
    response=save(client,payload);note_id=response.json['id']
    assert response.status_code==201
    assert stored(app,note_id)[1]['narrative']==payload['note']['narrative']
    assert '&lt;script&gt;' in client.get(response.json['url']).text
    payload['note']['narrative']=''
    response=update(client,note_id,payload,response.json['revision'])
    assert stored(app,note_id)[1]['narrative']==''
    payload['note']['narrative']='完成時の統合文章';payload['status']='completed'
    response=update(client,note_id,payload,response.json['revision'])
    assert response.status_code==200
    detail=client.get(response.json['url']).text
    assert '完成時の統合文章' in detail
    assert '<dt>手術所見</dt>' not in detail and '<dt>手術経過</dt>' not in detail
    assert '<dt>手術所見・手術経過</dt>' in detail


@pytest.mark.parametrize('value',['x'*10001,[],None])
def test_invalid_narrative_rejected(client,value):
    payload=draft_payload();payload['note']['narrative']=value
    assert save(client,payload).status_code==400


def test_segment_structured_fields_conditional_and_roundtrip(client,app):
    payload=draft_payload();payload['diagrams']=[]
    payload['note'].update(procedure=SEGMENTECTOMY,segment_side='右肺',segment_target='架空の対象区域')
    response=save(client,payload)
    assert response.status_code==201
    _,note=stored(app,response.json['id'])
    assert note['segment_side']=='右肺' and note['segment_target']=='架空の対象区域'
    fields={f['name']:f for f in FIELDS}
    assert fields['segment_side']['when']=={'procedure':SEGMENTECTOMY}
    assert fields['segment_target']['options'] is None  # No unverified medical master.
    payload['note']['segment_side']='未確認の選択肢'
    assert update(client,response.json['id'],payload,response.json['revision']).status_code==400


@pytest.mark.parametrize('type_name',['port','lesion','energy_device','text','resection_area','freehand'])
def test_transform_attributes_roundtrip_edit_undo_equivalent(client,type_name):
    obj=next(o for o in objects() if o['type']==type_name)
    payload=draft_payload();payload['diagrams']=[diagram(objects=[obj])]
    response=save(client,payload);note_id=response.json['id']
    original=copy.deepcopy(payload['diagrams'])
    obj.update(rotation=47.5,scale=1.7)
    response=update(client,note_id,payload,response.json['revision'])
    assert response.status_code==200
    assert client.get(f'/notes/{note_id}/diagrams').json==payload['diagrams']
    payload['diagrams']=original
    response=update(client,note_id,payload,response.json['revision'])
    assert response.status_code==200
    assert client.get(f'/notes/{note_id}/diagrams').json==original


@pytest.mark.parametrize('color,width',[('#222222',2),('#b42318',4),('#175cd3',8),('#167044',4)])
def test_pen_style_saved_without_changing_semantics(client,color,width):
    obj=objects()[-1];obj.update(stroke_color=color,stroke_width=width)
    payload=draft_payload();payload['diagrams']=[diagram(objects=[obj]),diagram(order=1,objects=[objects()[2]])]
    response=save(client,payload)
    assert response.status_code==201
    actual=client.get(f'/notes/{response.json["id"]}/diagrams').json
    assert actual==payload['diagrams']
    assert actual[0]['objects'][0]['type']=='freehand' and actual[1]['objects'][0]['type']=='lesion'


@pytest.mark.parametrize('attributes',[{'scale':0},{'scale':True},{'scale':5},{'rotation':float('inf')},{'rotation':361},{'stroke_color':'url(https://example.com)'},{'stroke_width':100},{'stroke_width':True}])
def test_invalid_transform_and_pen_style(client,attributes):
    obj=objects()[-1];obj.update(attributes)
    payload=draft_payload();payload['diagrams']=[diagram(objects=[obj])]
    assert save(client,payload).status_code==400


def test_independent_guides_and_endpoint_edit(client):
    obj=objects()[4]
    payload=draft_payload();payload['diagrams']=[diagram('lung','right_lung',objects=[obj]),diagram('lung','left_lung',order=1)]
    response=save(client,payload)
    payload['diagrams'][0]['guide_visible']=False
    obj.update(x1=60,y1=70,x2=300,y2=260)
    response=update(client,response.json['id'],payload,response.json['revision'])
    actual=client.get(f'/notes/{response.json["id"]}/diagrams').json
    assert response.status_code==200 and actual==payload['diagrams']
    assert actual[1]['guide_visible'] and len(actual[0]['objects'])==1


def test_local_assets_only_and_no_new_dependencies(client):
    from pathlib import Path
    page=client.get('/notes/new').text
    assert not re.search(r'(?:src|href)="https?://',page)
    for file in ('static/diagrams.js','static/form.js'):
        assert not re.search(r'(?:fetch|import)\s*\(?\s*[\'\"]https?://',Path(file).read_text(encoding='utf-8'))
    assert 'dialog' in Path('static/diagrams.js').read_text(encoding='utf-8')
