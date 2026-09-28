const NS = 'http://www.w3.org/2000/svg';
const config = JSON.parse(document.querySelector('#diagram-config').textContent);
const names = {PORT:'ポート', INCISION:'切開線', TUMOR:'腫瘍', STAPLER:'ステープラ', ENERGY_DEVICE:'エネルギーデバイス', DIVISION_LINE:'切離線', ENCLOSURE:'囲み', FREEHAND:'ペン', TEXT:'テキスト'};
const clone = value => structuredClone(value);
const clamp = (value, max) => Math.min(max, Math.max(0, value));
export function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function svgElement(tag, attributes = {}, text) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}
function button(text, action, parent) {
  const node = element('button', text);
  node.type = 'button'; node.addEventListener('click', action); parent.append(node);
  return node;
}
function legacyObjectGroup(obj) {
  const group = svgElement('g', {'data-object':obj.id, transform:`translate(${obj.x} ${obj.y}) rotate(${obj.rotation})`, stroke:'#3b6267', 'stroke-width':2, fill:'none'});
  if (obj.type === 'PORT') {
    group.append(svgElement('circle', {r:10, fill:'#e7f0ed'}), svgElement('text', {x:16, y:5, stroke:'none', fill:'#294c50', 'font-size':14}, `Port ${obj.number}`));
  } else if (obj.type === 'TUMOR') {
    group.append(svgElement('circle', {r:obj.size / 2, fill:'#ecd5cb', stroke:'#aa715e'}));
    if (obj.note) group.append(svgElement('title', {}, obj.note));
  } else if (obj.type === 'STAPLER') {
    group.append(svgElement('rect', {x:-38,y:-7,width:70,height:14,rx:3,fill:'#dae5e6'}), svgElement('path', {d:'M-25 -7 L-40 -27 L-50 -22 L-38 5 M-10 -7 V7 M0 -7 V7 M10 -7 V7 M20 -7 V7'}), svgElement('text', {x:-5,y:28,stroke:'none',fill:'#3b6267','font-size':13}, `S${obj.sequence}`));
  } else if (obj.type === 'ENERGY_DEVICE') {
    group.append(svgElement('path', {d:'M-45 0 H12 L35 -12 M12 0 L35 12 M-45 -8 V8', 'stroke-width':4}), svgElement('text', {x:-6,y:28,stroke:'none',fill:'#3b6267','font-size':13}, `E${obj.sequence}`));
  } else if (obj.type === 'TEXT') {
    group.append(svgElement('text', {x:0,y:0,stroke:'none',fill:'#294c50','font-size':17}, obj.text));
  } else {
    let d = obj.points.map((p, index) => `${index ? 'L' : 'M'}${p[0]} ${p[1]}`).join(' ');
    if (obj.type === 'ENCLOSURE') d += ' Z';
    const attributes = {d, 'stroke-linecap':'round', 'stroke-linejoin':'round'};
    if (obj.type === 'DIVISION_LINE') attributes['stroke-dasharray'] = '8 5';
    if (obj.type === 'INCISION') attributes['stroke-width'] = 4;
    if (obj.type === 'ENCLOSURE') attributes.fill = '#dcebe640';
    group.append(svgElement('path', attributes));
    // A transparent wider path makes thin strokes practical to select.
    group.append(svgElement('path', {d,stroke:'transparent','stroke-width':14,fill:'none'}));
  }
  return group;
}
const labels = {port:'ポート', incision:'切開線', lesion:'病変', resection_area:'切除範囲', staple_line:'ステープラ', energy_device:'エネルギーデバイス', finding:'所見', text:'テキスト', freehand:'自由描画'};
const devices = {unspecified:'指定なし', ultrasonic:'超音波', bipolar:'バイポーラ', other:'その他'};
const isNew = diagram => diagram.version === 2;
const title = diagram => config.templates[diagram.diagram_type].label;
const guideLabel = diagram => isNew(diagram) ? config.guides[diagram.guide_type].label : `旧版の図${diagram.position ? ' / '+diagram.position : ''}`;
const imagePath = key => '/static/images/diagram-guides/'+config.guides[key].file;
const transformable=o=>['port','lesion','energy_device','text','resection_area','freehand'].includes(o.type);
function pivot(o){
  if('x' in o)return {x:o.x,y:o.y};
  if(o.points){const xs=o.points.map(p=>p[0]),ys=o.points.map(p=>p[1]);return {x:(Math.min(...xs)+Math.max(...xs))/2,y:(Math.min(...ys)+Math.max(...ys))/2};}
  return {x:0,y:0};
}
function matrix(o){const c=pivot(o);return new DOMMatrix().translate(c.x,c.y).rotate(o.rotation||0).scale(o.scale||1).translate(-c.x,-c.y);}
function handle(parent,key,x,y,label,shape='circle'){
  const attrs={'data-handle':key,class:'transform-handle',fill:'#fff',stroke:'#086452','stroke-width':2,tabindex:0,role:'button','aria-label':label};
  const node=shape==='rect'?svgElement('rect',{...attrs,x:x-7,y:y-7,width:14,height:14}):svgElement('circle',{...attrs,cx:x,cy:y,r:8});
  parent.append(node);return node;
}
function selection(svg,node,o,modern){
  const box=node.getBBox(),overlay=svgElement('g',{'data-selection':o.id});
  if(!modern){node.append(svgElement('rect',{x:box.x-7,y:box.y-7,width:box.width+14,height:box.height+14,stroke:'#00776e','stroke-dasharray':'5 3',fill:'none','pointer-events':'none'}));return;}
  const m=transformable(o)?matrix(o):new DOMMatrix();
  const corners=[[box.x-6,box.y-6],[box.x+box.width+6,box.y-6],[box.x+box.width+6,box.y+box.height+6],[box.x-6,box.y+box.height+6]].map(([x,y])=>new DOMPoint(x,y).matrixTransform(m));
  overlay.append(svgElement('polygon',{points:corners.map(p=>`${p.x},${p.y}`).join(' '),stroke:'#086452','stroke-width':1.5,'stroke-dasharray':'5 3',fill:'none','pointer-events':'none'}));
  if('x1' in o){handle(overlay,'start',o.x1,o.y1,'始点を移動');handle(overlay,'end',o.x2,o.y2,'終点を移動');}
  else if(o.type==='finding'){handle(overlay,'target',o.target_x,o.target_y,'所見の対象位置を移動');handle(overlay,'label',o.label_x,o.label_y,'所見の文章位置を移動');}
  else if(transformable(o)){
    corners.forEach((p,i)=>handle(overlay,'resize',p.x,p.y,`拡大縮小 ${i+1}`,'rect'));
    // A circle has no directional appearance; rotation is useful for the other shapes.
    if(o.type!=='lesion'){
      const top=new DOMPoint(box.x+box.width/2,box.y-6).matrixTransform(m),angle=(o.rotation||0)*Math.PI/180;
      const x=top.x+Math.sin(angle)*30,y=top.y-Math.cos(angle)*30;
      overlay.append(svgElement('line',{x1:top.x,y1:top.y,x2:x,y2:y,stroke:'#086452','pointer-events':'none'}));handle(overlay,'rotate',x,y,'回転');
    }
  }
  const right=Math.max(...corners.map(p=>p.x)),top=Math.min(...corners.map(p=>p.y));
  const dx=Math.max(12,Math.min(788,right+24)),dy=Math.max(12,Math.min(488,top));
  handle(overlay,'delete',dx,dy,'選択した要素を削除');overlay.append(svgElement('text',{x:dx,y:dy+5,'text-anchor':'middle',fill:'#086452','font-size':16,'pointer-events':'none'},'×'));
  svg.append(overlay);
}function newObjectGroup(obj) {
  const g=svgElement('g',{'data-object':obj.id,stroke:obj.stroke_color||'#245f65','stroke-width':obj.stroke_width||2,fill:'none'});
  if(transformable(obj)){const m=matrix(obj);g.setAttribute('transform',`matrix(${m.a} ${m.b} ${m.c} ${m.d} ${m.e} ${m.f})`);}
  if(obj.type==='port') {
    g.append(svgElement('circle',{cx:obj.x,cy:obj.y,r:10,fill:'#e7f0ed'}),svgElement('text',{x:obj.x+15,y:obj.y+5,fill:'#245f65',stroke:'none','font-size':16},`Port ${obj.number}`));
  } else if(obj.type==='lesion') {
    g.append(svgElement('circle',{cx:obj.x,cy:obj.y,r:obj.size/2,fill:'#e9b9a9',stroke:'#984c36'}));
  } else if(obj.type==='energy_device') {
    g.append(svgElement('path',{d:`M${obj.x} ${obj.y-13} l13 13 l-13 13 l-13 -13 Z`,fill:'#fff2d3',stroke:'#785719','stroke-width':3}),svgElement('text',{x:obj.x,y:obj.y+5,'text-anchor':'middle','font-size':14,fill:'#785719',stroke:'none'},'E'));
  } else if(obj.type==='finding') {
    g.append(svgElement('line',{x1:obj.target_x,y1:obj.target_y,x2:obj.label_x,y2:obj.label_y,stroke:'#926746','stroke-dasharray':'4 3'}),svgElement('circle',{cx:obj.target_x,cy:obj.target_y,r:5,fill:'#926746'}),svgElement('text',{x:obj.label_x,y:obj.label_y,fill:'#704526',stroke:'none','font-size':17},obj.text));
  } else if(obj.type==='text') {
    g.append(svgElement('text',{x:obj.x,y:obj.y,fill:'#214d52',stroke:'none','font-size':17},obj.text));
  } else if(['staple_line','incision'].includes(obj.type)) {
    const attrs={x1:obj.x1,y1:obj.y1,x2:obj.x2,y2:obj.y2};
    g.append(svgElement('line',{...attrs,'stroke-width':obj.type==='incision'?4:2}));
    if(obj.type==='staple_line') {
      const dx=obj.x2-obj.x1,dy=obj.y2-obj.y1,len=Math.hypot(dx,dy),count=Math.max(1,Math.floor(len/12));
      if(len)for(let i=0;i<=count;i++) {
        const x=obj.x1+dx*i/count,y=obj.y1+dy*i/count;
        g.append(svgElement('line',{x1:x-dy/len*5,y1:y+dx/len*5,x2:x+dy/len*5,y2:y-dx/len*5}));
      }
    }
    g.append(svgElement('line',{...attrs,stroke:'transparent','stroke-width':16}));
  } else {
    const d=obj.points.map((p,i)=>`${i?'L':'M'}${p[0]} ${p[1]}`).join(' ')+(obj.type==='resection_area'?' Z':'');
    g.append(svgElement('path',{d,fill:obj.type==='resection_area'?'#44877c30':'none','stroke-dasharray':obj.type==='resection_area'?'6 4':'none','stroke-linecap':'round','stroke-linejoin':'round'}));
    g.append(svgElement('path',{d,stroke:'transparent','stroke-width':14,fill:'none'}));
  }
  if(obj.note)g.append(svgElement('title',{},obj.note));
  return g;
}
export function renderDiagram(svg, diagram, selected=null) {
  svg.replaceChildren();
  const guide=svgElement('g',{'data-guide':'true','pointer-events':'none'});
  if(isNew(diagram)) {
    if(diagram.guide_visible && config.guides[diagram.guide_type].file)guide.append(svgElement('image',{href:imagePath(diagram.guide_type),width:800,height:500,preserveAspectRatio:'xMidYMid meet',opacity:0.25}));
  } else if(diagram.layers.base.visible) {
    guide.setAttribute('transform',`translate(${diagram.base_transform.x} ${diagram.base_transform.y}) rotate(${diagram.base_transform.rotation} 400 250)`);
    guide.append(svgElement('image',{href:`/static/bases/${diagram.base_template}.svg`,width:800,height:500}));
    if(diagram.position)guide.append(svgElement('text',{x:400,y:120,'text-anchor':'middle',fill:'#466b62','font-size':16},diagram.position));
  }
  svg.append(guide);
  const records=svgElement('g',{'data-records':'true'});
  // Preserve legacy visibility and stacking exactly; guides are never selectable.
  const objects=isNew(diagram)?diagram.objects:Object.keys(config.specs[diagram.diagram_type].layers).flatMap(layer=>diagram.layers[layer].visible?diagram.objects.filter(obj=>config.layers[obj.type]===layer):[]);
  for(const obj of objects)records.append(isNew(diagram)?newObjectGroup(obj):legacyObjectGroup(obj));
  svg.append(records);
  if(selected) {
    const node=[...records.children].find(node=>node.dataset.object===selected);
    if(node)selection(svg,node,diagram.objects.find(o=>o.id===selected),isNew(diagram));
  }
}
function canvas(){return svgElement('svg',{viewBox:'0 0 800 500',class:'drawing-canvas',role:'img','aria-label':'手術図キャンバス'});}
function notice(parent){parent.append(element('p','ガイドは位置関係を記録するための補助で、患者固有の解剖を示すものではありません。線の刻みと「E」の菱形は本アプリ独自の記号です。ステープラの線数はカートリッジ使用本数を表しません。','diagram-notice'));}
export function renderSaved(parent, diagrams) {
  parent.replaceChildren();
  if(!diagrams.length)parent.append(element('p','手術図はありません。','muted'));
  for(const diagram of diagrams) {
    const section=element('section',undefined,'saved-diagram');
    section.append(element('h3',title(diagram)),element('p',`${guideLabel(diagram)} / ${diagram.objects.length}件`,'diagram-summary'));
    const wrap=element('div',undefined,'canvas-wrap'),svg=canvas();wrap.append(svg);section.append(wrap);parent.append(section);renderDiagram(svg,diagram);
    const notes=diagram.objects.flatMap(o=>{
      if(o.type==='energy_device')return [`エネルギーデバイス（${devices[o.device_type]}）：${o.note||'メモなし'}`];
      if(o.type==='finding'||o.type==='text')return [`${labels[o.type]}：${o.text}`];
      return o.note?[`${labels[o.type]||names[o.type]}：${o.note}`]:[];
    });
    if(notes.length)section.append(element('p',notes.join('\n'),'object-notes'));
  }
  if(diagrams.length)notice(parent);
}

