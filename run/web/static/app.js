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
const isDesktop = document.documentElement.dataset.desktop === 'true' || window.location.protocol === 'file:';
const desktopReady = new Promise(resolve => {
  if (window.pywebview?.api) resolve();
  else window.addEventListener('pywebviewready', resolve, { once: true });
});
if (isDesktop) {
  $('.brand').addEventListener('click', event => event.preventDefault());
  $('#root-form').hidden = true;
  $('#subdirs-label').hidden = true;
  $('#desktop-drop-note').hidden = false;
  $('#drop-zone').hidden = false;
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
    state.files = data.files;
    state.collection = !!data.collection;
    state.root = data.root;
    const existing = new Set(data.files.map(f => f.path));
    state.selected = new Set([...state.selected].filter(p => existing.has(p)));
    if (data.truncated) toast('Folder is very large; only the first files are shown.', 'info');
    renderAll();
  } catch (err) { toast(err.message); }
}

window.archivistFilesDropped = async result => {
  if (!result.added && !result.skipped) return;
  if (!result.added) {
    toast(`No photos were added; skipped ${result.skipped} unsupported or duplicate item${result.skipped === 1 ? '' : 's'}.`, 'info');
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
    toast(`Added ${result.added} photo${result.added === 1 ? '' : 's'}${result.skipped ? `; skipped ${result.skipped}` : ''}.`, 'info');
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

function renderGrid() {
  const grid = $('#grid');
  grid.replaceChildren();
  state.cards.clear();
  const frag = document.createDocumentFragment();
  for (const f of state.shown) {
    const thumb = h('div', { class: 'thumb' }, KIND_ICON[f.kind] || '📄');
    const card = h('div', {
      class: 'card' + (state.selected.has(f.path) ? ' selected' : ''), role: 'option',
      'aria-selected': state.selected.has(f.path), dataset: { path: f.path }, title: f.location || f.path,
    }, h('span', { class: 'badge' }, f.kind), thumb, h('div', { class: 'name' }, f.name));
    frag.append(card);
    state.cards.set(f.path, card);
    observer.observe(card);
  }
  grid.append(frag);
  const empty = $('#empty');
  if (!state.root && !state.collection) empty.textContent = isDesktop
    ? 'Drop one or more photos into the Archivist window to get started.'
    : 'Enter a folder path above (or use Browse…) to see its photos and videos.';
  else if (state.collection && !state.files.length) empty.textContent = 'Drop photos here to add them to your selection.';
  else if (state.collection && !state.shown.length) empty.textContent = 'No files match the current filters.';
  else if (!state.files.length) empty.textContent = 'No supported photos or videos found in this folder.';
  else if (!state.shown.length) empty.textContent = 'No files match the current filters.';
  else empty.textContent = '';
  $('#count').textContent = state.root || state.collection ? `${state.shown.length} shown · ${state.selected.size} selected` : '';
}

// Defer thumbnail requests until a card is near the viewport.
const observer = new IntersectionObserver(entries => {
  for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    observer.unobserve(entry.target);
    const f = state.files.find(x => x.path === entry.target.dataset.path);
    if (!f) continue;
    const thumb = entry.target.querySelector('.thumb');
    const img = h('img', { alt: '' });
    thumb.replaceChildren(img);
    setImageSource(img, `/api/thumb?path=${enc(f.path)}`);
  }
}, { rootMargin: '400px' });

function syncSelection() {
  for (const [path, card] of state.cards) {
    const on = state.selected.has(path);
    card.classList.toggle('selected', on);
    card.setAttribute('aria-selected', on);
  }
  $('#count').textContent = `${state.shown.length} shown · ${state.selected.size} selected`;
  renderSide();
}

function onGridClick(e) {
  const card = e.target.closest('.card');
  if (!card) return;
  const path = card.dataset.path;
  if (e.shiftKey && state.anchor) {
    const paths = state.shown.map(f => f.path);
    const a = paths.indexOf(state.anchor), b = paths.indexOf(path);
    if (a >= 0 && b >= 0) {
      if (!(e.metaKey || e.ctrlKey)) state.selected.clear();
      for (const p of paths.slice(Math.min(a, b), Math.max(a, b) + 1)) state.selected.add(p);
    }
  } else if (e.metaKey || e.ctrlKey) {
    state.selected.has(path) ? state.selected.delete(path) : state.selected.add(path);
    state.anchor = path;
  } else {
    const only = state.selected.size === 1 && state.selected.has(path);
    state.selected.clear();
    if (!only) state.selected.add(path);
    state.anchor = path;
  }
  syncSelection();
}

// ---------- side panel: preview, details, rename ----------

function renderSide() {
  const side = $('#side');
  const sel = selectedFiles();
  $('.layout').classList.toggle('no-side', (!state.root && !state.collection) || sel.length === 0);
  side.replaceChildren();
  if ((!state.root && !state.collection) || !sel.length) return;
  const close = h('button', { type: 'button', class: 'icon-btn', 'aria-label': 'Close preview', title: 'Close', onclick: () => { state.selected.clear(); syncSelection(); } }, '✕');
  side.append(h('div', { class: 'side-head' }, h('h2', {}, sel.length === 1 ? 'Preview' : `${sel.length} selected`), close));
  if (sel.length === 1) {
    const f = sel[0];
    const media = f.kind === 'video'
      ? h('video', { class: 'preview', controls: true, preload: 'metadata' })
      : h('img', { class: 'preview', alt: '' });
    media.addEventListener('error', () => media.remove());
    if (f.kind === 'video') {
      mediaUrl(f.path).then(src => { if (media.isConnected) media.src = src; }).catch(err => toast(err.message));
    } else {
      setImageSource(media, `/api/preview?path=${enc(f.path)}`);
    }
    side.append(media, filenameEditor(f), h('div', { class: 'muted file-path' }, `${f.location || f.path} · ${formatBytes(f.size)}`));
    const meta = h('div', { class: 'meta' });
    side.append(h('h3', {}, 'Details'), meta);
    loadInfo(f, meta);
  } else {
    const counts = {};
    sel.forEach(f => { counts[f.kind] = (counts[f.kind] || 0) + 1; });
    side.append(h('p', { class: 'muted' }, Object.entries(counts).map(([k, n]) => `${n} ${k}`).join(', ')),
      h('p', { class: 'muted' }, 'Select a single file to see its preview and details, or right-click the selection for actions.'));
  }
  if (state.pendingRename && sel.length === 1 && sel[0].path === state.pendingRename) {
    state.pendingRename = null;
    side.querySelector('.filename-btn')?.click();
  }
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

// ---------- context menu ----------

const menuEl = () => $('#ctx-menu');

function closeMenu(restoreFocus = false) {
  const m = menuEl();
  if (m.hidden) return;
  m.hidden = true;
  m.replaceChildren();
  if (restoreFocus) $('#grid').focus({ preventScroll: true });
}

function openMenu(x, y, items) {
  const m = menuEl();
  m.replaceChildren();
  for (const it of items) {
    if (it.heading) m.append(h('div', { class: 'ctx-heading', role: 'presentation' }, it.heading));
    else if (it.separator) m.append(h('div', { class: 'ctx-sep', role: 'separator' }));
    else {
      m.append(h('button', { type: 'button', role: 'menuitem', class: 'ctx-item' + (it.danger ? ' ctx-danger' : ''), disabled: it.disabled, onclick: () => { closeMenu(); it.run?.(); } },
        h('span', {}, it.label), it.hint && h('span', { class: 'ctx-hint' }, it.hint)));
    }
  }
  m.hidden = false;
  const r = m.getBoundingClientRect();
  m.style.left = Math.max(4, Math.min(x, window.innerWidth - r.width - 4)) + 'px';
  m.style.top = Math.max(4, Math.min(y, window.innerHeight - r.height - 4)) + 'px';
  m.querySelector('.ctx-item:not(:disabled)')?.focus({ preventScroll: true });
}

function menuKeydown(e) {
  const m = menuEl();
  if (m.hidden) return;
  const items = [...m.querySelectorAll('.ctx-item:not(:disabled)')];
  const i = items.indexOf(document.activeElement);
  if (e.key === 'Escape') { e.preventDefault(); closeMenu(true); }
  else if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length]?.focus(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length]?.focus(); }
  else if (e.key === 'Home') { e.preventDefault(); items[0]?.focus(); }
  else if (e.key === 'End') { e.preventDefault(); items.at(-1)?.focus(); }
  else if (e.key === 'Tab') { closeMenu(true); }
}

