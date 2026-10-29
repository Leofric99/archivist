'use strict';

/*
 * Interactive crop editor. Crops are stored as fractions [x, y, w, h] of each photo (as displayed, i.e. after
 * EXIF rotation), so they are independent of the preview resolution.
 */
function createCropEditor(files, onChange) {
  const MIN = 24;       // smallest box edge, in displayed pixels
  const NUDGE = 4;
  const PRESETS = [['1:1', 1, 1], ['5:4', 5, 4], ['4:3', 4, 3], ['3:2', 3, 2], ['7:5', 7, 5], ['16:9', 16, 9], ['2:1', 2, 1]];
  const crops = {};
  let idx = 0, mode = 'free', swapped = false, drag = null;

  const el = (tag, attrs = {}, ...kids) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'class') node.className = v;
      else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
      else if (k === 'dataset') Object.assign(node.dataset, v);
      else if (v === true) node.setAttribute(k, '');
      else node.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    return node;
  };
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), Math.max(lo, hi));
  const cur = () => files[idx];
  const url = (kind, path) => window.archivistAssetUrl
    ? window.archivistAssetUrl(`/api/${kind}?path=${encodeURIComponent(path)}`)
    : `/api/${kind}?path=${encodeURIComponent(path)}`;

  // ----- ratio controls -----
  const ratioSelect = el('select', { 'aria-label': 'Aspect ratio' },
    el('option', { value: 'free' }, 'Freeform'), el('option', { value: 'original' }, 'Original ratio'),
    PRESETS.map(([label]) => el('option', { value: label }, label)), el('option', { value: 'custom' }, 'Custom…'));
  const customW = el('input', { type: 'number', min: '0.1', step: 'any', value: '3', 'aria-label': 'Ratio width' });
  const customH = el('input', { type: 'number', min: '0.1', step: 'any', value: '2', 'aria-label': 'Ratio height' });
  const custom = el('span', { class: 'crop-custom', hidden: true }, customW, ' : ', customH);
  const swapBtn = el('button', { type: 'button', title: 'Swap landscape / portrait', onclick: () => { swapped = !swapped; applyRatio(); } }, '⇄ Rotate ratio');

  function currentRatio() {
    let r = null;
    if (mode === 'original') r = img.naturalWidth && img.naturalHeight ? img.naturalWidth / img.naturalHeight : null;
    else if (mode === 'custom') {
      const w = parseFloat(customW.value), h = parseFloat(customH.value);
      r = w > 0 && h > 0 ? w / h : null;
    } else if (mode !== 'free') {
      const [, w, h] = PRESETS.find(p => p[0] === mode);
      r = w / h;
    }
    if (r && swapped && mode !== 'original') r = 1 / r;
    return r;
  }

  ratioSelect.addEventListener('change', () => {
    mode = ratioSelect.value;
    swapped = false;
    custom.hidden = mode !== 'custom';
    swapBtn.disabled = mode === 'free' || mode === 'original';
    applyRatio();
  });
  [customW, customH].forEach(i => i.addEventListener('input', applyRatio));

  // Reshape the current box (or create one) to the chosen ratio, keeping its centre.
  function applyRatio() {
    const ratio = currentRatio();
    const W = img.clientWidth, H = img.clientHeight;
    if (!ratio || !W) { render(); return; }
    const c = crops[cur().path];
    const r = c ? { x: c[0] * W, y: c[1] * H, w: c[2] * W, h: c[3] * H } : { x: 0, y: 0, w: W, h: H };
    const cx = r.x + r.w / 2, cy = r.y + r.h / 2;
    if (r.w / r.h > ratio) r.w = r.h * ratio; else r.h = r.w / ratio;
    r.x = clamp(cx - r.w / 2, 0, W - r.w);
    r.y = clamp(cy - r.h / 2, 0, H - r.h);
    store(r);
  }

  // ----- stage -----
  const img = el('img', { class: 'crop-img', alt: '', draggable: 'false' });
  const handles = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'].map(k => el('span', { class: 'crop-handle h-' + k, dataset: { h: k } }));
  const box = el('div', { class: 'crop-box', tabindex: '0', hidden: true, 'aria-label': 'Crop area. Arrow keys move it, Shift+arrows resize it.' }, handles);
  // The dimming outside the box lives in its own clipped layer so it cannot spill over the dialog.
  const hole = el('div', { class: 'crop-hole' });
  const shade = el('div', { class: 'crop-shade' }, hole);
  const frame = el('div', { class: 'crop-frame' }, img, shade, box);
  const info = el('div', { class: 'crop-info muted' });
  const counter = el('span', { class: 'muted' });
  const strip = el('div', { class: 'crop-strip' });

  function store(r) {
    const W = img.clientWidth, H = img.clientHeight;
    crops[cur().path] = [r.x / W, r.y / H, r.w / W, r.h / H];
    render();
    onChange();
  }

  function render() {
    const W = img.clientWidth, H = img.clientHeight, c = crops[cur().path];
    if (!c || !W) {
      box.hidden = true;
      shade.hidden = true;
      info.textContent = 'Drag on the photo to draw a crop. Photos left uncropped are skipped (unless a centre-crop ratio is set below).';
    } else {
      box.hidden = false;
      shade.hidden = false;
      const geometry = { left: c[0] * W + 'px', top: c[1] * H + 'px', width: c[2] * W + 'px', height: c[3] * H + 'px' };
      Object.assign(box.style, geometry);
      Object.assign(hole.style, geometry);
      const ratio = (c[2] * W) / (c[3] * H);
      info.textContent = `Keeping ${Math.round(c[2] * 100)}% × ${Math.round(c[3] * 100)}% of the photo · ratio ${ratio.toFixed(2)}:1`;
    }
    counter.textContent = `${idx + 1} of ${files.length}`;
    strip.querySelectorAll('button').forEach((b, i) => {
      b.classList.toggle('active', i === idx);
      b.classList.toggle('cropped', !!crops[files[i].path]);
    });
  }

  // ----- pointer handling -----
  const point = e => {
    const r = img.getBoundingClientRect();
    return { x: clamp(e.clientX - r.left, 0, r.width), y: clamp(e.clientY - r.top, 0, r.height) };
  };
  const current = () => {
    const c = crops[cur().path], W = img.clientWidth, H = img.clientHeight;
    return c ? { x: c[0] * W, y: c[1] * H, w: c[2] * W, h: c[3] * H } : null;
  };

  // Rectangle spanned by a fixed corner and the pointer, honouring bounds and the ratio lock.
  function fromAnchor(ax, ay, px, py) {
    const W = img.clientWidth, H = img.clientHeight, ratio = currentRatio();
    const sx = px >= ax ? 1 : -1, sy = py >= ay ? 1 : -1;
    let w = Math.min(Math.abs(px - ax), sx > 0 ? W - ax : ax);
    let h = Math.min(Math.abs(py - ay), sy > 0 ? H - ay : ay);
    if (ratio) {
      if (w / Math.max(h, 1e-6) > ratio) w = h * ratio; else h = w / ratio;
    }
    return { x: sx > 0 ? ax : ax - w, y: sy > 0 ? ay : ay - h, w, h };
  }

  function edgeResize(hd, r0, px, py) {
    const W = img.clientWidth, H = img.clientHeight, ratio = currentRatio();
    const { x, y, w, h } = r0;
    const cx = x + w / 2, cy = y + h / 2;
    if (hd === 'n' || hd === 's') {
      let nh = hd === 'n' ? (y + h) - clamp(py, 0, y + h - MIN) : clamp(py, y + MIN, H) - y;
      if (!ratio) return { x, y: hd === 'n' ? y + h - nh : y, w, h: nh };
      let nw = nh * ratio;
      if (nw > W) { nw = W; nh = nw / ratio; }
      return { x: clamp(cx - nw / 2, 0, W - nw), y: hd === 'n' ? y + h - nh : y, w: nw, h: nh };
    }
    let nw = hd === 'w' ? (x + w) - clamp(px, 0, x + w - MIN) : clamp(px, x + MIN, W) - x;
    if (!ratio) return { x: hd === 'w' ? x + w - nw : x, y, w: nw, h };
    let nh = nw / ratio;
    if (nh > H) { nh = H; nw = nh * ratio; }
    return { x: hd === 'w' ? x + w - nw : x, y: clamp(cy - nh / 2, 0, H - nh), w: nw, h: nh };
  }

  frame.addEventListener('pointerdown', e => {
    if (e.button !== 0 || !img.clientWidth) return;
    const p = point(e), hd = e.target.dataset?.h, r0 = current();
    if (hd && r0) {
      drag = { type: hd.length === 2 ? 'corner' : 'edge', hd, r0, ax: hd.includes('w') ? r0.x + r0.w : r0.x, ay: hd.includes('n') ? r0.y + r0.h : r0.y };
    } else if (e.target === box && r0) {
      drag = { type: 'move', r0, start: p };
    } else {
      drag = { type: 'draw', ax: p.x, ay: p.y };
    }
    frame.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  frame.addEventListener('pointermove', e => {
    if (!drag) return;
    const p = point(e), W = img.clientWidth, H = img.clientHeight;
    let r;
    if (drag.type === 'move') {
      r = { ...drag.r0, x: clamp(drag.r0.x + p.x - drag.start.x, 0, W - drag.r0.w), y: clamp(drag.r0.y + p.y - drag.start.y, 0, H - drag.r0.h) };
    } else if (drag.type === 'edge') r = edgeResize(drag.hd, drag.r0, p.x, p.y);
    else r = fromAnchor(drag.ax, drag.ay, p.x, p.y);
    if (r.w > 0.5 && r.h > 0.5) store(r);
  });

  const endDrag = () => {
    if (!drag) return;
    const r = current();
    // A click (or a tiny drag) on the photo clears the box instead of leaving a sliver.
    if (drag.type === 'draw' && (!r || r.w < MIN || r.h < MIN)) { delete crops[cur().path]; render(); onChange(); }
    drag = null;
  };
  frame.addEventListener('pointerup', endDrag);
  frame.addEventListener('pointercancel', endDrag);

  box.addEventListener('keydown', e => {
    const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    const r = current();
    if (!d || !r) return;
    e.preventDefault();
    const W = img.clientWidth, H = img.clientHeight, ratio = currentRatio();
    if (e.shiftKey) {
      const grow = (d[0] + d[1]) * NUDGE * 2;
      let w = clamp(r.w + (ratio ? grow * ratio : d[0] * NUDGE * 2), MIN, W - r.x);
      let h = ratio ? w / ratio : clamp(r.h + d[1] * NUDGE * 2, MIN, H - r.y);
      if (h > H - r.y) { h = H - r.y; if (ratio) w = h * ratio; }
      store({ ...r, w, h });
    } else {
      store({ ...r, x: clamp(r.x + d[0] * NUDGE, 0, W - r.w), y: clamp(r.y + d[1] * NUDGE, 0, H - r.h) });
    }
  });

  // ----- navigation and actions -----
  function show(i) {
    idx = clamp(i, 0, files.length - 1);
    box.hidden = true;
    shade.hidden = true;
    const selected = cur();
    Promise.resolve(url('preview', selected.path)).then(src => {
      if (cur() === selected) img.src = src;
    });
    render();
    strip.children[idx]?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }
  img.addEventListener('load', render);
  new ResizeObserver(() => render()).observe(img);

  const prevBtn = el('button', { type: 'button', onclick: () => show(idx - 1) }, '‹ Previous');
  const nextBtn = el('button', { type: 'button', onclick: () => show(idx + 1) }, 'Next ›');
  const clearBtn = el('button', { type: 'button', onclick: () => { delete crops[cur().path]; render(); onChange(); } }, 'Clear crop');
  const copyBtn = el('button', {
    type: 'button', title: 'Use the same proportional crop box on every selected photo',
    onclick: () => {
      const c = crops[cur().path];
      if (!c) return;
      files.forEach(f => { crops[f.path] = [...c]; });
      render(); onChange();
    },
  }, 'Use this crop for all');

  files.forEach((f, i) => {
    const image = el('img', { alt: '', loading: 'lazy', draggable: 'false' });
    strip.append(el('button', { type: 'button', class: 'crop-thumb', title: f.path, onclick: () => show(i) }, image));
    Promise.resolve(url('thumb', f.path)).then(src => { if (image.isConnected) image.src = src; });
  });
  if (files.length < 2) { prevBtn.hidden = nextBtn.hidden = copyBtn.hidden = strip.hidden = true; }

  const root = el('div', { class: 'crop-editor' },
    el('div', { class: 'crop-toolbar' }, ratioSelect, custom, swapBtn, el('span', { class: 'spacer' }), clearBtn, copyBtn),
    el('div', { class: 'crop-stage' }, frame),
    el('div', { class: 'crop-nav' }, prevBtn, counter, nextBtn, el('span', { class: 'spacer' }), info),
    strip);
  swapBtn.disabled = true;
  show(0);

  return { el: root, getCrops: () => ({ ...crops }) };
}