const penColors={'#222222':'黒','#b42318':'赤','#175cd3':'青','#167044':'緑'};
const penWidths={2:'細',4:'中',8:'太'};

// One shared payload, with an independent editor and Undo history for each figure.
export class DiagramEditor {
  constructor(parent,diagrams,changed,save,getNote){
    this.parent=parent;this.diagrams=clone(diagrams);this.changed=changed;this.getNote=getNote;
    this.histories=diagrams.map(()=>({undo:[],redo:[]}));this.canvases=[];this.build();
  }
  build(){
    this.canvases.forEach(c=>{c.gesture=null;c.tool=null;});this.parent.replaceChildren();this.canvases=[];
    const add=()=>{const b=button('＋ 手術図を追加',()=>this.chooseTemplate(),this.parent);b.className='primary add-diagram';b.disabled=this.diagrams.length>=30;};
    add();
    if(!this.diagrams.length)this.parent.append(element('p','手術図はまだありません。0枚のまま次へ進めます。','empty-diagrams'));
    this.diagrams.forEach((d,i)=>{
      const panel=element('section',undefined,'diagram-workspace-item');panel.dataset.diagramIndex=i;panel.setAttribute('aria-label',`${i+1}枚目 ${title(d)} ${guideLabel(d)}`);this.parent.append(panel);
      const view=new DiagramCanvas(panel,this.diagrams,i,this.histories,this.changed,this.getNote);this.canvases.push(view);
      button('この手術図を削除',()=>this.confirmDelete(i,panel),panel).className='delete-diagram';
    });
    if(this.diagrams.length)add();
    notice(this.parent);
  }
  confirmDelete(index,panel){
    if(panel.querySelector('.delete-confirm'))return;
    const prompt=element('div',undefined,'delete-confirm');prompt.append(element('p','この手術図と図上の記録を削除しますか？'));
    button('削除する',()=>{
      this.diagrams.splice(index,1);this.histories.splice(index,1);
      this.diagrams.forEach((d,i)=>{if(isNew(d)){d.order=i;for(const snapshot of [...this.histories[i].undo,...this.histories[i].redo])snapshot.order=i;}});
      this.changed();this.build();
    },prompt);
    button('キャンセル',()=>prompt.remove(),prompt);panel.append(prompt);
  }
  chooseTemplate(){
    this.cancelGesture();this.dialog=element('dialog',undefined,'diagram-picker');this.dialog.setAttribute('aria-label','手術図を追加');this.parent.append(this.dialog);
    this.dialog.addEventListener('close',event=>event.currentTarget.remove());this.templateCards();this.dialog.showModal();
  }
  templateCards(){
    this.dialog.replaceChildren();this.dialog.append(element('h3','テンプレートを選択'));
    const grid=element('div',undefined,'diagram-cards');this.dialog.append(grid);
    for(const [kind,spec] of Object.entries(config.templates)){
      const card=button(spec.label,()=>kind==='blank'?this.add(kind,'none'):this.guideCards(kind),grid);card.className='choice-card';
      if(kind!=='blank'){const img=element('img');img.src=imagePath(spec.guides[0]);img.alt='';card.prepend(img);}else card.prepend(element('span','＋ 自由に記録','blank-preview'));
    }
    button('キャンセル',()=>this.dialog.close(),this.dialog);
  }
  guideCards(kind){
    this.dialog.replaceChildren();this.dialog.append(element('h3',`${config.templates[kind].label}：ガイドを選択`));
    const grid=element('div',undefined,'diagram-cards');this.dialog.append(grid);
    for(const key of config.templates[kind].guides){const b=button(config.guides[key].label,()=>this.add(kind,key),grid);b.className='choice-card';const img=element('img');img.src=imagePath(key);img.alt='';b.prepend(img);}
    button('テンプレート選択へ戻る',()=>this.templateCards(),this.dialog);button('キャンセル',()=>this.dialog.close(),this.dialog);
  }
  add(kind,guide){
    if(this.diagrams.length>=30)return;
    this.dialog.close();this.diagrams.push({version:2,diagram_type:kind,base_template:'guide-v2',guide_type:guide,guide_visible:guide!=='none',order:this.diagrams.length,next_port:1,objects:[]});
    this.histories.push({undo:[],redo:[]});this.changed();this.build();
    this.canvases.at(-1).parent.scrollIntoView({block:'start'});
  }
  cancelGesture(){this.canvases.forEach(c=>c.cancelGesture());}
  refresh(){this.canvases.forEach(c=>c.refresh());}
  updateReference(){this.canvases.forEach(c=>c.updateReference());}
  setPosition(position){this.canvases.forEach(c=>c.setPosition(position));}
}