function opItem(op, sel) {
  const n = sel.filter(f => op.accepts.includes(f.kind)).length;
  const noFfmpeg = op.group === 'videos' && !state.tools.ffmpeg;
  const hint = noFfmpeg ? 'ffmpeg not found' : op.scope === 'folder' ? 'whole folder' : (sel.length > 1 ? `${n} of ${sel.length}` : '');
  return { label: op.label, hint, disabled: noFfmpeg, danger: op.destructive && op.scope === 'folder', run: () => openOp(op) };
}

function folderItems() {
  const items = [{ heading: GROUP_TITLES.folder }];
  state.ops.filter(op => op.scope === 'folder').forEach(op => items.push(opItem(op, [])));
  return items;
}

function fileMenuItems(sel) {
  const items = [];
  if (sel.length === 1) {
    items.push({ label: 'Rename…', run: () => { state.pendingRename = sel[0].path; renderSide(); } }, { separator: true });
  }
  let any = false;
  for (const group of ['photos', 'videos', 'metadata']) {
    const ops = state.ops.filter(op => op.group === group && op.scope === 'files' && sel.some(f => op.accepts.includes(f.kind)));
    if (!ops.length) continue;
    any = true;
    items.push({ heading: GROUP_TITLES[group] }, ...ops.map(op => opItem(op, sel)));
  }
  if (!any) items.push({ label: 'No actions for this selection', disabled: true });
  if (state.root) items.push({ separator: true }, ...folderItems());
  return items;
}

