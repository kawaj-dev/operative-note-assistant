import {DiagramEditor, element, renderSaved} from './diagrams.js';

const form = document.querySelector('#note-form');
const steps = JSON.parse(document.querySelector('#field-config').textContent);
const fields = steps.flatMap(step => step[2]);
const initial = JSON.parse(document.querySelector('#initial-note').textContent);
const state = JSON.parse(document.querySelector('#editor-state').textContent);
const panels = [...document.querySelectorAll('[data-panel]')];
const error = document.querySelector('#form-error');
const statusText = document.querySelector('#save-status');
const draftButton = document.querySelector('#save-draft');
const progress = document.querySelector('.progress');
let current = state.step;
let version = 0;
let savedVersion = 0;
let timer;
let pending = null;
let completing = false;
let finished = false;
let conflict = false;
let saveError = false;

function scheduleSave() {
  clearTimeout(timer);
  if (!completing && !finished && !conflict) timer = setTimeout(() => persist('draft'), 1000);
}
function markDirty() {
  version += 1;
  document.querySelector('#fiction-confirm').checked = false;
  statusText.textContent = '変更あり・自動保存を待っています';
  scheduleSave();
}
const editor = new DiagramEditor(
  document.querySelector('#diagram-editor'),
  JSON.parse(document.querySelector('#initial-diagrams').textContent),
  markDirty,
  () => persist('draft', true),
  () => noteData(),
);

function repeatRows(field, values) {
  const parent = document.querySelector(`#${field.name}-rows`);
  parent.replaceChildren();
  const rows = values.length ? values : [''];
  rows.forEach((value, index) => {
    const row = element('div', undefined, 'repeat-row');
    const label = element('label', `${field.label} ${index + 1}`);
    const select = element('select');
    select.name = field.name;
    select.id = `${field.name}-${index}`;
    label.htmlFor = select.id;
    const empty = element('option', '選択してください');
    empty.value = '';
    select.append(empty);
    field.options.forEach(option => {
      const node = element('option', option);
      node.value = option;
      select.append(node);
    });
    select.value = value;
    const remove = element('button', '削除');
    remove.type = 'button';
    remove.disabled = rows.length === 1;
    remove.setAttribute('aria-label', `${field.label} ${index + 1}を削除`);
    remove.addEventListener('click', () => {
      const remaining = noteData()[field.name];
      remaining.splice(index, 1);
      repeatRows(field, remaining);
      markDirty();
    });
    row.append(label, select, remove);
    parent.append(row);
  });
  document.querySelector(`[data-add="${field.name}"]`).disabled = rows.length >= field.options.length;
}
for (const field of fields.filter(field => field.kind === 'repeat')) {
  repeatRows(field, initial[field.name]);
  document.querySelector(`[data-add="${field.name}"]`).addEventListener('click', () => {
    repeatRows(field, [...noteData()[field.name], '']);
    markDirty();
  });
}

function noteData() {
  const note = {};
  for (const field of fields) {
    const inputs = [...form.querySelectorAll(`[name="${field.name}"]`)];
    // Read hidden/disabled conditional controls too, so a draft retains work.
    note[field.name] = field.kind === 'checks' ? inputs.filter(input => input.checked).map(input => input.value)
      : field.kind === 'repeat' ? inputs.map(input => input.value) : inputs[0].value;
  }
  return note;
}
function visible(field, note) {
  return Object.entries(field.when).every(([name, value]) => note[name] === value);
}
function conditions() {
  const note = noteData();
  for (const field of fields) {
    const wrapper = form.querySelector(`[data-field="${field.name}"]`);
    const active = visible(field, note);
    wrapper.hidden = !active;
    wrapper.querySelectorAll('input,select,textarea').forEach(input => {
      input.disabled = !active;
      input.required = active && field.required;
    });
  }
}
function duration() {
  const {start_time: start, end_time: end} = noteData();
  if (!start || !end) return null;
  const minutes = value => Number(value.slice(0, 2)) * 60 + Number(value.slice(3));
  return (minutes(end) - minutes(start) + 1440) % 1440;
}
function updateDuration() {
  document.querySelector('#duration').textContent = duration() === null
    ? '開始・終了時刻を入力してください' : `${duration()} 分`;
}
function showError(message, fromSave = false) {
  saveError = fromSave;
  error.textContent = message;
  error.hidden = false;
}
function showStep(index, remember = true) {
  if (current === 7 && index !== 7) editor.cancelGesture();
  current = index;
  panels.forEach((panel, i) => panel.hidden = i !== index);
  document.querySelectorAll('[data-step]').forEach((button, i) => {
    if (i === index) button.setAttribute('aria-current', 'step');
    else button.removeAttribute('aria-current');
  });
  document.querySelector('#step-count').textContent = `${index + 1} / 10　${steps[index][0]}`;
  document.querySelector('#previous').disabled = index === 0;
  document.querySelector('#next').hidden = index === 9;
  document.querySelector('#save').hidden = index !== 9;
  if (index === 7) { editor.updateReference(); editor.refresh(); }
  if (index === 9) review();
  panels[index].querySelector('h2').focus({preventScroll: true});
  if (remember && (state.id || version > 0)) markDirty();
}
function review() {
  const parent = document.querySelector('#review');
  parent.replaceChildren();
  const note = noteData();
  for (const [title, , items] of steps) {
    if (!items.length) continue;
    const section = element('section', undefined, 'detail-section');
    section.append(element('h3', title));
    const list = element('dl', undefined, 'record-grid');
    for (const field of items.filter(field => visible(field, note))) {
      const value = note[field.name];
      const text = Array.isArray(value) ? value.filter(Boolean).join('、') : value;
      const row = element('div');
      row.append(element('dt', field.label), element('dd', text || '未記録'));
      list.append(row);
    }
    if (title === '基本情報') {
      const row = element('div');
      row.append(element('dt', '手術時間'), element('dd', duration() === null ? '未記録' : `${duration()} 分`));
      list.append(row);
    }
    section.append(list);
    parent.append(section);
  }
  const diagrams = element('div');
  parent.append(element('h3', '手術図'), diagrams);
  renderSaved(diagrams, editor.diagrams);
}
function savedTime(value) {
  const normalized = value.includes('T') ? value : value.replace(' ', 'T') + 'Z';
  return new Date(normalized).toLocaleTimeString('ja-JP', {hour: '2-digit', minute: '2-digit'});
}