class DiagramCanvas {
  constructor(parent,diagrams,index,histories,changed,getNote){
    this.parent=parent;this.diagrams=diagrams;this.histories=histories;this.changed=changed;this.getNote=getNote;
    this.pen={stroke_color:'#222222',stroke_width:4};this.edit(index);
  }
  get diagram(){return this.diagrams[this.index];}
  get history(){return this.histories[this.index];}
  snapshot(){return clone(this.diagram);}
  commit(before,refresh=true){
    if(JSON.stringify(before)===JSON.stringify(this.diagram))return;
    this.history.undo.push(before);if(this.history.undo.length>40)this.history.undo.shift();this.history.redo=[];this.changed();if(refresh)this.refresh();
  }  edit(index){
    this.index=index;this.tool=null;this.selected=null;this.gesture=null;this.parent.replaceChildren();
    this.parent.append(element('h3',`${title(this.diagram)} / ${guideLabel(this.diagram)}`));
    this.reference=element('div',undefined,'procedure-reference');this.parent.append(this.reference);this.updateReference();
    const guideRow=element('label',undefined,'guide-toggle'),toggle=element('input');toggle.type='checkbox';toggle.checked=isNew(this.diagram)?this.diagram.guide_visible:this.diagram.layers.base.visible;
    toggle.disabled=this.diagram.guide_type==='none';toggle.addEventListener('change',()=>{this.gesture=null;const before=this.snapshot();if(isNew(this.diagram))this.diagram.guide_visible=toggle.checked;else this.diagram.layers.base.visible=toggle.checked;this.commit(before);});
    guideRow.append(toggle,document.createTextNode('ガイドを表示'));this.parent.append(guideRow);this.guideToggle=toggle;
    if(!isNew(this.diagram))this.parent.append(element('p','旧版の図です。既存の配置・注記を編集できます。新しい記録ツールは「＋ 手術図を追加」から利用してください。','muted'));
    this.help=element('p',undefined,'tool-help');this.help.setAttribute('role','status');this.parent.append(this.help);
    const wrap=element('div',undefined,'canvas-wrap');this.svg=canvas();this.svg.tabIndex=0;
    this.svg.setAttribute('aria-label','手術図キャンバス。要素をクリックして選択、矢印キーで移動、Deleteで削除。');wrap.append(this.svg);this.parent.append(wrap);
    const toolGroups=element('div',undefined,'workspace-tools');this.parent.append(toolGroups);
    this.toolbar=element('div',undefined,'tools');const recording=element('section',undefined,'tool-group');recording.append(element('h4','記録'),this.toolbar);toolGroups.append(recording);
    for(const type of isNew(this.diagram)?config.templates[this.diagram.diagram_type].types.filter(t=>t!=='freehand'):[]){
      const b=button('＋ '+labels[type],()=>{this.gesture=null;this.tool=this.tool===type?null:type;this.selected=null;this.refresh();},this.toolbar);b.dataset.tool=type;
    }
    const drawing=element('section',undefined,'tool-group');drawing.append(element('h4','描画'));toolGroups.append(drawing);
    this.penButton=button('ペン',()=>{this.gesture=null;this.tool=this.tool==='freehand'?null:'freehand';this.selected=null;this.refresh();},drawing);
    this.penButton.disabled=!isNew(this.diagram);this.penButton.dataset.tool='freehand';
    this.penOptions=element('div',undefined,'pen-options');drawing.append(this.penOptions);this.styleControls(this.penOptions,this.pen,()=>{});
    const actions=element('div',undefined,'object-actions');
    this.undoButton=button('↶ Undo',()=>this.travel('undo','redo'),actions);this.redoButton=button('↷ Redo',()=>this.travel('redo','undo'),actions);
    this.deleteButton=button('選択を削除',()=>this.remove(),actions);const editing=element('section',undefined,'tool-group');editing.append(element('h4','編集'),actions);toolGroups.append(editing);
    const workspace=element('div',undefined,'figure-workspace'),panel=element('aside',undefined,'figure-controls');
    panel.setAttribute('aria-label',`${title(this.diagram)}の操作`);
    this.parent.append(workspace);workspace.append(wrap,panel);panel.append(toolGroups);
    const display=element('section',undefined,'tool-group');display.append(element('h4','表示'),guideRow);toolGroups.append(display);
    panel.append(this.help);
    this.inspector=element('div',undefined,'object-inspector');panel.append(this.inspector);
    this.svg.addEventListener('pointerdown',e=>this.pointerDown(e));this.svg.addEventListener('pointermove',e=>this.pointerMove(e));this.svg.addEventListener('pointerup',e=>this.pointerUp(e));this.svg.addEventListener('pointercancel',()=>this.cancelGesture());this.svg.addEventListener('keydown',e=>this.keyDown(e));
    this.refresh();
  }
  updateReference(){
    if(!this.reference||this.index===null)return;
    this.reference.replaceChildren();this.reference.hidden=this.diagram.diagram_type!=='lung';
    if(this.reference.hidden)return;
    const note=this.getNote(),other='その他（自由入力）';
    this.reference.append(element('strong','Step 04の入力内容（参照）'),element('p',`術式：${(note.procedure===other?note.procedure_other:note.procedure)||'未入力'}`));
    const target=note.procedure==='肺葉切除術（Lobectomy）'?(note.lobe===other?note.lobe_other:note.lobe):'';
    this.reference.append(element('p',`対象肺葉：${target||'未入力／対象外'}`));
    if(note.resection_note)this.reference.append(element('p',`術式詳細・補足：${note.resection_note}`));
    if(note.procedure==='区域切除術（Segmentectomy）')this.reference.append(element('p',`区域切除の対象：${note.segment_side||'対象側未入力'} / ${note.segment_target||'区域名未入力'}`));
    this.reference.append(element('small','術式・対象はStep 04で管理します。図上のクリックでは決定しません。'));
  }
  refresh(){
    if(this.index===null)return;
    if(this.selected&&!this.diagram.objects.some(o=>o.id===this.selected))this.selected=null;
    renderDiagram(this.svg,this.diagram,this.selected);
    this.toolbar.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tool===this.tool)));
    this.penButton.setAttribute('aria-pressed',String(this.tool==='freehand'));
    this.guideToggle.checked=isNew(this.diagram)?this.diagram.guide_visible:this.diagram.layers.base.visible;
    this.undoButton.disabled=!this.history.undo.length;this.redoButton.disabled=!this.history.redo.length;this.deleteButton.disabled=!this.selected;
    this.help.textContent=!this.tool?'直接クリックで選択、ドラッグで移動。四隅で拡大縮小、上の丸で回転、線の端点で長さ・角度を調整できます。':(['staple_line','incision'].includes(this.tool)?'始点、終点の順にクリック（またはドラッグ）。Escapeで中止。':['freehand','resection_area'].includes(this.tool)?'ドラッグして描きます。切除範囲は最後に閉じます。':'図上をクリックして1個配置します。')+' 配置すると追加モードは終了します。';
    this.renderInspector();
  }
  renderInspector(){
    this.inspector.replaceChildren();const obj=this.diagram.objects.find(o=>o.id===this.selected);this.inspector.hidden=!obj;if(!obj)return;
    this.inspector.append(element('h4',`${labels[obj.type]||names[obj.type]}を編集`));
    const inputField=(key,label,type='number',min=0,max=800)=>{
      const field=element('label',label),input=element(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;input.value=obj[key]??(key==='scale'?1:key==='rotation'?0:'');input.setAttribute('aria-label',label);
      if(type==='number'){input.min=min;input.max=max;input.step='any';}else {input.maxLength=500;if(key==='text')input.required=true;}
      field.append(input);this.inspector.append(field);
      const update=(final=false)=>{
        const value=type==='number'?Number(input.value):input.value;
        if(!input.checkValidity()||(type==='number'&&(!input.value||!Number.isFinite(value)))||(key==='text'&&!value.trim())){
          if(final){this.help.textContent='入力値を確認してください。';input.value=obj[key];}return;
        }
        const before=this.snapshot();obj[key]=value;this.commit(before,false);
        renderDiagram(this.svg,this.diagram,this.selected);
        this.undoButton.disabled=!this.history.undo.length;this.redoButton.disabled=!this.history.redo.length;
      };
      // Keep focus/caret while updating the same model used by autosave.
      input.addEventListener('input',()=>update());
      input.addEventListener('change',()=>update(true));
    };
    if('x1' in obj)for(const [key,label,max] of [['x1','始点 X',800],['y1','始点 Y',500],['x2','終点 X',800],['y2','終点 Y',500]])inputField(key,label,'number',0,max);
    if(obj.type==='finding')for(const [key,label,max] of [['target_x','所見の位置 X',800],['target_y','所見の位置 Y',500],['label_x','文章の位置 X',800],['label_y','文章の位置 Y',500]])inputField(key,label,'number',0,max);
    if(isNew(this.diagram)&&transformable(obj)){inputField('scale','拡大率','number',0.25,4);inputField('rotation','回転（度）','number',-360,360);}
    if(!isNew(this.diagram)&&'rotation' in obj)inputField('rotation','回転（度）','number',-360,360);
    if('size' in obj)inputField('size','サイズ（図上の単位）','number',4,120);
    if('device_type' in obj){
      const field=element('label','デバイスの種類'),select=element('select');select.setAttribute('aria-label','デバイスの種類');
      for(const [value,label] of Object.entries(devices)){const option=element('option',label);option.value=value;select.append(option);}select.value=obj.device_type;field.append(select);this.inspector.append(field);
      select.addEventListener('change',()=>{const before=this.snapshot();obj.device_type=select.value;this.commit(before);});
    }
    if(obj.type==='freehand')this.styleControls(this.inspector,obj,before=>this.commit(before));
    if('text' in obj)inputField('text',obj.type==='finding'?'位置に関連する所見':'テキスト','text');
    if('note' in obj)inputField('note','メモ（任意）','textarea');
    if(!isNew(this.diagram)&&this.diagram.objects.some(o=>!this.diagram.layers[config.layers[o.type]].visible))this.inspector.append(element('p','旧版で非表示にされた記録も保存されています。','muted'));
  }
  point(event){const p=new DOMPoint(event.clientX,event.clientY).matrixTransform(this.svg.getScreenCTM().inverse());return {x:Math.round(clamp(p.x,800)*10)/10,y:Math.round(clamp(p.y,500)*10)/10};}
  pointerDown(event){
    if(event.button!==0)return;event.preventDefault();this.svg.focus({preventScroll:true});const p=this.point(event);
    if(this.gesture?.waiting){this.gesture.obj.x2=p.x;this.gesture.obj.y2=p.y;this.finishGesture();return;}
    const control=event.target.closest('[data-handle]')?.dataset.handle;
    if(control){
      const obj=this.diagram.objects.find(o=>o.id===this.selected);if(!obj)return;
      if(control==='delete'){this.remove();return;}
      this.gesture={before:this.snapshot(),obj:clone(obj),origin:clone(obj),start:p,mode:control,center:pivot(obj)};
      this.svg.setPointerCapture(event.pointerId);return;
    }
    const hit=event.target.closest('[data-object]')?.dataset.object;
    // Existing records remain directly selectable even while an add tool is armed.
    if(hit){this.gesture=null;this.tool=null;}
    if(!this.tool){
      const id=event.target.closest('[data-object]')?.dataset.object,obj=this.diagram.objects.find(o=>o.id===id);this.selected=obj?id:null;this.refresh();if(!obj)return;
      this.gesture={before:this.snapshot(),obj:clone(obj),origin:clone(obj),start:p,mode:'move'};
    }else{
      if(this.diagram.objects.length>=200){this.help.textContent='各図200個までです。';return;}
      const obj={id:crypto.randomUUID(),type:this.tool};
      if(this.tool==='freehand')Object.assign(obj,this.pen);
      if(['staple_line','incision'].includes(this.tool))Object.assign(obj,{x1:p.x,y1:p.y,x2:p.x,y2:p.y});
      else if(['freehand','resection_area'].includes(this.tool))obj.points=[[p.x,p.y]];
      else if(this.tool==='finding')Object.assign(obj,{target_x:p.x,target_y:p.y,label_x:clamp(p.x+25,680),label_y:clamp(p.y-20,480),text:'所見'});
      else Object.assign(obj,{x:p.x,y:p.y});
      if(this.tool==='port')obj.number=this.diagram.next_port;
      if(this.tool==='lesion')Object.assign(obj,{size:24,note:''});
      if(this.tool==='energy_device')Object.assign(obj,{device_type:'unspecified',note:''});
      if(this.tool==='text')obj.text='テキスト';
      this.gesture={before:this.snapshot(),obj,start:p,mode:'add'};
      if(!obj.points&&!('x1' in obj)){this.finishGesture();this.inspector.querySelector('input[type=text]')?.focus({preventScroll:true});return;}
    }
    this.svg.setPointerCapture(event.pointerId);
  }
  pointerMove(event){
    if(!this.gesture)return;const p=this.point(event),g=this.gesture;
    if(g.mode==='move')g.obj=this.translated(g.origin,p.x-g.start.x,p.y-g.start.y);
    else if(['start','end','target','label'].includes(g.mode)){
      const keys={start:['x1','y1'],end:['x2','y2'],target:['target_x','target_y'],label:['label_x','label_y']}[g.mode];g.obj[keys[0]]=p.x;g.obj[keys[1]]=p.y;
    }else if(g.mode==='resize'){
      const distance=Math.hypot(g.start.x-g.center.x,g.start.y-g.center.y)||1;
      g.obj.scale=Math.min(4,Math.max(0.25,(g.origin.scale||1)*Math.hypot(p.x-g.center.x,p.y-g.center.y)/distance));
    }else if(g.mode==='rotate'){
      const angle=(Math.atan2(p.y-g.center.y,p.x-g.center.x)-Math.atan2(g.start.y-g.center.y,g.start.x-g.center.x))*180/Math.PI+(g.origin.rotation||0);
      g.obj.rotation=((angle+540)%360)-180;
    }
    else if('x1' in g.obj){g.obj.x2=p.x;g.obj.y2=p.y;}
    else if(g.obj.points&&g.obj.points.length<2000){const last=g.obj.points.at(-1);if(Math.hypot(p.x-last[0],p.y-last[1])>=1)g.obj.points.push([p.x,p.y]);}
    const preview=this.snapshot();if(g.mode!=='add')preview.objects=preview.objects.map(o=>o.id===g.obj.id?g.obj:o);else preview.objects.push(g.obj);
    renderDiagram(this.svg,preview,g.mode==='add'?null:g.obj.id);
  }
  pointerUp(event){
    const g=this.gesture;if(!g||g.waiting)return;this.pointerMove(event);
    if(this.svg.hasPointerCapture(event.pointerId))this.svg.releasePointerCapture(event.pointerId);
    if(g.mode==='add'&&'x1' in g.obj&&Math.hypot(g.obj.x2-g.obj.x1,g.obj.y2-g.obj.y1)<2){g.waiting=true;this.help.textContent='終了位置をクリックしてください。Escapeで中止。';return;}
    this.finishGesture();
  }
  finishGesture(){
    const g=this.gesture;this.gesture=null;if(!g)return;
    if(g.obj.points&&g.obj.points.length<(g.obj.type==='resection_area'?3:2)){this.refresh();return;}
    if(g.mode==='add'&&'x1' in g.obj&&Math.hypot(g.obj.x2-g.obj.x1,g.obj.y2-g.obj.y1)<2){this.refresh();return;}
    if(g.mode==='add'){this.diagram.objects.push(g.obj);if(g.obj.type==='port')this.diagram.next_port++;this.tool=null;}
    else this.diagram.objects=this.diagram.objects.map(o=>o.id===g.obj.id?g.obj:o);
    this.selected=g.obj.id;this.commit(g.before);this.refresh();
  }
  cancelGesture(){this.gesture=null;this.tool=null;this.refresh();}
  translated(original,dx,dy){
    const o=clone(original);let pairs;
    if(!isNew(this.diagram)||'x' in o)pairs=[['x','y']];
    else if('x1' in o)pairs=[['x1','y1'],['x2','y2']];
    else if(o.type==='finding')pairs=[['target_x','target_y'],['label_x','label_y']];
    const points=pairs?pairs.map(([x,y])=>[o[x],o[y]]):o.points;
    dx=Math.max(-Math.min(...points.map(p=>p[0])),Math.min(800-Math.max(...points.map(p=>p[0])),dx));dy=Math.max(-Math.min(...points.map(p=>p[1])),Math.min(500-Math.max(...points.map(p=>p[1])),dy));
    if(pairs)for(const [x,y] of pairs){o[x]+=dx;o[y]+=dy;}else o.points=points.map(([x,y])=>[x+dx,y+dy]);return o;
  }
  remove(){if(!this.selected)return;this.gesture=null;const before=this.snapshot();this.diagram.objects=this.diagram.objects.filter(o=>o.id!==this.selected);this.selected=null;this.commit(before);}
  travel(from,to){if(!this.history[from].length)return;this.gesture=null;this.tool=null;this.history[to].push(this.snapshot());this.diagrams[this.index]=this.history[from].pop();this.selected=null;this.changed();this.refresh();}
  keyDown(event){
    if(this.gesture?.waiting){this.gesture.obj.x2=p.x;this.gesture.obj.y2=p.y;this.finishGesture();return;}
    const control=event.target.closest('[data-handle]')?.dataset.handle;
    if(control&&(event.key==='Enter'||event.key===' ')){if(control==='delete'){event.preventDefault();this.remove();}return;}
    if(control&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){
      const obj=this.diagram.objects.find(o=>o.id===this.selected);if(!obj)return;event.preventDefault();const before=this.snapshot(),delta=['ArrowRight','ArrowUp'].includes(event.key)?1:-1;
      if(control==='rotate')obj.rotation=Math.max(-360,Math.min(360,(obj.rotation||0)+delta*5));
      else if(control==='resize')obj.scale=Math.max(0.25,Math.min(4,(obj.scale||1)+delta*0.1));
      else {const keys={start:['x1','y1'],end:['x2','y2'],target:['target_x','target_y'],label:['label_x','label_y']}[control];if(keys){const vertical=event.key==='ArrowUp'||event.key==='ArrowDown',key=keys[vertical?1:0];obj[key]=clamp(obj[key]+(event.key==='ArrowUp'?-1:event.key==='ArrowDown'?1:delta),vertical?500:800);}}
      this.commit(before);return;
    }
    if(event.key==='Escape'){event.preventDefault();this.cancelGesture();return;}
    if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='z'){event.preventDefault();this.travel(event.shiftKey?'redo':'undo',event.shiftKey?'undo':'redo');return;}
    if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();this.remove();return;}
    const directions={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};
    if(this.selected&&directions[event.key]){event.preventDefault();const before=this.snapshot(),amount=event.shiftKey?10:1,[x,y]=directions[event.key];this.diagram.objects=this.diagram.objects.map(o=>o.id===this.selected?this.translated(o,x*amount,y*amount):o);this.commit(before);}
  }
  styleControls(parent,target,changed){
    for(const [key,label,options] of [['stroke_color','ペンの色',penColors],['stroke_width','線の太さ',penWidths]]){
      const field=element('label',label),select=element('select');select.setAttribute('aria-label',label);
      for(const [value,text] of Object.entries(options)){const option=element('option',text);option.value=value;select.append(option);}
      select.value=target[key]??(key==='stroke_color'?'#222222':4);field.append(select);parent.append(field);
      select.addEventListener('change',()=>{const before=this.snapshot();target[key]=key==='stroke_width'?Number(select.value):select.value;changed(before);});
    }
  }
  setPosition(position){
    if(!isNew(this.diagram)&&this.diagram.diagram_type==='approach'){
      this.diagram.position=position;for(const snapshot of [...this.history.undo,...this.history.redo])snapshot.position=position;this.refresh();
    }
  }
}