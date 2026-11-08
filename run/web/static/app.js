'use strict';

const $ = (sel, el = document) => el.querySelector(sel);

const state = {
  pendingRename: null,
  root: null, collection: false, home: '', ops: [], tools: {},
  files: [], shown: [], selected: new Set(), anchor: null, cards: new Map(), infoToken: 0,
};

const GROUP_TITLES = { photos: 'Photographs', videos: 'Videos', metadata: 'Metadata', folder: 'Whole folder' };
const KIND_ICON = { image: '🖼️', raw: '📷', video: '🎞️' };
const MAX_PLAN_ROWS = 300;
const MAX_CAPTION_ROWS = 200;
let activeTool = null;
const isDesktop = document.documentElement.dataset.desktop === 'true' || window.location.protocol === 'file:';
const desktopReady = new Promise(resolve => {
  if (window.pywebview?.api) resolve();
  else window.addEventListener('pywebviewready', resolve, { once: true });
});
if (isDesktop) {
  $('.brand').addEventListener('click', event => event.preventDefault());
  $('#root-form').hidden = true;
  $('#subdirs-label').hidden = true;
  $('#desktop-drop-note').hidden = true;
}

// ---------- helpers ----------

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

async function api(path, { method = 'GET', body } = {}) {
  let res;
  if (isDesktop) {
    await desktopReady;
    if (!window.pywebview?.api) throw new Error('The Archivist desktop bridge is unavailable.');
    const result = await window.pywebview.api.request(method, '/api' + path, body === undefined ? null : body);
    const binary = atob(result.body);
    const bytes = Uint8Array.from(binary, ch => ch.charCodeAt(0));
    res = new Response(bytes.length ? bytes : null, {
      status: result.status,
      headers: { 'Content-Type': result.content_type },
    });
  } else {
    res = await fetch('/api' + path, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const data = await res.json();
      msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    } catch (_) { /* keep status text */ }
    throw new Error(msg);
  }
  return res;
}
const getJson = async (path, opts) => (await api(path, opts)).json();
const enc = encodeURIComponent;

async function assetUrl(path) {
  if (!isDesktop) return path;
  const res = await api(path.replace(/^\/api/, ''));
  const blob = await res.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error || new Error('Could not load preview.'));
    reader.readAsDataURL(blob);
  });
}
window.archivistAssetUrl = assetUrl;

async function setImageSource(image, path) {
  try {
    const source = await assetUrl(path);
    if (image.isConnected) image.src = source;
  } catch (err) {
    console.warn('Could not load media preview:', err);
  }
}

async function mediaUrl(path) {
  if (!isDesktop) return `/api/file?path=${enc(path)}`;
  await desktopReady;
  if (!window.pywebview?.api) throw new Error('The Archivist desktop bridge is unavailable.');
  return window.pywebview.api.media_url(path);
}

function createDesktopJobStream(jobId, onMessage, onError) {
  let closed = false, timer;
  let since = 0;
  const stream = {
    close() {
      closed = true;
      clearTimeout(timer);
    },
  };
  async function poll() {
    try {
      const snapshot = await getJson(`/jobs/${jobId}?since=${since}`);
      since = snapshot.next;
      onMessage(snapshot);
      if (!closed && snapshot.status === 'running') timer = setTimeout(poll, 400);
    } catch (err) {
      stream.close();
      onError(err);
    }
  }
  poll();
  return stream;
}

let toastTimer;
function toast(message, kind = 'error') {
  const el = $('#toast');
  el.textContent = message;
  el.className = 'toast ' + kind;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 6000);
}

