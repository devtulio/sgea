/*
 * base.js — esqueleto compartilhado da família SGCD/SGCA/SGDP/SGEA
 *
 * Fonte canônica: C:\Users\devtu\Documents\Claude Code\_esqueleto\base.js
 * Cópias vendorizadas em cada sistema são geradas por sync.py — não editar
 * a cópia dentro de SGCD/, SGCA/, SGDP/, SGEA/ diretamente, editar aqui e
 * rodar `python sync.py`.
 *
 * Como usar, no <head>/fim do <body> de cada SISTEMA.html, nesta ordem:
 *   <script>const SGX_APP_ID = 'sgcd';</script>   <!-- namespace de localStorage -->
 *   <script src="base.js"></script>
 *   <script> ... script próprio do sistema, usa as funções abaixo ... </script>
 *
 * Este arquivo só define funções/utilitários reutilizáveis — não tem
 * nenhum código que roda sozinho no carregamento (boot, login inicial etc.
 * continuam no script de cada sistema, que decide quando chamar o que
 * está aqui). A única exceção são os listeners de teclado genéricos no
 * fim do arquivo (Escape fecha modal aberto, focus-trap de Tab dentro de
 * modal, Enter/Espaço em elementos role="button") — esses são universais
 * e seguros de anexar sempre.
 *
 * Funções aqui esperam que o sistema já tenha definido, antes de chamá-las:
 *   - SGX_APP_ID (string) — usado para prefixar chaves de localStorage
 *   - _apiToken / _apiUser (let, escopo de módulo/script do próprio sistema)
 *   - _showLoginOverlay() — função própria do sistema (mostra a tela de login);
 *     chamada por _apiLogout() quando a sessão expira
 */

// ── API wrapper (fetch + Bearer token + 401 → logout) ──────────────────────
const API = {
  async req(method, path, body, isForm = false) {
    const headers = {};
    if (_apiToken) headers['Authorization'] = `Bearer ${_apiToken}`;
    if (body && !isForm) headers['Content-Type'] = 'application/json';
    const opts = { method, headers };
    if (body) opts.body = isForm ? body : JSON.stringify(body);
    try {
      const r = await fetch(path, opts);
      // 401 no próprio login é "senha incorreta", não sessão expirada — deixa
      // o chamador (verificarSenha) tratar a resposta em vez de disparar logout.
      if (r.status === 401 && path !== '/api/auth/login') { _apiLogout(); return null; }
      return r;
    } catch (e) {
      console.error('[API]', method, path, e.message);
      if (typeof toast === 'function') toast('Falha de comunicação com o servidor.', 'error');
      return null;
    }
  },
  get:    (p)       => API.req('GET',    p),
  post:   (p, b)    => API.req('POST',   p, b),
  put:    (p, b)    => API.req('PUT',    p, b),
  del:    (p)       => API.req('DELETE', p),
  upload: (p, form) => API.req('POST',   p, form, true),
  async json(r) { try { return r ? await r.json() : null; } catch { return null; } },
};

