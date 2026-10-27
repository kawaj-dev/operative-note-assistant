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


def test_step10_print_controls(client):
    page = client.get('/notes/new').text
    panel = page.split('data-panel="9"')[1].split('</section>')[0]
    assert 'id="review"' in panel and 'id="fiction-confirm"' in panel
    assert 'data-review-view="review" aria-controls="review" aria-pressed="true"' in panel
    assert 'data-review-view="print-preview"' in panel
    assert 'type="button" id="print-note"' in panel
    assert 'id="print-document"' in panel
    assert 'type="submit" id="save"' in page


def test_print_document_current_data_and_switch_without_mutation():
    """Execute the production preview functions with a small in-memory DOM adapter."""
    import shutil
    import subprocess
    from pathlib import Path
    from fields import STEPS, blank_note
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the client-side preview test')
    source = Path('static/form.js').read_text(encoding='utf-8')
    functions = source[source.index('function printPreview()'):source.index("document.querySelectorAll('[data-review-view]').forEach(button => {\n  button.addEventListener")]
    note = blank_note()
    note.update(case_id='DEMO-901', operation_date='2026-01-01', blood_loss=0,
                transfusion='なし', combined_done='なし', combined_detail='非表示の下書き値',
                narrative='架空の所見\n二行目 <script>test</script>', surgeon=['架空術者A', ''])
    script = r'''
const assert = require('node:assert/strict');
class Node {
  constructor(tag, text, className) { this.tag=tag;this.text=text;this.className=className;this.children=[];this.hidden=false;this.attributes={}; }
  append(...nodes){this.children.push(...nodes);}
  prepend(...nodes){this.children.unshift(...nodes);}
  replaceChildren(...nodes){this.children=[...nodes];}
  setAttribute(key,value){this.attributes[key]=value;}
}
const element=(...args)=>new Node(...args);
const nodes=Object.fromEntries(['#print-document','#review','#print-preview'].map(id=>[id,new Node('div')]));
const buttons=['review','print-preview'].map(view=>{const b=new Node('button');b.dataset={reviewView:view};return b;});
const document={querySelector:id=>nodes[id],querySelectorAll:()=>buttons};
const noteData=()=>note;
const visible=(field,note)=>Object.entries(field.when).every(([key,value])=>note[key]===value);
const duration=()=>0;
const editor={diagrams:[{id:'second-created',guide_visible:false},{id:'first-created',guide_visible:true}]};
const renderSaved=(parent,diagrams)=>diagrams.forEach(d=>parent.append(element('svg',d.id)));

''' + '\nconst steps=' + json.dumps(STEPS, ensure_ascii=False) + ';\nconst note=' + json.dumps(note, ensure_ascii=False) + ';\n' + functions + r'''
const snapshot=JSON.stringify({note,diagrams:editor.diagrams});
setReviewView('print-preview');
function entries(node){return [node,...node.children.flatMap(entries)];}
let all=entries(nodes['#print-document']);
let texts=all.map(n=>n.text);
assert(texts.includes(0));assert(texts.includes('0 分'));assert(texts.includes('なし'));
assert(texts.includes('架空の所見\n二行目 <script>test</script>'));
assert(!texts.includes('術後診断'));assert(!texts.includes('非表示の下書き値'));
assert(texts.some(t=>typeof t==='string' && t.includes('学習用プロトタイプ')));
assert.deepEqual(all.filter(n=>n.tag==='svg').map(n=>n.text),['second-created','first-created']);
assert.equal(nodes['#review'].hidden,true);assert.equal(buttons[1].attributes['aria-pressed'],'true');
setReviewView('review');
assert.equal(nodes['#review'].hidden,false);assert.equal(nodes['#print-preview'].hidden,true);
assert.equal(JSON.stringify({note,diagrams:editor.diagrams}),snapshot);
note.narrative='変更後の架空所見';setReviewView('print-preview');
assert(entries(nodes['#print-document']).some(n=>n.text==='変更後の架空所見'));
'''
    # These functions must not call any save/dirty APIs (the adapter provides none).
    result = subprocess.run([node, '-e', script], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr


def test_print_css_and_native_print():
    from pathlib import Path
    css = Path('static/style.css').read_text(encoding='utf-8')
    js = Path('static/form.js').read_text(encoding='utf-8')
    assert '@page {size:A4 portrait;margin:15mm}' in css
    assert '@media print' in css and 'break-inside:avoid' in css
    assert 'body.printing-note #note-form> :not([data-panel="9"])' in css
    assert 'window.print()' in js and "window.addEventListener('beforeprint'" in js
    assert 'renderSaved(diagrams, editor.diagrams)' in js