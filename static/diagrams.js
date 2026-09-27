const NS = 'http://www.w3.org/2000/svg';
const config = JSON.parse(document.querySelector('#diagram-config').textContent);
const names = {SELECT:'選択・移動', PORT:'ポート', INCISION:'切開線', TUMOR:'腫瘍', STAPLER:'ステープラ', ENERGY_DEVICE:'エネルギーデバイス', DIVISION_LINE:'切離線', ENCLOSURE:'囲み', FREEHAND:'ペン', TEXT:'テキスト'};
const drawingTypes = ['INCISION', 'DIVISION_LINE', 'ENCLOSURE', 'FREEHAND'];
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
function objectGroup(obj) {
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
export function renderDiagram(svg, diagram, selected = null) {
  svg.replaceChildren();
  const base = svgElement('g', {'data-object':'base', transform:`translate(${diagram.base_transform.x} ${diagram.base_transform.y}) rotate(${diagram.base_transform.rotation} 400 250)`});
  base.append(svgElement('image', {href:`/static/bases/${diagram.base_template}.svg`,width:800,height:500}));
  if (diagram.diagram_type === 'approach') base.append(svgElement('text', {x:400,y:120,'text-anchor':'middle',fill:'#466b62','font-size':16}, diagram.position));
  if (diagram.layers.base.visible) svg.append(base);
  for (const layer of Object.keys(config.specs[diagram.diagram_type].layers)) {
    if (layer === 'base' || !diagram.layers[layer].visible) continue;
    const group = svgElement('g', {'data-layer':layer});
    for (const obj of diagram.objects.filter(obj => config.layers[obj.type] === layer)) group.append(objectGroup(obj));
    svg.append(group);
  }
  if (selected) {
    const node = [...svg.querySelectorAll('[data-object]')].find(node => node.dataset.object === selected);
    if (node) {
      const box = node.getBBox();
      node.append(svgElement('rect', {x:box.x-6,y:box.y-6,width:box.width+12,height:box.height+12,stroke:'#168374','stroke-width':1,'stroke-dasharray':'4 3',fill:'none','pointer-events':'none'}));
    }
  }
}
function canvas() {
  const svg = svgElement('svg', {viewBox:'0 0 800 500',class:'drawing-canvas',role:'img','aria-label':'手術図キャンバス'});
  return svg;
}
function notice(parent) {
  parent.append(element('p','ベース図は未確認のプレースホルダーです。枠は人体や解剖を表しません。注記・配置の機能検証に使用してください。','placeholder-notice'));
  parent.append(element('p','模式図の利用方針：本図は機能検証用に典型的な解剖を簡略化して示すものです。実際の気管支・血管の分岐・走行には解剖学的変異があります。診療目的には使用できません。現在のベースは解剖未収載です。','diagram-notice'));
}
export function renderSaved(parent, diagrams) {
  parent.replaceChildren();
  for (const diagram of diagrams) {
    const section = element('section', undefined, 'saved-diagram');
    section.append(element('h3',config.specs[diagram.diagram_type].label));
    const hidden = Object.entries(diagram.layers).filter(([,state])=>!state.visible).map(([key])=>config.specs[diagram.diagram_type].layers[key]);
    section.append(element('p',`${diagram.objects.length} オブジェクト${diagram.position ? ` / ${diagram.position}` : ''} / 非表示レイヤー：${hidden.join('、') || 'なし'}`, 'diagram-summary'));
    const wrap = element('div',undefined,'canvas-wrap'); const svg = canvas();
    wrap.append(svg); section.append(wrap); parent.append(section); renderDiagram(svg,diagram);
    const notes = diagram.objects.filter(obj=>obj.type==='TUMOR' && obj.note).map((obj,index)=>`腫瘍注記 ${index+1}：${obj.note}`);
    if (notes.length) section.append(element('p',notes.join('\n'),'object-notes'));
  }
  notice(parent);
}

export class DiagramEditor {
  constructor(parent, diagrams, changed) {
    this.diagrams = clone(diagrams); this.index = 0; this.tool = 'SELECT'; this.selected = null;
    this.histories = diagrams.map(()=>({undo:[],redo:[]})); this.changed = changed;
    this.parent = parent; this.build();
  }
  get diagram() { return this.diagrams[this.index]; }
  get history() { return this.histories[this.index]; }
  snapshot() { return clone(this.diagram); }
  commit(before) {
    if (JSON.stringify(before) === JSON.stringify(this.diagram)) return;
    this.history.undo.push(before); if (this.history.undo.length>40) this.history.undo.shift();
    this.history.redo = []; this.changed(); this.refresh();
  }
  build() {
    this.parent.replaceChildren();
    const tabs = element('div',undefined,'diagram-tabs'); tabs.setAttribute('role','tablist');
    this.diagrams.forEach((diagram,index)=>{
      const tab = button(config.specs[diagram.diagram_type].label,()=>{this.index=index;this.selected=null;this.tool='SELECT';this.build();},tabs);
      tab.setAttribute('role','tab');tab.setAttribute('aria-selected',String(index===this.index));
    });
    this.parent.append(tabs);
    this.toolbar = element('div',undefined,'tools');
    for (const tool of ['SELECT',...config.specs[this.diagram.diagram_type].types]) {
      const btn = button(names[tool],()=>{this.tool=tool;this.selected=null;this.refresh();},this.toolbar);btn.dataset.tool=tool;
    }
    this.parent.append(this.toolbar);
    this.help = element('p',undefined,'tool-help');this.help.setAttribute('role','status');this.parent.append(this.help);
    const layout=element('div',undefined,'diagram-layout'); const left=element('div');
    const wrap=element('div',undefined,'canvas-wrap');this.svg=canvas();this.svg.setAttribute('tabindex','0');
    this.svg.setAttribute('aria-label','手術図キャンバス。選択した要素は矢印キーで移動、Deleteで削除できます。');
    wrap.append(this.svg);left.append(wrap);
    const actions=element('div',undefined,'object-actions');
    this.undoButton=button('↶ Undo',()=>this.travel('undo','redo'),actions);
    this.redoButton=button('↷ Redo',()=>this.travel('redo','undo'),actions);
    this.deleteButton=button('選択を削除',()=>this.remove(),actions);
    left.append(actions);layout.append(left);
    this.side=element('aside',undefined,'layer-panel');layout.append(this.side);this.parent.append(layout);
    notice(this.parent);
    this.svg.addEventListener('pointerdown',event=>this.pointerDown(event));
    this.svg.addEventListener('pointermove',event=>this.pointerMove(event));
    this.svg.addEventListener('pointerup',event=>this.pointerUp(event));
    this.svg.addEventListener('pointercancel',()=>this.cancelDrag());
    this.svg.addEventListener('keydown',event=>this.keyDown(event));
    this.refresh();
  }
  refresh() {
    if (this.selected && !this.editable(this.selected)) this.selected=null;
    renderDiagram(this.svg,this.diagram,this.selected);
    this.toolbar.querySelectorAll('button').forEach(btn=>btn.setAttribute('aria-pressed',String(btn.dataset.tool===this.tool)));
    this.undoButton.disabled=!this.history.undo.length;this.redoButton.disabled=!this.history.redo.length;
    this.deleteButton.disabled=!this.selected || this.selected==='base';
    this.help.textContent=this.tool==='SELECT'?'クリックで選択、ドラッグで移動。回転は右側の角度欄で変更できます。':drawingTypes.includes(this.tool)?'キャンバス上をドラッグして描きます。':'キャンバス上をクリックして配置します。配置後は選択ツールで移動できます。';
    this.renderSidebar();
  }
  renderSidebar() {
    this.side.replaceChildren(); const layers=element('div');layers.append(element('strong','固定レイヤー'));
    for (const [key,label] of Object.entries(config.specs[this.diagram.diagram_type].layers)) {
      const row=element('div',undefined,'layer-row');row.append(element('strong',label));
      for (const [prop,text] of [['visible','表示'],['locked','ロック']]) {
        const labelNode=element('label');const input=element('input');input.type='checkbox';input.checked=this.diagram.layers[key][prop];
        input.setAttribute('aria-label',`${label} ${text}`);
        input.addEventListener('change',()=>{const before=this.snapshot();this.diagram.layers[key][prop]=input.checked;this.commit(before);});
        labelNode.append(input,document.createTextNode(text));row.append(labelNode);
      }
      layers.append(row);
    }
    this.side.append(layers);const inspector=element('div',undefined,'inspector');this.side.append(inspector);
    const obj=this.selected==='base'?this.diagram.base_transform:this.diagram.objects.find(o=>o.id===this.selected);
    if (!obj) {inspector.append(element('p','要素を選択すると、回転や注記を変更できます。','muted'));return;}
    inspector.append(element('strong',this.selected==='base'?'ベース':names[obj.type]));
    const inputField=(key,label,type,min,max)=>{
      const labelNode=element('label',label); const input=element('input');input.type=type;input.value=obj[key];
      if(type==='number'){input.min=min;input.max=max;input.step='1';}else input.maxLength=500;
      input.setAttribute('aria-label',label);labelNode.append(input);inspector.append(labelNode);
      input.addEventListener('change',()=>{
        const value=type==='number'?Number(input.value):input.value;
        if (!input.checkValidity() || (type==='number' && (!input.value || !Number.isFinite(value))) || (key==='text'&&!value.trim())) {this.help.textContent='入力値を確認してください。';return;}
        const before=this.snapshot();obj[key]=value;this.commit(before);
      });
    };
    inputField('rotation','回転（度）','number',-360,360);
    if(obj.type==='TUMOR'){inputField('size','サイズ（図上の単位）','number',4,120);inputField('note','腫瘍の注記（任意）','text');}
    if(obj.type==='TEXT')inputField('text','テキスト','text');
  }
  editable(id) {
    const obj=this.diagram.objects.find(o=>o.id===id);
    const key=id==='base'?'base':obj?config.layers[obj.type]:null;
    return key && this.diagram.layers[key].visible && !this.diagram.layers[key].locked;
  }
  point(event) {
    const point=new DOMPoint(event.clientX,event.clientY).matrixTransform(this.svg.getScreenCTM().inverse());
    return {x:Math.round(clamp(point.x,800)*10)/10,y:Math.round(clamp(point.y,500)*10)/10};
  }
  pointerDown(event) {
    if(event.button!==0)return;event.preventDefault();this.svg.focus({preventScroll:true});const point=this.point(event);
    if(this.tool==='SELECT') {
      const id=event.target.closest('[data-object]')?.dataset.object;
      this.selected=id && this.editable(id)?id:null;this.refresh();
      if(!this.selected)return;
      const obj=id==='base'?this.diagram.base_transform:this.diagram.objects.find(o=>o.id===id);
      this.drag={before:this.snapshot(),start:point,origin:{x:obj.x,y:obj.y},obj,drawing:false};
    } else {
      const layer=this.diagram.layers[config.layers[this.tool]];
      if(!layer.visible||layer.locked){this.help.textContent='対象レイヤーを表示し、ロックを解除してください。';return;}
      if(this.diagram.objects.length>=200){this.help.textContent='各図200個まで配置できます。';return;}
      const before=this.snapshot();const obj={id:crypto.randomUUID(),type:this.tool,x:point.x,y:point.y,rotation:0};
      if(this.tool==='TEXT') {const text=window.prompt('テキスト（架空情報のみ・500文字以内）');if(!text?.trim())return;if(text.length>500){this.help.textContent='テキストは500文字以内です。';return;}obj.text=text;}
      if(this.tool==='PORT')obj.number=this.diagram.next_port++;
      if(this.tool==='TUMOR'){obj.size=24;obj.note='';}
      if(['STAPLER','ENERGY_DEVICE'].includes(this.tool))obj.sequence=this.diagram.next_sequence++;
      if(drawingTypes.includes(this.tool))obj.points=[[0,0],[0,0]];
      this.diagram.objects.push(obj);this.selected=obj.id;
      if(obj.points)this.drag={before,start:point,obj,drawing:true};
      else {this.commit(before);return;}
    }
    this.svg.setPointerCapture(event.pointerId);
  }
  pointerMove(event) {
    if(!this.drag)return;const point=this.point(event);const {obj,start,origin,drawing}=this.drag;
    if(drawing) {
      const relative=[Math.round((point.x-start.x)*10)/10,Math.round((point.y-start.y)*10)/10];
      if(['INCISION','DIVISION_LINE'].includes(obj.type))obj.points[1]=relative;
      else if(obj.points.length<2000)obj.points.push(relative);
    } else {
      obj.x=Math.max(this.selected==='base'?-800:0,Math.min(800,origin.x+point.x-start.x));
      obj.y=Math.max(this.selected==='base'?-500:0,Math.min(500,origin.y+point.y-start.y));
    }
    renderDiagram(this.svg,this.diagram,this.selected);
  }
  pointerUp(event) {
    if(!this.drag)return;this.pointerMove(event);const {before,obj,drawing}=this.drag;this.drag=null;
    if(this.svg.hasPointerCapture(event.pointerId))this.svg.releasePointerCapture(event.pointerId);
    if(drawing && obj.points.every(p=>Math.hypot(...p)<2)){this.diagrams[this.index]=before;this.selected=null;this.refresh();return;}
    this.commit(before);
  }
  cancelDrag(){if(this.drag){this.diagrams[this.index]=this.drag.before;this.drag=null;this.selected=null;this.refresh();}}
  remove() {
    if(!this.selected||this.selected==='base'||!this.editable(this.selected))return;
    const before=this.snapshot();this.diagram.objects=this.diagram.objects.filter(o=>o.id!==this.selected);this.selected=null;this.commit(before);
  }
  travel(from,to) {
    if(!this.history[from].length)return;
    this.history[to].push(this.snapshot());this.diagrams[this.index]=this.history[from].pop();
    this.selected=null;this.changed();this.refresh();
  }
  keyDown(event) {
    if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='z'){event.preventDefault();this.travel(event.shiftKey?'redo':'undo',event.shiftKey?'undo':'redo');return;}
    if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();this.remove();return;}
    if(!this.selected||!this.editable(this.selected)||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
    event.preventDefault();const before=this.snapshot();const obj=this.selected==='base'?this.diagram.base_transform:this.diagram.objects.find(o=>o.id===this.selected);
    const amount=event.shiftKey?10:1;
    if(event.key==='ArrowLeft')obj.x-=amount;if(event.key==='ArrowRight')obj.x+=amount;if(event.key==='ArrowUp')obj.y-=amount;if(event.key==='ArrowDown')obj.y+=amount;
    obj.x=Math.max(this.selected==='base'?-800:0,Math.min(800,obj.x));obj.y=Math.max(this.selected==='base'?-500:0,Math.min(500,obj.y));this.commit(before);
  }
  setPosition(position) {
    // Body position is owned by the basic-information field, including after Undo.
    this.diagrams[0].position=position;
    for(const snapshot of [...this.histories[0].undo,...this.histories[0].redo])snapshot.position=position;
    if(this.index===0)this.refresh();
  }
}