function emptyMenuItems() {
  return [
    { label: 'Select all shown', run: () => { state.shown.forEach(f => state.selected.add(f.path)); syncSelection(); } },
    { label: 'Refresh', run: () => loadFiles() },
    ...(state.root ? [{ separator: true }, ...folderItems()] : []),
  ];
}

function onGridContextMenu(e) {
  if (!state.root && !state.collection) return;
  e.preventDefault();
  const card = e.target.closest('.card');
  const fromKeyboard = e.button === 0 && e.clientX === 0 && e.clientY === 0;
  if (card) {
    const path = card.dataset.path;
    // Like a file manager: right-clicking outside the selection selects just that file.
    if (!state.selected.has(path)) { state.selected = new Set([path]); state.anchor = path; syncSelection(); }
    openMenu(e.clientX, e.clientY, fileMenuItems(selectedFiles()));
  } else if (fromKeyboard && state.selected.size) {
    const first = state.cards.get([...state.selected][0])?.getBoundingClientRect();
    openMenu(first ? first.left + 20 : 40, first ? first.top + 20 : 40, fileMenuItems(selectedFiles()));
  } else {
    openMenu(e.clientX || 40, e.clientY || 40, emptyMenuItems());
  }
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

function openBrowse(startPath, onChoose) {
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
    } catch (err) { toast(err.message); }
  }
  $('#browse-cancel').onclick = () => dlg.close();
  $('#browse-choose').onclick = () => { dlg.close(); onChoose(current); };
  go(startPath);
  dlg.showModal();
}

// ---------- operation dialog ----------

function paramVisible(param, values) {
  if (!param.show_if) return true;
  return Object.entries(param.show_if).every(([k, v]) => typeof v === 'boolean' ? !!values[k] === v : values[k] === v);
}

