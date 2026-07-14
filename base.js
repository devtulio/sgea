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