async function persist(status, manual = false) {
  clearTimeout(timer);
  // Serialize writes. A response for an older snapshot must not mark new edits saved.
  while (pending) await pending;
  if (conflict || finished) return false;
  if (status === 'draft' && state.id && version === savedVersion) return true;
  const sentVersion = version;
  const payload = {
    status, note: noteData(), diagrams: structuredClone(editor.diagrams),
    step: current, revision: state.revision, creation_key: state.creation_key,
  };
  statusText.textContent = '保存中...';
  draftButton.disabled = true;
  let replayed = false;
  pending = (async () => {
    try {
      const response = await fetch(state.id ? `/notes/${state.id}` : '/notes', {
        method: state.id ? 'PUT' : 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': document.querySelector('meta[name=csrf-token]').content},
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        conflict = Boolean(data.conflict);
        throw new Error(data.error || '保存できませんでした。');
      }
      state.id = data.id;
      state.revision = data.revision;
      replayed = data.replayed;
      if (!replayed) savedVersion = sentVersion;
      if (data.status === 'completed') {
        finished = true;
        window.location.assign(data.url);
      } else {
        window.history.replaceState(null, '', data.url);
        statusText.textContent = `${manual ? '下書きを保存しました' : '自動保存しました'} ${savedTime(data.updated_at)}`;
        if (saveError) error.hidden = true;
      }
      return true;
    } catch (caught) {
      statusText.textContent = status === 'draft' ? '自動保存に失敗しました・未保存の変更があります' : '完成保存できませんでした';
      showError(caught.message || '接続を確認して下書き保存で再試行してください。', true);
      return false;
    }
  })();
  const success = await pending;
  pending = null;
  draftButton.disabled = completing || conflict;
  if (success && !finished) {
    // If a create response was lost, re-use its returned identity before retrying.
    if (replayed) return persist(status, manual);
    if (version !== savedVersion) scheduleSave();
  }
  return success;
}

for (const button of document.querySelectorAll('[data-step]')) {
  button.addEventListener('click', () => showStep(Number(button.dataset.step)));
}
document.querySelector('#previous').addEventListener('click', () => showStep(Math.max(0, current - 1)));
document.querySelector('#next').addEventListener('click', () => showStep(Math.min(9, current + 1)));
draftButton.addEventListener('click', () => persist('draft', true));
function inputChanged(event) {
  if (!event.target.name) return;
  conditions();
  if (event.target.name === 'position') editor.setPosition(event.target.value);
  editor.updateReference();
  updateDuration();
  error.hidden = true;
  markDirty();
}
form.addEventListener('input', inputChanged);
form.addEventListener('change', inputChanged);
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (completing || conflict) return;
  if (current !== 9) { showStep(Math.min(9, current + 1)); return; }
  conditions();
  const note = noteData();
  const missing = fields.filter(field => field.required && visible(field, note) && !note[field.name].trim());
  if (missing.length) {
    const index = steps.findIndex(step => step[2].includes(missing[0]));
    showStep(index);
    showError('完成に必要な項目が未入力です：' + missing.map(field => field.label).join('、'));
    document.getElementById(missing[0].name).focus();
    return;
  }
  const invalid = [...form.querySelectorAll('input[name],select[name],textarea[name]')].find(input => !input.disabled && !input.checkValidity());
  if (invalid) {
    showStep(Number(invalid.closest('[data-panel]').dataset.panel));
    invalid.reportValidity();
    return;
  }
  if (!document.querySelector('#fiction-confirm').checked) {
    showError('入力内容がすべて架空であることを確認してください。');
    return;
  }
  if (Boolean(note.start_time) !== Boolean(note.end_time)) {
    showStep(0);
    showError('完成保存時は開始時刻と終了時刻を両方入力してください。');
    return;
  }
  completing = true;
  clearTimeout(timer);
  form.inert = true;
  progress.inert = true;
  draftButton.disabled = true;
  await persist('completed');
  completing = false;
  form.inert = false;
  progress.inert = false;
  draftButton.disabled = conflict;
});
window.addEventListener('beforeunload', event => {
  if (!finished && (version !== savedVersion || pending)) {
    event.preventDefault();
    event.returnValue = '';
  }
});
document.addEventListener('visibilitychange', () => {
  if (document.hidden && !completing && version !== savedVersion) persist('draft');
});
conditions();
updateDuration();
showStep(current, false);
if (state.updated_at) statusText.textContent = `下書き保存済み ${savedTime(state.updated_at)}`;