function openOp(op) {
  const dlg = $('#op-dialog');
  const files = op.scope === 'files' ? selectedFiles().filter(f => op.accepts.includes(f.kind)) : [];
  const ctx = { op, files, plan: null, answers: {}, inputs: {}, captionInputs: {}, cropEditor: null, running: false, logCount: 0 };

  const fields = h('fieldset', { class: 'fields', style: 'border:0;padding:0;margin:0' });
  const planArea = h('div', { class: 'plan' });
  const jobArea = h('div', { class: 'job' });
  const closeBtn = h('button', { type: 'button', onclick: () => dlg.close() }, 'Close');
  const reviewBtn = h('button', { type: 'button', class: 'primary', onclick: () => runPlan() }, 'Review changes');
  const applyBtn = h('button', { type: 'button', class: op.destructive ? 'danger' : 'primary', hidden: true, disabled: true, onclick: () => applyPlan() }, 'Apply');
  const cancelBtn = h('button', { type: 'button', hidden: true, onclick: () => ctx.jobId && api(`/jobs/${ctx.jobId}/cancel`, { method: 'POST' }) }, 'Cancel job');

  const scopeText = op.scope === 'folder'
    ? `Applies to every supported file in ${state.root} (including subfolders), regardless of the current selection.`
    : `${files.length} file(s) selected.`;
  dlg.replaceChildren(
    h('h2', {}, op.label), h('p', { class: 'muted' }, op.description), h('p', {}, scopeText),
    fields, planArea, jobArea, h('div', { class: 'dialog-actions' }, cancelBtn, closeBtn, reviewBtn, applyBtn));

  const refreshVisibility = () => {
    const values = collectParams(false);
    for (const p of op.params) ctx.inputs[p.name].wrap.classList.toggle('hidden', !paramVisible(p, values));
  };
  const invalidate = () => {
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
        : [h('label', { class: 'title', for: id }, p.label + (p.required ? ' *' : '')), control],
      datalist, p.help && h('div', { class: 'help' }, p.help));
    ctx.inputs[p.name] = { el, wrap };
    fields.append(wrap);
  }
  refreshVisibility();

  if (op.editor === 'crop' && files.length) {
    ctx.cropEditor = createCropEditor(files, invalidate);
    fields.prepend(ctx.cropEditor.el);
  }

  const previewImg = h('img', { class: 'preview-img', alt: '', hidden: true });
  async function previewFile(file, caption) {
    try {
      const res = await api(`/ops/${op.id}/preview`, { method: 'POST', body: { path: file.path, params: collectParams(false), caption } });
      const url = URL.createObjectURL(await res.blob());
      if (previewImg.src.startsWith('blob:')) URL.revokeObjectURL(previewImg.src);
      previewImg.src = url;
      previewImg.hidden = false;
    } catch (err) { toast(err.message); }
  }

  if (op.captions && files.length) {
    const box = h('details', { class: 'captions', open: op.captions === 'required' },
      h('summary', {}, op.captions === 'required' ? 'Caption for each photo (photos left blank are skipped)' : 'Optional per-file text (blank uses the text above)'));
    for (const f of files.slice(0, MAX_CAPTION_ROWS)) {
      const input = h('input', { type: 'text', placeholder: 'Caption', 'aria-label': 'Caption for ' + f.name });
      input.addEventListener('input', invalidate);
      ctx.captionInputs[f.path] = input;
      const img = h('img', { alt: '', loading: 'lazy' });
      box.append(h('div', { class: 'caption-row' },
        img,
        input,
        op.previewable && h('button', { type: 'button', onclick: () => previewFile(f, input.value) }, 'Preview'),
        h('div', { class: 'fname' }, f.path)));
      if (f.kind !== 'video') setImageSource(img, `/api/thumb?path=${enc(f.path)}`);
    }
    if (files.length > MAX_CAPTION_ROWS) box.append(h('p', { class: 'muted' }, `Captions can be entered for the first ${MAX_CAPTION_ROWS} files only.`));
    fields.append(box);
  }
  if (op.previewable && files.length) {
    fields.append(h('button', { type: 'button', onclick: () => previewFile(files[0], ctx.captionInputs[files[0].path]?.value || '') }, `Preview on ${files[0].name}`), previewImg);
  }

  async function runPlan() {
    reviewBtn.disabled = true;
    try {
      ctx.plan = await getJson(`/ops/${op.id}/plan`, { method: 'POST', body: { paths: files.map(f => f.path), params: collectParams(), answers: ctx.answers } });
      renderPlan();
    } catch (err) {
      ctx.plan = null;
      planArea.replaceChildren(h('div', { class: 'notice error' }, err.message));
      applyBtn.hidden = true;
    } finally { reviewBtn.disabled = false; }
  }

  function renderPlan() {
    const plan = ctx.plan;
    planArea.replaceChildren();
    plan.errors.forEach(m => planArea.append(h('div', { class: 'notice error' }, m)));
    plan.warnings.forEach(m => planArea.append(h('div', { class: 'notice warn' }, m)));
    if (plan.summary) planArea.append(h('p', {}, h('strong', {}, plan.summary)));
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
    if (plan.items.length) {
      const rows = plan.items.slice(0, MAX_PLAN_ROWS).map(i => h('tr', { class: i.status },
        h('td', {}, i.status === 'ok' ? '→' : i.status === 'skip' ? '·' : '✗'), h('td', {}, i.source), h('td', {}, i.target || ''), h('td', {}, i.note)));
      planArea.append(h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, ''), h('th', {}, 'File'), h('th', {}, 'Result'), h('th', {}, 'Note'))), h('tbody', {}, rows))));
      if (plan.items.length > MAX_PLAN_ROWS) planArea.append(h('p', { class: 'muted' }, `Showing the first ${MAX_PLAN_ROWS} of ${plan.items.length} files.`));
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
    try {
      const res = await getJson(`/ops/${op.id}/apply`, { method: 'POST', body: { plan_id: ctx.plan.plan_id, confirm: ctx.confirmInput ? ctx.confirmInput.value : null } });
      ctx.jobId = res.job_id;
      startJob();
    } catch (err) { toast(err.message); }
  }

  function startJob() {
    ctx.running = true;
    fields.disabled = true;
    planArea.hidden = true;
    reviewBtn.hidden = applyBtn.hidden = closeBtn.hidden = true;
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
    cancelBtn.hidden = true;
    closeBtn.hidden = false;
    const kind = s.status === 'done' && !s.counts.failed ? 'ok' : s.status === 'done' ? 'warn' : 'error';
    const text = s.status === 'cancelled' ? 'Cancelled.' : s.status === 'error' ? `Stopped by an error: ${s.error}` : 'Finished.';
    jobArea.prepend(h('div', { class: 'notice ' + kind }, `${text} ${s.counts.ok} succeeded, ${s.counts.skipped} skipped, ${s.counts.failed} failed.`));
    state.selected.clear();
    await loadFiles();
  }

  dlg.oncancel = e => { if (ctx.running) e.preventDefault(); };
  dlg.showModal();
}