const selectedFiles = () => state.files.filter(f => state.selected.has(f.path));
const formatBytes = n => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`;

// ---------- folder + file list ----------

async function loadState() {
  const s = await getJson('/state');
  state.ops = s.ops;
  state.home = s.home;
  state.tools = s.tools;
  state.root = s.root;
  state.collection = !!s.collection;
  $('#root-input').value = s.root || '';
  if (s.root || state.collection) await loadFiles();
  else renderAll();
}

async function openRoot(path) {
  try {
    const res = await getJson('/root', { method: 'POST', body: { path } });
    state.root = res.root;
    state.collection = false;
    const current = await getJson('/state');
    state.ops = current.ops;
    $('#root-input').value = res.root;
    state.selected.clear();
    await loadFiles();
  } catch (err) { toast(err.message); }
}

async function loadFiles() {
  try {
    const data = await getJson(`/files?subdirs=${$('#subdirs').checked}`);
    state.files = data.files.slice(0, 1);
    state.collection = !!data.collection;
    state.root = data.root;
    const existing = new Set(data.files.map(f => f.path));
    state.selected = new Set(state.files.map(f => f.path));
    if (data.truncated) toast('Folder is very large; only the first files are shown.', 'info');
    renderAll();
  } catch (err) { toast(err.message); }
}

window.archivistFilesDropped = async result => {
  if (!result.added && !result.skipped) return;
  if (!result.added) {
    toast('Choose just one supported photo or video at a time.', 'info');
    return;
  }
  try {
    const s = await getJson('/state');
    state.root = s.root;
    state.collection = !!s.collection;
    state.ops = s.ops;
    state.tools = s.tools;
    $('#root-input').value = s.root || '';
    state.selected.clear();
    await loadFiles();
    toast('File opened. Choose an action in the sidebar.', 'info');
  } catch (err) { toast(err.message); }
};

window.archivistDropFailed = message => toast(message);

function renderAll() { applyFilters(); renderSide(); }

function applyFilters() {
  const kinds = new Set([...document.querySelectorAll('.kind-filter:checked')].map(i => i.value));
  const q = $('#search').value.trim().toLowerCase();
  state.shown = state.files.filter(f => kinds.has(f.kind)
    && (!q || `${f.name} ${f.location || f.path}`.toLowerCase().includes(q)));
  renderGrid();
}




// The file name shows as a button; clicking it swaps in an input for the name (the extension stays fixed).
function filenameEditor(file) {
  const dot = file.name.lastIndexOf('.');
  const ext = dot > 0 ? file.name.slice(dot) : '';
  const stem = ext ? file.name.slice(0, dot) : file.name;
  const wrap = h('div', { class: 'filename-wrap' });

  const showName = () => {
    wrap.replaceChildren(h('button', { type: 'button', class: 'filename-btn', title: 'Click to rename', onclick: edit },
      h('span', { class: 'filename' }, file.name), h('span', { class: 'pencil', 'aria-hidden': 'true' }, '✎')));
  };

  function edit() {
    const input = h('input', { type: 'text', class: 'filename-input', value: stem, 'aria-label': `New name for ${file.name} (extension ${ext || 'none'} is kept)`, autocomplete: 'off', spellcheck: 'false' });
    let busy = false, done = false;
    const cancel = () => { done = true; showName(); };
    async function commit() {
      if (busy || done) return;
      const name = input.value.trim();
      if (!name || name === stem) { cancel(); return; }
      busy = true;
      input.disabled = true;
      try {
        const res = await getJson('/rename', { method: 'POST', body: { path: file.path, name } });
        done = true;
        state.selected.delete(file.path);
        state.selected.add(res.path);
        if (state.anchor === file.path) state.anchor = res.path;
        await loadFiles();
        toast(`Renamed to ${res.name}`, 'info');
      } catch (err) {
        busy = false;
        input.disabled = false;
        input.focus();
        toast(err.message);
      }
    }
    input.addEventListener('keydown', e => {
      e.stopPropagation();
      if (e.key === 'Enter') { e.preventDefault(); commit(); }
      else if (e.key === 'Escape') { e.preventDefault(); cancel(); }
    });
    input.addEventListener('blur', () => { setTimeout(() => { if (!busy) commit(); }, 0); });
    wrap.replaceChildren(h('div', { class: 'filename-edit' }, input, ext && h('span', { class: 'ext' }, ext)));
    input.focus();
    input.select();
  }

  showName();
  return wrap;
}


async function loadInfo(file, target) {
  const token = ++state.infoToken;
  target.textContent = 'Loading…';
  try {
    const data = await getJson(`/info?path=${enc(file.path)}`);
    if (token !== state.infoToken) return;
    target.replaceChildren(...data.sections.map((s, i) => h('details', { open: i < 2 },
      h('summary', {}, s.title), h('table', {}, s.rows.map(([k, v]) => h('tr', {}, h('td', {}, k), h('td', {}, v)))))));
  } catch (err) {
    if (token === state.infoToken) target.textContent = err.message;
  }
}

// ---------- folder browser ----------

function openBrowse(startPath, onChoose, chooseFile = false) {
  const dlg = $('#browse-dialog');
  let current = '';
  async function go(path) {
    try {
      const data = await getJson(`/browse?path=${enc(path || '')}`);
      current = data.path;
      $('#browse-path').textContent = current;
      const list = $('#browse-list');
      list.replaceChildren();
      if (data.parent) list.append(h('li', { onclick: () => go(data.parent) }, '⬆️  ..'));
      data.folders.forEach(name => list.append(h('li', { onclick: () => go(current.replace(/[\\/]+$/, '') + (current.includes('\\') ? '\\' : '/') + name) }, '📁 ' + name)));
      if (chooseFile) data.files.forEach(name => list.append(h('li', {}, h('button', { type: 'button', onclick: () => { dlg.close(); onChoose(current.replace(/[\\/]+$/, '') + '/' + name); } }, name))));
    } catch (err) { toast(err.message); }
  }
  $('#browse-cancel').onclick = () => dlg.close();
  $('#browse-choose').onclick = () => { dlg.close(); onChoose(current); };
  $('#browse-choose').hidden = chooseFile;
  dlg.querySelector('h2').textContent = chooseFile ? 'Open a photo or video' : 'Choose a folder';
  go(startPath);
  dlg.showModal();
}

// ---------- operation dialog ----------

function toolTitle(op) {
  return { crop: 'Crop image', burnin_basic: 'Add date & text', burnin_caption: 'Add a caption band', burnin_video: 'Add date & text', rename_digital: 'Rename from capture date', rename_film: 'Rename with a custom date', rename_videos: 'Rename video', export_metadata: 'Export metadata', import_metadata: 'Import metadata', clone_metadata: 'Copy metadata from another image' }[op.id] || op.label;
}
function toolDescription(op) {
  return { crop: 'Draw a crop on the image, or choose an aspect ratio.', burnin_basic: 'Add a date and optional text to your image.', burnin_caption: 'Add a caption band below your image. The preview updates as you type.', burnin_video: 'Add a date and optional text to your video.', rename_digital: 'Name your file using its capture date and an optional suffix.', rename_film: 'Name your scan using a date you provide.', rename_videos: 'Name your video using its creation date.', export_metadata: 'Save this image’s metadata beside it as CSV or JSON. Overwrite replaces an earlier export, never the image.', import_metadata: 'Read matching metadata from a CSV or JSON file and apply it to this image.', clone_metadata: 'Copy metadata and timestamps from a source image to this image.' }[op.id] || op.description;
}
function paramVisible(param, values) {
  if (!param.show_if) return true;
  return Object.entries(param.show_if).every(([k, v]) => typeof v === 'boolean' ? !!values[k] === v : values[k] === v);
}

function openOp(op) {
  activeTool?.dispose();
  const dlg = $('#side');
  const files = op.scope === 'files' ? selectedFiles().filter(f => op.accepts.includes(f.kind)) : [];
  const ctx = { op, files, plan: null, answers: {}, inputs: {}, captionInputs: {}, cropEditor: null, running: false, logCount: 0 };
  const isRename = op.id.startsWith('rename_');
  let saveMode = 'copy', planningVersion = 0;
  let previewTimer, previewVersion = 0, previewUrl = null;
  const dispose = () => {
    planningVersion++;
    clearTimeout(previewTimer);
    previewVersion++;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    ctx.cropEditor?.destroy();
    activeTool = null;
    $('#media-stage').dataset.path = '';
  };
  activeTool = { path: files[0]?.path, dispose };
  const back = () => {
    if (ctx.running) return;
    dispose();
    renderGrid();
    renderSide();
  };

  const fields = h('fieldset', { class: 'fields', style: 'border:0;padding:0;margin:0' });
  const planArea = h('div', { class: 'plan' });
  const jobArea = h('div', { class: 'job' });
  const closeBtn = h('button', { type: 'button', class: 'tool-back', onclick: back }, '← All tools');
  const reviewBtn = h('button', { type: 'button', class: 'primary', onclick: () => runPlan() }, 'Review changes');
  const applyBtn = h('button', { type: 'button', class: op.destructive ? 'danger' : 'primary', hidden: true, disabled: true, onclick: () => applyPlan() }, 'Apply');
  const cancelBtn = h('button', { type: 'button', hidden: true, onclick: () => ctx.jobId && api(`/jobs/${ctx.jobId}/cancel`, { method: 'POST' }) }, 'Cancel job');
  const copyBtn = h('button', { type: 'button', class: 'primary', onclick: () => save('copy') }, 'Save as copy');
  const overwriteBtn = h('button', { type: 'button', onclick: () => save('overwrite') }, 'Save and overwrite');
  const saveButtons = [copyBtn, overwriteBtn];

  const scopeText = op.scope === 'folder'
    ? `Applies to every supported file in ${state.root} (including subfolders), regardless of the current selection.`
    : files[0]?.name || 'No file open.';
  dlg.replaceChildren(
    closeBtn,
    h('h2', {}, toolTitle(op)), h('p', { class: 'muted' }, toolDescription(op)), h('p', {}, scopeText),
    fields, planArea, jobArea, h('div', { class: 'tool-actions' }, cancelBtn, ...(isRename ? [reviewBtn, applyBtn] : saveButtons)));
  dlg.scrollTop = 0;

  const refreshVisibility = () => {
    const values = collectParams(false);
    for (const p of op.params) ctx.inputs[p.name].wrap.classList.toggle('hidden', hiddenParam(p) || !paramVisible(p, values));
  };
  function hiddenParam(p) { return ['overwrite', 'output_dir', 'include_raw', 'include_video'].includes(p.name) || (op.editor === 'crop' && p.name === 'ratio'); }
  const invalidate = () => {
    planningVersion++;
    schedulePreview();
    if (ctx.running || !ctx.plan) return;
    ctx.plan = null;
    ctx.answers = {};
    planArea.replaceChildren(h('p', { class: 'muted' }, 'Options changed. Review the changes again.'));
    applyBtn.hidden = true;
  };

  function collectParams(withCaptions = true) {
    const out = {};
    for (const p of op.params) {
      const el = ctx.inputs[p.name].el;
      out[p.name] = p.kind === 'bool' ? el.checked : el.value.trim();
    }
    out.overwrite = saveMode === 'overwrite';
    out.save_mode = saveMode;
    if ('output_dir' in out) out.output_dir = op.id === 'export_metadata' ? (files[0].location || files[0].path).replace(/[\\/][^\\/]+$/, '') : '';
    if ('include_raw' in out) out.include_raw = files[0]?.kind === 'raw';
    if ('include_video' in out) out.include_video = files[0]?.kind === 'video';
    if (withCaptions) {
      out.captions = {};
      for (const [path, el] of Object.entries(ctx.captionInputs)) if (el.value.trim()) out.captions[path] = el.value.trim();
      if (ctx.cropEditor) out.crops = ctx.cropEditor.getCrops();
    }
    return out;
  }

  for (const p of op.params) {
    let el, datalist = null;
    const id = `param-${op.id}-${p.name}`;
    if (p.kind === 'bool') el = h('input', { type: 'checkbox', id, checked: !!p.default });
    else if (p.kind === 'choice') {
      const isFont = p.name === 'font';
      el = h('select', { id, style: isFont ? `font-family: "${p.default}", serif` : null },
        p.choices.map(([v, label]) => h('option', { value: v, selected: v === p.default, style: isFont ? `font-family: "${v}"` : null }, label)));
      if (isFont) el.addEventListener('change', () => { el.style.fontFamily = `"${el.value}", serif`; });
    }
    else {
      el = h('input', { type: 'text', id, value: p.default ?? '', placeholder: p.kind === 'date' ? 'YYYYMMDD' : '', autocomplete: 'off' });
      if (p.kind === 'file') {
        datalist = h('datalist', { id: id + '-list' }, state.files.filter(f => f.kind !== 'video').slice(0, 5000).map(f => h('option', { value: f.path })));
        el.setAttribute('list', id + '-list');
      }
    }
    el.addEventListener('input', () => { invalidate(); refreshVisibility(); });
    el.addEventListener('change', () => { invalidate(); refreshVisibility(); });
    let control = el;
    if (p.kind === 'path' && p.name.endsWith('_dir')) {
      control = h('div', { class: 'path-row' }, el, h('button', { type: 'button', onclick: () => openBrowse(el.value || state.root, path => { el.value = path; el.dispatchEvent(new Event('input')); }) }, 'Browse…'));
    }
    const wrap = h('div', { class: 'field' },
      p.kind === 'bool'
        ? h('label', { class: 'inline' }, el, ' ', p.label + (p.required ? ' *' : ''))
        : [h('label', { class: 'title', for: id }, p.name === 'date' ? 'Date' : p.label + (p.required ? ' *' : '')), control],
      datalist, p.help && !['text', 'suffix', 'source'].includes(p.name) && h('div', { class: 'help' }, p.name === 'font' ? 'Choose a font to see it in the live preview.' : p.help));
    ctx.inputs[p.name] = { el, wrap };
    fields.append(wrap);
  }
  refreshVisibility();

  if (op.editor === 'crop' && files.length) {
    ctx.cropEditor = createCropEditor(files, invalidate);
    const canvas = $('#media-stage .preview-canvas');
    canvas.replaceChildren(ctx.cropEditor.el);
    fields.prepend(ctx.cropEditor.el.querySelector('.crop-toolbar'));
  }

  const previewImg = $('#media-stage .full-preview');
  const previewStatus = h('p', { class: 'help', role: 'status', 'aria-live': 'polite' });
  if (op.previewable) fields.append(previewStatus);
  function schedulePreview() {
    if (!op.previewable || ctx.running) return;
    clearTimeout(previewTimer);
    const version = ++previewVersion;
    previewStatus.textContent = 'Updating preview…';
    previewTimer = setTimeout(() => previewFile(files[0], ctx.captionInputs[files[0].path]?.value || '', version), 350);
  }
  async function previewFile(file, caption, version) {
    try {
      const res = await api(`/ops/${op.id}/preview`, { method: 'POST', body: { path: file.path, params: collectParams(false), caption } });
      const url = URL.createObjectURL(await res.blob());
      if (version !== previewVersion || !previewImg?.isConnected) { URL.revokeObjectURL(url); return; }
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = url;
      previewImg.src = url;
      previewImg.hidden = false;
      previewStatus.textContent = 'Live preview · original unchanged';
    } catch (err) {
      if (version === previewVersion) previewStatus.textContent = `Preview unavailable: ${err.message}`;
    }
  }

  if (op.captions === 'required' && files.length) {
    const box = h('div', { class: 'field' });
    for (const f of files.slice(0, MAX_CAPTION_ROWS)) {
      const input = h('input', { type: 'text', placeholder: 'Caption', 'aria-label': 'Caption for ' + f.name });
      input.addEventListener('input', invalidate);
      ctx.captionInputs[f.path] = input;
      input.id = 'image-caption';
      box.append(h('label', { class: 'title', for: input.id }, 'Caption'), input);
    }
    fields.append(box);
  }
  if (op.previewable && files.length) schedulePreview();

  async function runPlan() {
    const version = ++planningVersion;
    reviewBtn.disabled = true;
    try {
      const plan = await getJson(`/ops/${op.id}/plan`, { method: 'POST', body: { paths: files.map(f => f.path), params: collectParams(), answers: ctx.answers } });
      if (version !== planningVersion) return false;
      ctx.plan = plan;
      renderPlan();
      return plan.ready;
    } catch (err) {
      ctx.plan = null;
      planArea.replaceChildren(h('div', { class: 'notice error' }, err.message));
      applyBtn.hidden = true;
    } finally { reviewBtn.disabled = false; }
  }

  async function save(mode) {
    if (ctx.running) return;
    saveMode = mode;
    saveButtons.forEach(b => { b.disabled = true; });
    try {
      if (!await runPlan()) return;
      if (mode === 'overwrite' && !window.confirm(op.id === 'export_metadata'
        ? 'Replace the existing exported metadata file? The photo itself will not be changed.'
        : `Save changes over “${files[0].name}”? This will replace the original file and cannot be undone.`)) {
        ctx.plan = null;
        planArea.replaceChildren();
        return;
      }
      await applyPlan();
    } finally { if (!ctx.running) saveButtons.forEach(b => { b.disabled = false; }); }
  }

  function renderPlan() {
    const plan = ctx.plan;
    planArea.replaceChildren();
    plan.errors.forEach(m => planArea.append(h('div', { class: 'notice error' }, m)));
    plan.warnings.forEach(m => planArea.append(h('div', { class: 'notice warn' }, m)));
    if (plan.ready) planArea.append(h('p', {}, h('strong', {}, isRename ? 'Ready to rename.' : 'Ready to save.')));
    if (plan.questions.length) {
      planArea.append(h('h3', {}, 'Please answer'));
      for (const q of plan.questions) {
        const name = `q-${q.id}`;
        const radio = (value, label) => h('label', {}, h('input', { type: 'radio', name, value, onchange: () => {
          ctx.answers[q.id] = value === 'yes';
          if (plan.questions.every(x => x.id in ctx.answers)) runPlan();
        } }), ' ' + label);
        planArea.append(h('div', { class: 'question' }, h('div', {}, q.prompt), h('div', { class: 'detail' }, q.detail), radio('yes', 'Yes, group them'), radio('no', 'No, keep separate')));
      }
    }
    for (const item of plan.items) {
      if (item.target) planArea.append(h('p', { class: 'save-destination' }, 'Save to: ', item.target === files[0].path ? files[0].location || files[0].name : item.target));
      if (item.note) planArea.append(h('p', { class: 'muted' }, item.note));
    }
    let confirmInput = null;
    if (plan.confirmation) {
      confirmInput = h('input', { type: 'text', placeholder: plan.confirmation.expected, autocomplete: 'off', 'aria-label': 'Confirmation' });
      confirmInput.addEventListener('input', update);
      planArea.append(h('div', { class: 'field' }, h('label', { class: 'title' }, `${plan.confirmation.message} ${plan.confirmation.expected}`), confirmInput));
    }
    ctx.confirmInput = confirmInput;
    function update() {
      applyBtn.disabled = !(plan.ready && (!plan.confirmation || confirmInput.value === plan.confirmation.expected));
    }
    applyBtn.hidden = false;
    update();
  }

  async function applyPlan() {
    ctx.running = true;
    closeBtn.disabled = $('#open-file').disabled = true;
    fields.disabled = reviewBtn.disabled = applyBtn.disabled = true;
    try {
      const res = await getJson(`/ops/${op.id}/apply`, { method: 'POST', body: { plan_id: ctx.plan.plan_id, confirm: ctx.confirmInput ? ctx.confirmInput.value : null } });
      ctx.jobId = res.job_id;
      startJob();
    } catch (err) {
      ctx.running = false;
      closeBtn.disabled = $('#open-file').disabled = false;
      fields.disabled = reviewBtn.disabled = applyBtn.disabled = false;
      toast(err.message);
    }
  }

  function startJob() {
    ctx.running = true;
    saveButtons.forEach(b => { b.hidden = true; });
    clearTimeout(previewTimer);
    previewVersion++;
    $('#open-file').disabled = true;
    closeBtn.disabled = true;
    fields.disabled = true;
    planArea.hidden = true;
    reviewBtn.hidden = applyBtn.hidden = true;
    cancelBtn.hidden = false;
    const bar = h('div', {});
    const status = h('div', { class: 'muted' }, 'Starting…');
    const log = h('div', { class: 'log' });
    jobArea.replaceChildren(h('h3', {}, 'Progress'), h('div', { class: 'progress' }, bar), status, log);
    const handleSnapshot = s => {
      const first = s.next - s.logs.length;
      s.logs.forEach((entry, i) => {
        if (first + i < ctx.logCount) return;
        log.append(h('div', { class: entry.level }, entry.message));
      });
      ctx.logCount = Math.max(ctx.logCount, s.next);
      log.scrollTop = log.scrollHeight;
      const p = s.progress;
      const pct = p.total ? Math.min(100, ((p.done + p.fraction) / p.total) * 100) : 0;
      bar.style.width = pct + '%';
      status.textContent = s.status === 'running' ? `${p.done} of ${p.total} · ${p.label}` : '';
      if (s.status !== 'running') {
        es.close();
        finishJob(s, jobArea);
      }
    };
    const es = isDesktop
      ? createDesktopJobStream(ctx.jobId, handleSnapshot, err => toast(err.message))
      : new EventSource(`/api/jobs/${ctx.jobId}/events`);
    if (!isDesktop) es.onmessage = ev => handleSnapshot(JSON.parse(ev.data));
  }

  async function finishJob(s) {
    ctx.running = false;
    $('#open-file').disabled = false;
    closeBtn.disabled = false;
    cancelBtn.hidden = true;
    closeBtn.hidden = false;
    const kind = s.status === 'done' && !s.counts.failed ? 'ok' : s.status === 'done' ? 'warn' : 'error';
    const text = s.status === 'cancelled' ? 'Cancelled.' : s.status === 'error' ? `Stopped by an error: ${s.error}` : 'Finished.';
    jobArea.prepend(h('div', { class: 'notice ' + kind }, s.status === 'done' && s.counts.ok ? 'Saved successfully.' : text));
    state.selected.clear();
    $('#media-stage').dataset.path = '';
    await loadFiles();
  }

  closeBtn.focus({ preventScroll: true });
}

// ---------- startup ----------

async function chooseMedia() {
  try {
    if (isDesktop) {
      await desktopReady;
      await window.archivistFilesDropped(await window.pywebview.api.choose_file());
    } else {
      openBrowse(state.home, async path => {
        try {
          await window.archivistFilesDropped(await getJson('/open-file', { method: 'POST', body: { path } }));
        } catch (err) { toast(err.message); }
      }, true);
    }
  } catch (err) { toast(err.message); }
}

function renderGrid() {
  const stage = $('#media-stage');
  const file = state.files[0];
  if (activeTool && activeTool.path !== file?.path) activeTool.dispose();
  const empty = $('#empty');
  empty.replaceChildren();
  stage.hidden = !file;
  $('#open-file').textContent = file ? 'Open another file' : 'Open photo or video';
  if (!file) {
    stage.replaceChildren();
    empty.append(h('div', { class: 'empty-mark', 'aria-hidden': 'true' }, '＋'),
      h('p', { class: 'eyebrow' }, 'ONE FILE. YOUR FULL ATTENTION.'),
      h('h1', {}, 'Give your memories a little care.'),
      h('p', {}, 'Open a photo or video to preview, crop, add text, or manage its details.'),
      h('button', { type: 'button', class: 'primary', onclick: chooseMedia }, 'Open photo or video'),
      h('p', { class: 'empty-footnote' }, isDesktop ? 'Or drop one file anywhere in this window.' : 'Choose one file from your computer.'));
    return;
  }
  // Keep the current player mounted when an operation refreshes file details.
  if (stage.dataset.path === file.path && stage.dataset.name === file.name) return;
  stage.dataset.path = file.path;
  stage.dataset.name = file.name;
  const media = file.kind === 'video'
    ? h('video', { controls: true, preload: 'metadata', class: 'full-preview', 'aria-label': file.name })
    : h('img', { class: 'full-preview', alt: file.name });
  const error = h('p', { class: 'preview-error', hidden: true }, 'A preview is unavailable for this format. You can still use the tools in the sidebar.');
  media.addEventListener('error', () => { media.hidden = true; error.hidden = false; });
  stage.replaceChildren(h('div', { class: 'stage-heading' }, h('span', {}, file.kind === 'video' ? 'VIDEO PREVIEW' : 'PHOTO PREVIEW'), h('span', {}, formatBytes(file.size))),
    h('div', { class: 'preview-canvas' }, media, error), h('div', { class: 'stage-caption' }, file.name));
  if (file.kind === 'video') mediaUrl(file.path).then(src => { if (media.isConnected) media.src = src; }).catch(err => toast(err.message));
  else setImageSource(media, `/api/preview?path=${enc(file.path)}`);
}

function renderSide() {
  if (activeTool) return;
  const side = $('#side');
  const file = state.files[0];
  $('.layout').classList.toggle('no-side', !file);
  side.replaceChildren();
  if (!file) return;
  side.append(h('p', { class: 'eyebrow' }, 'YOUR WORKSPACE'), h('h2', {}, 'Make it yours'),
    h('p', { class: 'muted' }, 'Choose a tool, adjust its options, then review your changes.'),
    filenameEditor(file));
  const names = { photos: 'Photo tools', videos: 'Video tools', metadata: 'File details' };
  const labels = { crop: 'Crop image', burnin_basic: 'Add date & text', burnin_verbose: 'Add a caption band', rename_digital: 'Rename from capture date', rename_film: 'Rename with a custom date' };
  for (const group of ['photos', 'videos', 'metadata']) {
    const actions = state.ops.filter(op => op.group === group && op.scope === 'files' && op.accepts.includes(file.kind));
    if (!actions.length) continue;
    side.append(h('h3', {}, names[group]));
    for (const op of actions) {
      const unavailable = group === 'videos' && !state.tools.ffmpeg;
      side.append(h('button', { type: 'button', class: 'tool-button', disabled: unavailable, onclick: () => openOp(op) },
        h('span', { class: 'tool-title' }, toolTitle(op), h('span', { 'aria-hidden': 'true' }, ' →')),
        h('span', { class: 'tool-description' }, unavailable ? 'Install ffmpeg to use video tools.' : toolDescription(op))));
    }
  }
  const meta = h('div', { class: 'meta' });
  side.append(h('h3', {}, 'About this file'), h('div', { class: 'muted file-path' }, file.location || file.path), meta,
    h('p', { class: 'sidebar-note' }, 'Files stay on your computer. Crop and text tools save a new copy by default.'));
  loadInfo(file, meta);
}

$('#open-file').addEventListener('click', chooseMedia);


loadState().catch(err => toast(err.message));