function _apiLogout() {
  if (_apiToken) fetch('/api/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${_apiToken}` } }).catch(() => {});
  _apiToken = null; _apiUser = null;
  localStorage.removeItem(`${SGX_APP_ID}-token`);
  if (typeof _showLoginOverlay === 'function') _showLoginOverlay();
}

// ── Toast ────────────────────────────────────────────────────────────────
function toast(msg, type = '') {
  const el = document.createElement('div');
  el.className = 'toast-msg ' + type;
  el.textContent = msg;
  document.getElementById('toast')?.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ── Confirmação customizada (reaproveita o modal #confirm-overlay) ─────────
function customConfirm(msg, { title = 'Confirmar', icon = '⚠️', okLabel = 'Confirmar', okClass = 'btn-danger', cancelLabel = 'Cancelar' } = {}) {
  return new Promise(res => {
    document.getElementById('confirm-msg').textContent   = msg;
    document.getElementById('confirm-title').textContent = title;
    if (document.getElementById('confirm-icon')) document.getElementById('confirm-icon').textContent = icon;
    const okBtn     = document.getElementById('confirm-ok');
    const cancelBtn = document.getElementById('confirm-cancel');
    okBtn.textContent     = okLabel;
    okBtn.className       = 'btn ' + okClass;
    cancelBtn.textContent = cancelLabel;
    document.getElementById('confirm-overlay').classList.remove('hidden');

    const finish = val => {
      document.getElementById('confirm-overlay').classList.add('hidden');
      okBtn.removeEventListener('click', onOk);
      cancelBtn.removeEventListener('click', onCancel);
      res(val);
    };
    const onOk     = () => finish(true);
    const onCancel = () => finish(false);
    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
  });
}
document.addEventListener('DOMContentLoaded', () => {
  const overlay = document.getElementById('confirm-overlay');
  // Clica no botão Cancelar em vez de só esconder o overlay — customConfirm()
  // só resolve a Promise (e limpa os listeners de OK/Cancelar) quando um dos
  // dois botões é clicado; esconder por fora disso trava o await pra sempre.
  overlay?.addEventListener('click', e => { if (e.target === overlay) document.getElementById('confirm-cancel')?.click(); });
});

// ── Utilitários genéricos ───────────────────────────────────────────────
function _debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function _hideAllViews() { document.querySelectorAll('.view').forEach(v => v.classList.remove('active')); }
function setNavActive(id) {
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.getElementById(id)?.classList.add('active');
}

// ── Exportação de arquivos ─────────────────────────────────────────────────
// Salva um arquivo pedindo ao usuário onde salvar (File System Access API,
// suportada no Chrome/Edge — navegadores recomendados). Em contexto sem suporte
// (ex.: acesso pela rede por IP, sem localhost) cai no download tradicional pra
// pasta padrão. Retorna false se o usuário cancelou o diálogo (o chamador não
// deve seguir como se tivesse salvo). Aceita string ou Blob em `conteudo`.
async function _salvarArquivoComo(conteudo, nomeArquivo, mimeType) {
  if (window.showSaveFilePicker) {
    try {
      const ext = '.' + nomeArquivo.split('.').pop();
      const handle = await window.showSaveFilePicker({
        suggestedName: nomeArquivo,
        types: [{ description: 'Arquivo', accept: { [mimeType]: [ext] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(conteudo);
      await writable.close();
      return true;
    } catch (e) {
      if (e.name === 'AbortError') return false;  // usuário cancelou o diálogo
      // outros erros (ex.: navegador bloqueou por política): cai no fallback abaixo
    }
  }
  const blob = conteudo instanceof Blob ? conteudo : new Blob([conteudo], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = nomeArquivo;
  link.click();
  URL.revokeObjectURL(url);
  return true;
}

// Monta uma string CSV (com BOM UTF-8) a partir de um cabeçalho e linhas —
// cada linha é um array de valores; células são escapadas (aspas duplicadas).
function toCSV(header, linhas) {
  const cel = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
  return '﻿' + [header.map(cel).join(','), ...linhas.map(l => l.map(cel).join(','))].join('\r\n');
}

// ── Exportar Excel (.xlsx) ─────────────────────────────────────────────────
// Writer OOXML mínimo, sem dependências: ZIP em modo "store" (sem compressão)
// + XML mínimo (1 planilha, células inline-string ou numéricas) — evita puxar
// uma lib de compressão só para gerar uma tabela simples. Chame _exportarXlsx.
function _crc32(bytes) {
  let crc = 0xFFFFFFFF;
  for (let i = 0; i < bytes.length; i++) {
    crc ^= bytes[i];
    for (let j = 0; j < 8; j++) crc = (crc >>> 1) ^ (0xEDB88320 & -(crc & 1));
  }
  return (crc ^ 0xFFFFFFFF) >>> 0;
}
function _zipStore(files) {
  const now = new Date();
  const dosTime = ((now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1)) & 0xFFFF;
  const dosDate = (((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate()) & 0xFFFF;
  const enc = new TextEncoder();
  const parts = [];
  const central = [];
  let offset = 0;
  for (const f of files) {
    const nameBytes = enc.encode(f.name);
    const crc = _crc32(f.data);
    const size = f.data.length;

    const local = new Uint8Array(30 + nameBytes.length);
    const lv = new DataView(local.buffer);
    lv.setUint32(0, 0x04034b50, true);
    lv.setUint16(4, 20, true);
    lv.setUint16(6, 0, true);
    lv.setUint16(8, 0, true);
    lv.setUint16(10, dosTime, true);
    lv.setUint16(12, dosDate, true);
    lv.setUint32(14, crc, true);
    lv.setUint32(18, size, true);
    lv.setUint32(22, size, true);
    lv.setUint16(26, nameBytes.length, true);
    lv.setUint16(28, 0, true);
    local.set(nameBytes, 30);
    parts.push(local, f.data);

    const centralEntry = new Uint8Array(46 + nameBytes.length);
    const cv = new DataView(centralEntry.buffer);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(4, 20, true);
    cv.setUint16(6, 20, true);
    cv.setUint16(8, 0, true);
    cv.setUint16(10, 0, true);
    cv.setUint16(12, dosTime, true);
    cv.setUint16(14, dosDate, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, size, true);
    cv.setUint32(24, size, true);
    cv.setUint16(28, nameBytes.length, true);
    cv.setUint32(42, offset, true);
    centralEntry.set(nameBytes, 46);
    central.push(centralEntry);

    offset += local.length + f.data.length;
  }
  const centralSize   = central.reduce((s, c) => s + c.length, 0);
  const centralOffset = offset;
  const end = new Uint8Array(22);
  const ev = new DataView(end.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(8, files.length, true);
  ev.setUint16(10, files.length, true);
  ev.setUint32(12, centralSize, true);
  ev.setUint32(16, centralOffset, true);
  return new Blob([...parts, ...central, end], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
}
function _colLetter(n) {
  let s = '', i = n + 1;
  while (i > 0) { const r = (i - 1) % 26; s = String.fromCharCode(65 + r) + s; i = Math.floor((i - 1) / 26); }
  return s;
}
function _xlsxCellXml(col, row, value) {
  const ref = `${col}${row}`;
  if (value == null || value === '') return `<c r="${ref}"/>`;
  if (typeof value === 'number' && isFinite(value)) return `<c r="${ref}"><v>${value}</v></c>`;
  const esc = String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  return `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${esc}</t></is></c>`;
}
// Retorna false se o usuário cancelou o diálogo "Salvar como" (ver _salvarArquivoComo).
async function _exportarXlsx(nomeArquivo, cabecalho, linhas) {
  const rowsXml = [cabecalho, ...linhas].map((row, ri) =>
    `<row r="${ri + 1}">${row.map((v, ci) => _xlsxCellXml(_colLetter(ci), ri + 1, v)).join('')}</row>`
  ).join('');
  const sheetXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${rowsXml}</sheetData></worksheet>`;
  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>`;
  const rootRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`;
  const workbookXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Dados" sheetId="1" r:id="rId1"/></sheets></workbook>`;
  const workbookRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>`;
  const enc = new TextEncoder();
  const blob = _zipStore([
    { name: '[Content_Types].xml',        data: enc.encode(contentTypes) },
    { name: '_rels/.rels',                data: enc.encode(rootRels) },
    { name: 'xl/workbook.xml',            data: enc.encode(workbookXml) },
    { name: 'xl/_rels/workbook.xml.rels', data: enc.encode(workbookRels) },
    { name: 'xl/worksheets/sheet1.xml',   data: enc.encode(sheetXml) },
  ]);
  return _salvarArquivoComo(blob, nomeArquivo, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
}

// ── Editor de texto rico (contenteditable) para corpo de e-mail ────────────
// Comandos genéricos parametrizados pelo id do editor. Monte a toolbar com
// _rteMount (preenche <div class="rte-toolbar" data-editor="ID"></div>) e envie
// o HTML sempre passando por _sanitizeEmailHtml (barreira contra XSS).
function _rteEsc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function _rteExec(editorId, cmd, val) {
  document.getElementById(editorId)?.focus();
  document.execCommand(cmd, false, val);
}
function _rtePtToSize(pt) {
  // execCommand fontSize aceita 1-7; mapeamos pt -> tamanho aproximado
  const map = { '9': 1, '10': 2, '11': 2, '12': 3, '14': 4, '16': 5, '18': 6, '24': 7 };
  return map[String(pt)] || 3;
}
function _rteInsertLink(editorId) {
  const url = prompt('URL do link:');
  if (!url) return;
  const text = prompt('Texto do link (deixe em branco para usar a URL):') || url;
  const safe = /^https?:\/\//i.test(url) ? url.replace(/"/g, '&quot;') : '#';
  document.getElementById(editorId)?.focus();
  document.execCommand('insertHTML', false, `<a href="${safe}" target="_blank">${_rteEsc(text)}</a>`);
}
function _rteGetHtml(editorId) { const d = document.getElementById(editorId); return d ? d.innerHTML : ''; }
function _rteGetText(editorId) { const d = document.getElementById(editorId); return d ? d.innerText : ''; }
function _rteSetContent(editorId, text) {
  const d = document.getElementById(editorId);
  if (!d) return;
  // Cada linha vira um <div>; vazias viram <div><br></div> (padrão do contenteditable)
  d.innerHTML = String(text ?? '').split('\n').map(l => l === '' ? '<div><br></div>' : `<div>${_rteEsc(l)}</div>`).join('');
}
// HTML da toolbar para um editor (todos os botões apontam para os comandos genéricos acima).
function _rteToolbarHtml(editorId) {
  const b = (cmd, title, label) => `<button type="button" class="_etb" onclick="_rteExec('${editorId}','${cmd}')" title="${title}">${label}</button>`;
  const opt = (v, sel) => `<option value="${v}"${sel ? ' selected' : ''}>${v}</option>`;
  return `<div class="_etb-toolbar">
    ${b('bold', 'Negrito (Ctrl+B)', '<b>B</b>')}${b('italic', 'Itálico (Ctrl+I)', '<i>I</i>')}${b('underline', 'Sublinhado (Ctrl+U)', '<u>U</u>')}
    <span class="_etb-sep"></span>
    ${b('justifyLeft', 'Alinhar à esquerda', '&#8676;')}${b('justifyCenter', 'Centralizar', '&#8801;')}${b('justifyRight', 'Alinhar à direita', '&#8677;')}${b('justifyFull', 'Justificar', '&#8723;')}
    <span class="_etb-sep"></span>
    <select class="_etb-sel" style="width:120px" onchange="_rteExec('${editorId}','fontName',this.value);this.blur()" title="Fonte">
      ${opt('Arial')}${opt('Calibri')}${opt('Georgia')}${opt('Times New Roman')}${opt('Verdana', true)}
    </select>
    <select class="_etb-sel" style="width:62px" onchange="_rteExec('${editorId}','fontSize',_rtePtToSize(this.value));this.blur()" title="Tamanho">
      <option value="9">9pt</option><option value="10">10pt</option><option value="11">11pt</option><option value="12" selected>12pt</option><option value="14">14pt</option><option value="16">16pt</option><option value="18">18pt</option>
    </select>
    <span class="_etb-sep"></span>
    ${b('insertUnorderedList', 'Lista com marcadores', '&#8226;&#8226;')}${b('insertOrderedList', 'Lista numerada', '1.')}${b('indent', 'Aumentar recuo', '&#8677;&#8677;')}${b('outdent', 'Diminuir recuo', '&#8676;&#8676;')}
    <span class="_etb-sep"></span>
    <button type="button" class="_etb" onclick="_rteInsertLink('${editorId}')" title="Inserir link">&#128279;</button>
    ${b('removeFormat', 'Remover formatação', '&#10007;')}
    <span class="_etb-sep"></span>
    ${b('undo', 'Desfazer (Ctrl+Z)', '&#8634;')}${b('redo', 'Refazer (Ctrl+Y)', '&#8635;')}
  </div>`;
}
// Preenche cada placeholder <div class="rte-toolbar" data-editor="ID"></div> em root (default: document).
function _rteMount(root) {
  (root || document).querySelectorAll('.rte-toolbar[data-editor]').forEach(ph => { ph.innerHTML = _rteToolbarHtml(ph.dataset.editor); });
}
// Remove tags/atributos perigosos do HTML gerado pelo contenteditable (barreira XSS ao enviar).
function _sanitizeEmailHtml(html) {
  if (!html) return '';
  const ALLOWED_TAGS = new Set([
    'p', 'br', 'div', 'span', 'b', 'strong', 'i', 'em', 'u', 's', 'strike',
    'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'blockquote', 'pre', 'code',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a', 'img',
    'font', 'hr', 'sub', 'sup',
  ]);
  const ALLOWED_ATTRS = new Set([
    'style', 'href', 'src', 'alt', 'width', 'height', 'align', 'valign',
    'border', 'cellpadding', 'cellspacing', 'colspan', 'rowspan', 'target',
    'color', 'size', 'face',
  ]);
  const DANGEROUS_PROTOCOLS = /^(javascript|vbscript|data(?!:image\/(png|jpeg|gif|webp|svg)))/i;
  const doc = new DOMParser().parseFromString(html, 'text/html');
  function clean(node) {
    if (node.nodeType === Node.TEXT_NODE) return;
    if (node.nodeType === Node.COMMENT_NODE) { node.remove(); return; }
    if (node.nodeType !== Node.ELEMENT_NODE) { node.remove(); return; }
    const tag = node.tagName.toLowerCase();
    if (!ALLOWED_TAGS.has(tag)) { node.replaceWith(document.createTextNode(node.textContent)); return; }
    for (const attr of [...node.attributes]) {
      if (!ALLOWED_ATTRS.has(attr.name.toLowerCase())) node.removeAttribute(attr.name);
      else if ((attr.name === 'href' || attr.name === 'src') && DANGEROUS_PROTOCOLS.test(attr.value.trim())) node.removeAttribute(attr.name);
    }
    for (const attr of [...node.attributes]) { if (/^on/i.test(attr.name)) node.removeAttribute(attr.name); }
    for (const child of [...node.childNodes]) clean(child);
  }
  for (const child of [...doc.body.childNodes]) clean(child);
  return doc.body.innerHTML;
}

// ── Tela de login: mostrar/ocultar senha + aviso de Caps Lock ──────────────
function _pinToggleOlho() {
  const inp = document.getElementById('pin-input');
  const ico = document.getElementById('pin-eye-icon');
  if (inp.type === 'password') {
    inp.type = 'text';
    ico.innerHTML = '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>';
  } else {
    inp.type = 'password';
    ico.innerHTML = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>';
  }
}
function _pinCheckCaps(e) {
  const warn = document.getElementById('pin-caps-warn');
  if (!warn) return;
  const caps = typeof e.getModifierState === 'function' && e.getModifierState('CapsLock');
  warn.style.display = caps ? 'flex' : 'none';
}

// ── Fundo animado da tela de login (rede de partículas) ────────────────────
let _lcRaf = null, _lcNodes = [], _lcMouse = { x: -9999, y: -9999 };
const _LC_DEFAULTS = { count: 60, dist: 110, speed: 4 };
const _LC = Object.assign({}, _LC_DEFAULTS);

function _lcConfigKey() { return `${SGX_APP_ID}_lc_config`; }

function _lcLoadConfig() {
  try {
    const s = JSON.parse(localStorage.getItem(_lcConfigKey()) || '{}');
    if (s.count) _LC.count = s.count;
    if (s.dist)  _LC.dist  = s.dist;
    if (s.speed) _LC.speed = s.speed;
  } catch {}
  const sl = id => document.getElementById(id);
  if (sl('lc-sl-nodes')) { sl('lc-sl-nodes').value = _LC.count; sl('lc-out-nodes').textContent = _LC.count; }
  if (sl('lc-sl-dist'))  { sl('lc-sl-dist').value  = _LC.dist;  sl('lc-out-dist').textContent  = _LC.dist;  }
  if (sl('lc-sl-speed')) { sl('lc-sl-speed').value = _LC.speed; sl('lc-out-speed').textContent = _LC.speed; }
}
function _lcSaveConfig() { localStorage.setItem(_lcConfigKey(), JSON.stringify({ count: _LC.count, dist: _LC.dist, speed: _LC.speed })); }
function _lcToggleConfig() {
  const p = document.getElementById('lc-config-panel');
  if (p) p.style.display = p.style.display === 'none' ? 'block' : 'none';
}
function _lcSpeedVal() { return _LC.speed * 0.08; }
function _lcParam(key, val, outId) {
  document.getElementById(outId).textContent = val;
  if (key === 'count') {
    _LC.count = val;
    while (_lcNodes.length < val) {
      const c = document.getElementById('pin-canvas');
      _lcNodes.push({ x: Math.random()*(c?.width||800), y: Math.random()*(c?.height||600),
        vx: (Math.random()-.5)*_lcSpeedVal(), vy: (Math.random()-.5)*_lcSpeedVal(), r: Math.random()*1.6+1 });
    }
    while (_lcNodes.length > val) _lcNodes.pop();
  } else if (key === 'dist') {
    _LC.dist = val;
  } else if (key === 'speed') {
    _LC.speed = val;
    const s = _lcSpeedVal();
    for (const n of _lcNodes) {
      const a = Math.atan2(n.vy, n.vx);
      const m = Math.random() * s + s * .3;
      n.vx = Math.cos(a) * m; n.vy = Math.sin(a) * m;
    }
  }
  _lcSaveConfig();
}
function _lcResetConfig() {
  Object.assign(_LC, _LC_DEFAULTS);
  _lcSaveConfig();
  _lcLoadConfig();
  _lcNodes = [];
}

function _loginCanvasStart() {
  const canvas = document.getElementById('pin-canvas');
  if (!canvas) return;
  const overlay = document.getElementById('overlay-pin');
  const ctx = canvas.getContext('2d');

  _lcLoadConfig();

  function resize() { canvas.width = overlay.offsetWidth; canvas.height = overlay.offsetHeight; }
  resize();

  if (_lcNodes.length === 0) {
    for (let i = 0; i < _LC.count; i++) {
      const s = _lcSpeedVal();
      _lcNodes.push({ x: Math.random() * canvas.width, y: Math.random() * canvas.height,
        vx: (Math.random() - .5) * s * 2, vy: (Math.random() - .5) * s * 2, r: Math.random() * 1.6 + 1 });
    }
  }

  function onMove(e) {
    const r = overlay.getBoundingClientRect();
    const src = e.touches ? e.touches[0] : e;
    _lcMouse.x = src.clientX - r.left;
    _lcMouse.y = src.clientY - r.top;
  }
  function onLeave() { _lcMouse.x = -9999; _lcMouse.y = -9999; }
  overlay.addEventListener('mousemove', onMove);
  overlay.addEventListener('touchmove', onMove, { passive: true });
  overlay.addEventListener('mouseleave', onLeave);
  canvas._lcCleanup = () => {
    overlay.removeEventListener('mousemove', onMove);
    overlay.removeEventListener('touchmove', onMove);
    overlay.removeEventListener('mouseleave', onLeave);
  };

  function frame() {
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    const ns = _lcNodes;
    const D = _LC.dist, mx = _lcMouse.x, my = _lcMouse.y;

    for (let i = 0; i < ns.length; i++) {
      const a = ns[i];
      for (let j = i + 1; j < ns.length; j++) {
        const b = ns[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d = Math.sqrt(dx*dx + dy*dy);
        if (d < D) {
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
          ctx.strokeStyle = `rgba(180,190,210,${(1 - d / D) * 0.35})`;
          ctx.lineWidth = .7; ctx.stroke();
        }
      }
      const mdx = a.x - mx, mdy = a.y - my;
      const md = Math.sqrt(mdx*mdx + mdy*mdy);
      if (md < D * 1.5) {
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(mx, my);
        ctx.strokeStyle = `rgba(180,190,210,${(1 - md / (D * 1.5)) * 0.65})`;
        ctx.lineWidth = 1; ctx.stroke();
      }
    }

    for (const n of ns) {
      const mdx = n.x - mx, mdy = n.y - my;
      const near = Math.sqrt(mdx*mdx + mdy*mdy) < D * 1.2;
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r * (near ? 1.5 : 1), 0, Math.PI * 2);
      ctx.fillStyle = `rgba(180,190,210,${near ? 0.9 : 0.45})`;
      ctx.fill();
      n.x += n.vx; n.y += n.vy;
      if (n.x < 0 || n.x > W) { n.vx *= -1; n.x = Math.max(0, Math.min(W, n.x)); }
      if (n.y < 0 || n.y > H) { n.vy *= -1; n.y = Math.max(0, Math.min(H, n.y)); }
    }

    _lcRaf = requestAnimationFrame(frame);
  }

  if (_lcRaf) cancelAnimationFrame(_lcRaf);
  _lcRaf = requestAnimationFrame(frame);
}

function _loginCanvasStop() {
  if (_lcRaf) { cancelAnimationFrame(_lcRaf); _lcRaf = null; }
  const canvas = document.getElementById('pin-canvas');
  if (canvas?._lcCleanup) { canvas._lcCleanup(); canvas._lcCleanup = null; }
  _lcNodes = [];
  _lcMouse = { x: -9999, y: -9999 };
}

// ── Listeners globais (universais — sempre seguros de anexar) ──────────────
const FOCUSABLE_SEL = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

document.addEventListener('keydown', e => {
  if (e.key !== 'Tab') return;
  const modal = document.querySelector('.overlay:not(.hidden)');
  if (!modal) return;
  const focaveis = [...modal.querySelectorAll(FOCUSABLE_SEL)].filter(el => el.offsetParent !== null);
  if (!focaveis.length) return;
  const primeiro = focaveis[0], ultimo = focaveis[focaveis.length - 1];
  if (e.shiftKey && document.activeElement === primeiro) { e.preventDefault(); ultimo.focus(); }
  else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primeiro.focus(); }
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    const aberto = [...document.querySelectorAll('.overlay:not(.hidden)')].find(o => o.id !== 'overlay-pin' && o.id !== 'overlay-force-pwd');
    if (!aberto) return;
    // #confirm-overlay precisa passar pelo botão Cancelar (não só esconder) —
    // ver comentário equivalente no handler de clique-fora, mesmo overlay.
    if (aberto.id === 'confirm-overlay') { document.getElementById('confirm-cancel')?.click(); return; }
    aberto.classList.add('hidden');
  }
});

document.addEventListener('keydown', e => {
  if ((e.key === 'Enter' || e.key === ' ') && e.target.getAttribute('role') === 'button') {
    e.preventDefault();
    e.target.click();
  }
});

// ── Aviso de servidor desatualizado (compartilhado pelos 4 sistemas) ──────────
// Cada app chama checarVersaoServidor(APP_VERSION, 'Iniciar <App>.bat') no login.
// Compara a versão do processo Python rodando (via /health) com a da página; se o
// servidor for mais antigo (iniciado antes de uma atualização → rotas novas dão
// 404 até reiniciar), mostra uma faixa no topo orientando a reiniciar.
async function checarVersaoServidor(appVersion, batName) {
  let sv;
  try {
    const r = await fetch('/health', { cache: 'no-store' });
    sv = (await r.json())?.version;
  } catch { return; }  // servidor inacessível: o resto do app já sinaliza
  if (sv === appVersion) return;
  const msg = sv
    ? `Servidor em execução: v${sv} · esta página: v${appVersion}. Reinicie o servidor (${batName}) para carregar a versão nova — funções novas podem falhar até lá.`
    : `O servidor em execução é uma versão antiga e não informa a versão. Reinicie o servidor (${batName}) — funções novas podem falhar até lá.`;
  let bar = document.getElementById('server-version-warn');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'server-version-warn';
    bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:9999;background:#b45309;color:#fff;padding:8px 44px 8px 16px;font-size:.85rem;line-height:1.4;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.35)';
    bar.innerHTML = '<span id="server-version-warn-msg"></span><button onclick="this.parentElement.remove()" title="Dispensar" style="position:absolute;right:10px;top:6px;background:rgba(255,255,255,.2);border:none;color:#fff;border-radius:4px;padding:2px 9px;cursor:pointer">✕</button>';
    document.body.appendChild(bar);
  }
  document.getElementById('server-version-warn-msg').textContent = '⚠ ' + msg;
}