// ---------- startup ----------

$('#root-form').addEventListener('submit', e => { e.preventDefault(); const v = $('#root-input').value.trim(); if (v) openRoot(v); });
$('#browse-btn').addEventListener('click', () => openBrowse($('#root-input').value || state.home, path => openRoot(path)));
$('#subdirs').addEventListener('change', () => { if (state.root) loadFiles(); });
document.querySelectorAll('.kind-filter').forEach(i => i.addEventListener('change', applyFilters));
let searchTimer;
$('#search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(applyFilters, 150); });
$('#grid').addEventListener('click', e => { closeMenu(); onGridClick(e); });
$('#grid').addEventListener('contextmenu', onGridContextMenu);
$('#empty').addEventListener('contextmenu', onGridContextMenu);
$('#grid').addEventListener('keydown', e => {
  if (e.key === 'Escape' && state.selected.size) { state.selected.clear(); syncSelection(); }
});
document.addEventListener('keydown', menuKeydown);
document.addEventListener('pointerdown', e => { if (!e.target.closest('#ctx-menu')) closeMenu(); }, true);
window.addEventListener('blur', () => closeMenu());
window.addEventListener('resize', () => closeMenu());
$('#grid').addEventListener('scroll', () => closeMenu(), { passive: true });
$('#select-all').addEventListener('click', () => { state.shown.forEach(f => state.selected.add(f.path)); syncSelection(); });
$('#clear-selection').addEventListener('click', () => { state.selected.clear(); syncSelection(); });

loadState().catch(err => toast(err.message));
