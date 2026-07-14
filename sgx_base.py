# sgx_base.py — esqueleto compartilhado da família SGCD/SGCA/SGDP/SGEA
#
# Fonte canônica: C:\Users\devtu\Documents\Claude Code\_esqueleto\sgx_base.py
# Cópias vendorizadas em cada sistema são geradas por sync.py — não editar a
# cópia dentro de SGCD/, SGCA/, SGDP/, SGEA/ diretamente, editar aqui e rodar
# `python sync.py`.
#
# Cada função aqui é parametrizada explicitamente (recebe get_db/ttl/tabela
# como argumento) em vez de depender de uma constante global do módulo —
# assim o server.py de cada sistema continua dono do seu próprio DB_PATH,
# SESSION_TTL etc., só importa e chama o que precisa:
#
#   import sgx_base
#   get_db = sgx_base.make_get_db(DB_PATH)
#   ...
#   token = sgx_base.create_session(get_db, user_id, SESSION_TTL)

import hashlib
import secrets
import smtplib
import ssl
import sqlite3
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# ── Banco de dados ──────────────────────────────────────────────────────────

class ConnAutoClose(sqlite3.Connection):
    """sqlite3.Connection.__exit__ só faz commit/rollback da transação — não
    fecha a conexão. Sem isso, todo `with get_db() as conn:` vaza uma conexão
    aberta por chamada. Fecha a conexão junto, sem precisar alterar nenhum
    call site."""
    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


def connect_db(db_path):
    """IMPORTANTE: não usar como fábrica (`get_db = lambda: connect_db(X)` capturado
    uma única vez) — os testes de cada sistema reatribuem `server.DB_PATH` depois do
    import (`setUpModule` isola o banco num diretório temporário) e esperam que
    `get_db()` releia esse global a cada chamada, não um valor congelado no import.
    Cada sistema deve manter seu próprio wrapper fino:

        def get_db():
            return sgx_base.connect_db(DB_PATH)

    assim `DB_PATH` é resolvido no namespace do próprio server.py a cada chamada,
    exatamente como a função get_db() original (não vendorizada) sempre fez."""
    conn = sqlite3.connect(db_path, factory=ConnAutoClose)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


# ── Senhas (PBKDF2-HMAC-SHA256) ──────────────────────────────────────────────

def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100_000)
    return f'{salt}:{dk.hex()}'


def verify_password(password, stored):
    try:
        salt, _ = stored.split(':', 1)
        return secrets.compare_digest(hash_password(password, salt), stored)
    except Exception:
        return False


# ── Rate limit de tentativas de login ───────────────────────────────────────
# ponytail: dict em memória, sem lock — pior caso é uma contagem levemente
# imprecisa sob concorrência, não uma falha; zera a cada reinício do servidor.

class LoginRateLimiter:
    def __init__(self, max_attempts=5, lockout_window=300):
        self.max_attempts = max_attempts
        self.lockout_window = lockout_window
        self._failures = {}   # username (lower) -> [timestamps de tentativas falhas]

    def is_locked(self, username):
        key = (username or '').strip().lower()
        now = time.time()
        attempts = [t for t in self._failures.get(key, []) if now - t < self.lockout_window]
        self._failures[key] = attempts
        return len(attempts) >= self.max_attempts

    def record_failure(self, username):
        key = (username or '').strip().lower()
        self._failures.setdefault(key, []).append(time.time())

    def clear(self, username):
        self._failures.pop((username or '').strip().lower(), None)


# ── Sessões (Bearer token com TTL renovado por ping) ────────────────────────

def create_session(get_db, user_id, ttl):
    token = secrets.token_urlsafe(32)
    expires = time.time() + ttl
    with get_db() as conn:
        conn.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
        conn.execute('INSERT INTO sessions (token,user_id,expires) VALUES (?,?,?)', (token, user_id, expires))
    return token


def get_session(get_db, token, usuarios_table='usuarios'):
    if not token:
        return None
    with get_db() as conn:
        row = conn.execute(
            f'''SELECT s.token, s.user_id, s.expires, u.*
                FROM sessions s JOIN {usuarios_table} u ON u.id=s.user_id
                WHERE s.token=? AND s.expires>? AND u.ativo=1''',
            (token, time.time())
        ).fetchone()
    return dict(row) if row else None


def delete_session(get_db, token):
    with get_db() as conn:
        conn.execute('DELETE FROM sessions WHERE token=?', (token,))


def renew_session(get_db, token, ttl):
    with get_db() as conn:
        conn.execute('UPDATE sessions SET expires=? WHERE token=?', (time.time() + ttl, token))


def active_sessions(get_db):
    with get_db() as conn:
        return conn.execute('SELECT COUNT(*) FROM sessions WHERE expires>?', (time.time(),)).fetchone()[0]


def purge_expired_sessions(get_db):
    """Chamar a cada iteração do watchdog de cada sistema (o loop em si —
    sleep, hooks de backup/auditoria/alertas próprios de cada domínio —
    continua no server.py de cada sistema, só a limpeza de sessão é comum)."""
    with get_db() as conn:
        conn.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))


# ── E-mail (SMTP puro, sem dependência externa) ─────────────────────────────

def send_email_raw(smtp, frm, to, subj, html, plain=''):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subj
    msg['From']    = f"{frm['name']} <{frm['email']}>"
    msg['To']      = to if isinstance(to, str) else ', '.join(to)
    if plain: msg.attach(MIMEText(plain, 'plain', 'utf-8'))
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    port = int(smtp.get('port', 587))
    host = smtp['host']
    user = smtp['auth']['user']
    pw   = smtp['auth']['pass']

    ctx = ssl.create_default_context()
    if smtp.get('ignoreSSL'):
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE

    if smtp.get('secure'):
        with smtplib.SMTP_SSL(host, port, context=ctx) as s:
            s.login(user, pw); s.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as s:
            s.ehlo()
            if smtp.get('requireTLS', True): s.starttls(context=ctx)
            s.login(user, pw); s.send_message(msg)


# ── Configurações genéricas (sys_settings key/value) ────────────────────────

def save_settings(get_db, data):
    """Regra: string vazia nunca sobrescreve um valor já salvo — evita que um
    formulário em branco (ex.: senha SMTP não recarregada) apague a
    configuração real ao salvar. Para limpar um campo de propósito, editar
    o banco direto."""
    with get_db() as conn:
        for key, value in data.items():
            if value == '' or value is None:
                continue
            conn.execute('INSERT OR REPLACE INTO sys_settings (key,value) VALUES (?,?)', (key, str(value)))


# ── Auditoria genérica ───────────────────────────────────────────────────────

def add_audit(get_db, table, audit_id, ts, user_id, user_nome, tipo, detail, process_id=None):
    """user_id/user_nome devem sempre vir da sessão autenticada no chamador,
    nunca do corpo da requisição — senão qualquer chamada poderia forjar
    auditoria em nome de outro usuário. `table` é parametrizado porque o
    nome da tabela de auditoria difere entre sistemas (audit_global / auditoria)."""
    with get_db() as conn:
        conn.execute(
            f'''INSERT INTO {table} (id,ts,user_id,user_nome,type,label,detail,process_id)
                VALUES (?,?,?,?,?,?,?,?)''',
            (audit_id, ts, user_id, user_nome, tipo, tipo, detail, process_id)
        )
