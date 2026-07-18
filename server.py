# SGEA v0.13.3 — Servidor local: SQLite, autenticação, REST API, controle de estoque por lote (FEFO), backup automático
import http.server
import socketserver
import os
import json
import sqlite3
import hashlib
import ssl
import smtplib
import threading
import time
import subprocess
import sys
import urllib.request
import urllib.error
import logging
import uuid
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urlparse, parse_qs

import sgx_base

# Windows: console pode usar cp1252/cp850 em vez de UTF-8, quebrando prints
# com caracteres especiais (╔═╗, emojis). Força UTF-8 para evitar UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

PORT        = int(os.environ.get('SGEA_PORT', 3003))
_BASE       = os.path.dirname(os.path.abspath(__file__))
# SGEA_DATA_DIR: usado pelos testes E2E para isolar banco/backups do sgea.db
# real sem precisar rodar o servidor a partir de outra pasta (os arquivos
# estáticos como SGEA.html continuam servidos a partir de _BASE).
_DATA_DIR   = os.environ.get('SGEA_DATA_DIR', _BASE)
DB_PATH     = os.path.join(_DATA_DIR, 'sgea.db')
BACKUP_DIR  = os.path.join(_DATA_DIR, 'backups')
PROFILE_DIR = os.path.join(_DATA_DIR, 'browser-profile')
LOG_PATH    = os.path.join(_DATA_DIR, 'sgea_errors.log')
BACKUP_KEEP = 7      # número de backups automáticos mantidos
SESSION_TTL = 60     # renovado pelo ping a cada 5s (ver comentário em _watchdog mais abaixo)

os.makedirs(_DATA_DIR, exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH, level=logging.ERROR,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
_log = logging.getLogger('sgea')

os.chdir(_BASE)

_watchdog_paused  = False   # pausa o watchdog durante diálogos bloqueantes (ex: FolderBrowser)
_had_session      = False   # True após primeiro login; controla quando o backup pós-sessão pode disparar
_backup_pos_sess  = False   # True = backup pós-sessão já executado; aguarda nova sessão para resetar
_last_trash_purge = 0       # time.time() da última purga da lixeira (roda no máx. 1x/hora)
TRASH_RETENTION_DIAS = 30   # dias até um registro na lixeira ser apagado de vez

# ── Banco de dados ────────────────────────────────────────────────────────────

# Alias de compatibilidade: _ConnAutoClose é referenciada diretamente em vários
# pontos além de get_db() (backup manual, restore, integrity check) — manter o
# nome em vez de caçar cada call site.
_ConnAutoClose = sgx_base.ConnAutoClose

def get_db():
    return sgx_base.connect_db(DB_PATH)

def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT NOT NULL UNIQUE COLLATE NOCASE,
                nome       TEXT NOT NULL,
                senha_hash TEXT NOT NULL,
                admin      INTEGER DEFAULT 0,
                ativo      INTEGER DEFAULT 1,
                must_change_password INTEGER DEFAULT 0,
                criado_em  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token   TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                expires REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_global (
                id TEXT PRIMARY KEY, ts TEXT NOT NULL, user_id INTEGER, user_nome TEXT,
                type TEXT, label TEXT, detail TEXT, process_id TEXT, process_obj TEXT
            );
            CREATE TABLE IF NOT EXISTS sys_settings (
                key TEXT PRIMARY KEY, value TEXT
            );

            CREATE TABLE IF NOT EXISTS centros_custo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE,
                nome TEXT NOT NULL,
                ativo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS fornecedores (
                id TEXT PRIMARY KEY,
                cnpj TEXT UNIQUE,
                razao_social TEXT NOT NULL,
                nome_fantasia TEXT,
                telefone TEXT,
                email TEXT,
                ativo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS funcionarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cargo TEXT,
                unidade TEXT,
                matricula TEXT,
                ativo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS frota (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero TEXT UNIQUE,
                placa TEXT,
                marca TEXT,
                modelo TEXT,
                combustivel TEXT,
                centro_custo_id INTEGER REFERENCES centros_custo(id),
                ativo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS produtos (
                id TEXT PRIMARY KEY,
                codigo_fiorilli TEXT NOT NULL UNIQUE,
                nome TEXT NOT NULL,
                centro_custo_id INTEGER REFERENCES centros_custo(id),
                unidade_licitada TEXT,
                qtd_por_embalagem INTEGER NOT NULL DEFAULT 1,
                unidade_consumo TEXT NOT NULL DEFAULT 'UN',
                situacao_licitacao TEXT,
                codigo_licitacao TEXT,
                objeto_licitacao TEXT,
                ativo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS pedidos (
                id TEXT PRIMARY KEY,
                numero TEXT NOT NULL,
                codigo_licitacao TEXT,
                data_pedido TEXT,
                fornecedor_id TEXT REFERENCES fornecedores(id),
                status TEXT DEFAULT 'aberto',
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
                updated_at TEXT,
                UNIQUE(numero, codigo_licitacao)
            );
            CREATE TABLE IF NOT EXISTS entradas (
                id TEXT PRIMARY KEY,
                pedido_id TEXT REFERENCES pedidos(id),
                tipo TEXT NOT NULL DEFAULT 'pedido' CHECK(tipo IN ('pedido','compra_direta')),
                fornecedor_id TEXT REFERENCES fornecedores(id),
                nfe_numero TEXT,
                nfe_chave_acesso TEXT,
                data_entrega TEXT NOT NULL,
                recebedor_id INTEGER REFERENCES funcionarios(id),
                centro_custo_id INTEGER REFERENCES centros_custo(id),
                observacao TEXT,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
                created_by INTEGER REFERENCES usuarios(id),
                updated_at TEXT,
                deleted_at TEXT
            );
            CREATE TABLE IF NOT EXISTS entrada_itens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entrada_id TEXT NOT NULL REFERENCES entradas(id) ON DELETE CASCADE,
                produto_id TEXT NOT NULL REFERENCES produtos(id),
                quantidade_embalagem REAL,
                quantidade_unidades INTEGER NOT NULL,
                valor_unitario REAL NOT NULL,
                valor_total REAL NOT NULL,
                lote_numero TEXT,
                data_validade TEXT
            );
            CREATE TABLE IF NOT EXISTS pedido_itens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pedido_id TEXT NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
                produto_id TEXT NOT NULL REFERENCES produtos(id),
                quantidade_pedida INTEGER NOT NULL CHECK(quantidade_pedida > 0),
                quantidade_anulada INTEGER NOT NULL DEFAULT 0,
                UNIQUE(pedido_id, produto_id)
            );
            CREATE TABLE IF NOT EXISTS lotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                produto_id TEXT NOT NULL REFERENCES produtos(id),
                lote_numero TEXT,
                data_validade TEXT,
                quantidade_recebida INTEGER NOT NULL,
                quantidade_atual INTEGER NOT NULL CHECK(quantidade_atual >= 0),
                valor_unitario_custo REAL NOT NULL DEFAULT 0,
                entrada_item_id INTEGER REFERENCES entrada_itens(id),
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_lotes_produto_validade ON lotes(produto_id, data_validade);

            CREATE TABLE IF NOT EXISTS saidas (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                solicitante_id INTEGER REFERENCES funcionarios(id),
                solicitante_nome TEXT,
                solicitante_cargo TEXT,
                centro_custo_id INTEGER REFERENCES centros_custo(id),
                frota_id INTEGER REFERENCES frota(id),
                numero_solicitacao TEXT,
                observacao TEXT,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
                created_by INTEGER REFERENCES usuarios(id),
                deleted_at TEXT
            );
            CREATE TABLE IF NOT EXISTS saida_itens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                saida_id TEXT NOT NULL REFERENCES saidas(id) ON DELETE CASCADE,
                produto_id TEXT NOT NULL REFERENCES produtos(id),
                quantidade INTEGER NOT NULL CHECK(quantidade > 0),
                valor_unitario_medio REAL NOT NULL,
                valor_total REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS saida_item_lotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                saida_item_id INTEGER NOT NULL REFERENCES saida_itens(id) ON DELETE CASCADE,
                lote_id INTEGER NOT NULL REFERENCES lotes(id),
                quantidade INTEGER NOT NULL CHECK(quantidade > 0),
                valor_unitario_custo REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_entradas_deleted ON entradas(deleted_at);
            CREATE INDEX IF NOT EXISTS idx_saidas_deleted ON saidas(deleted_at);
            CREATE INDEX IF NOT EXISTS idx_produtos_ativo ON produtos(ativo);
        ''')
        cols_usu = [r[1] for r in conn.execute('PRAGMA table_info(usuarios)').fetchall()]
        if 'cpf' not in cols_usu: conn.execute("ALTER TABLE usuarios ADD COLUMN cpf TEXT DEFAULT ''")
        if 'email' not in cols_usu: conn.execute("ALTER TABLE usuarios ADD COLUMN email TEXT DEFAULT ''")
        if 'cargo' not in cols_usu: conn.execute("ALTER TABLE usuarios ADD COLUMN cargo TEXT DEFAULT ''")
        if 'matricula' not in cols_usu: conn.execute("ALTER TABLE usuarios ADD COLUMN matricula TEXT DEFAULT ''")
        conn.execute('''
            CREATE VIEW IF NOT EXISTS v_estoque AS
            SELECT p.id AS produto_id,
                   COALESCE(SUM(l.quantidade_atual), 0) AS estoque_fisico,
                   COALESCE(SUM(l.quantidade_atual * l.valor_unitario_custo), 0) AS estoque_financeiro,
                   MIN(CASE WHEN l.quantidade_atual > 0 THEN l.data_validade END) AS proxima_validade
            FROM produtos p LEFT JOIN lotes l ON l.produto_id = p.id
            GROUP BY p.id
        ''')
        # Sessões são descartadas a cada início do servidor (logout automático ao fechar janela)
        conn.execute('DELETE FROM sessions')
        conn.executemany('INSERT OR IGNORE INTO sys_settings VALUES (?,?)', [
            ('orgao', ''), ('municipio', ''), ('cnpj_orgao', ''), ('aut_nome', ''), ('aut_cargo', ''),
            ('backup_path', BACKUP_DIR),
            ('auto_backup_enabled', '1'),
            ('auto_backup_keep', str(BACKUP_KEEP)),
            ('smtp_host', ''), ('smtp_port', '587'), ('smtp_user', ''), ('smtp_pass', ''),
            ('smtp_secure', '0'), ('smtp_require_tls', '1'), ('smtp_ignore_ssl', '0'),
            ('smtp_from_name', ''), ('smtp_to', ''),
        ])
        conn.commit()
        if conn.execute('SELECT COUNT(*) FROM usuarios').fetchone()[0] == 0:
            conn.execute(
                'INSERT INTO usuarios (username,nome,senha_hash,admin,must_change_password) VALUES (?,?,?,1,1)',
                ('admin', 'Administrador', _hash_password('admin123'))
            )
            conn.commit()
            print('Usuário padrão criado: admin / admin123 — troque a senha no primeiro acesso.')

# ── Segurança ─────────────────────────────────────────────────────────────────

_hash_password   = sgx_base.hash_password
_verify_password = sgx_base.verify_password

# ── Rate limit de login ─────────────────────────────────────────────────────
LOGIN_MAX_ATTEMPTS   = 5
LOGIN_LOCKOUT_WINDOW = 300   # 5 min — janela deslizante de tentativas falhas
_rate_limiter = sgx_base.LoginRateLimiter(LOGIN_MAX_ATTEMPTS, LOGIN_LOCKOUT_WINDOW)
_login_rate_limited   = _rate_limiter.is_locked
_record_login_failure = _rate_limiter.record_failure
_clear_login_failures  = _rate_limiter.clear

# create_session/delete_session/renew_session/active_sessions delegam pro
# sgx_base (mecânica idêntica nos 4 sistemas). get_session() fica local: faz
# um SELECT de colunas explícito (não u.*) por segurança — nunca deve devolver
# a coluna de hash de senha junto com os dados da sessão — e as colunas
# selecionadas divergem por sistema (schema de usuarios não é idêntico).
def create_session(user_id):
    return sgx_base.create_session(get_db, user_id, SESSION_TTL)

def get_session(token):
    if not token:
        return None
    with get_db() as conn:
        row = conn.execute(
            '''SELECT s.token, s.user_id, s.expires, u.nome, u.username, u.admin, u.ativo
               FROM sessions s JOIN usuarios u ON u.id=s.user_id
               WHERE s.token=? AND s.expires>? AND u.ativo=1''',
            (token, time.time())
        ).fetchone()
    return dict(row) if row else None

def delete_session(token):
    sgx_base.delete_session(get_db, token)

def renew_session(token):
    sgx_base.renew_session(get_db, token, SESSION_TTL)

def active_sessions():
    return sgx_base.active_sessions(get_db)

def _check_shutdown():
    """Dispara um backup automático, uma única vez, depois que a última sessão
    ativa termina. O servidor nunca encerra sozinho — só via Ctrl+C."""
    global _backup_pos_sess
    if _had_session and active_sessions() == 0 and not _backup_pos_sess:
        _backup_pos_sess = True
        cfg = _get_backup_cfg()
        if cfg['enabled']:
            print('\nÚltima sessão encerrada. Executando backup automático...')
            _do_json_backup(cfg)
            _do_db_backup(cfg)

# ── Utilitários ───────────────────────────────────────────────────────────────

def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%S')

def _float(v):
    if v is None or v == '':
        return None
    try:
        return float(str(v).replace(',', '.').replace('R$', '').strip())
    except Exception:
        return None

def _require(data, *fields):
    for f in fields:
        v = data.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ValueError(f'Campo obrigatório: {f}')

class EstoqueInsuficiente(Exception):
    def __init__(self, produto_id, solicitado, disponivel):
        self.produto_id, self.solicitado, self.disponivel = produto_id, solicitado, disponivel
        super().__init__(f'Estoque insuficiente para o produto (solicitado: {solicitado}, disponível: {disponivel})')

class SaldoPedidoExcedido(Exception):
    def __init__(self, mensagem):
        super().__init__(mensagem)

def _pedido_item_status(pedida, recebida, anulada):
    if anulada > 0:
        return 'encerrado_parcial'
    if recebida >= pedida:
        return 'atendido'
    if recebida > 0:
        return 'parcial'
    return 'aberto'

def _pedido_itens_com_saldo(conn, pedido_id):
    """Itens do pedido com quantidade_recebida/saldo/status calculados a partir das
    entradas vinculadas — quantidade_recebida nunca é armazenada, só derivada, pra não
    correr o risco de um contador desalinhar da soma real de entrada_itens."""
    rows = conn.execute('''
        SELECT pi.id, pi.produto_id, pi.quantidade_pedida, pi.quantidade_anulada,
               p.nome AS produto_nome, p.unidade_consumo,
               COALESCE((
                   SELECT SUM(ei.quantidade_unidades)
                   FROM entrada_itens ei JOIN entradas e ON e.id = ei.entrada_id
                   WHERE e.pedido_id = pi.pedido_id AND ei.produto_id = pi.produto_id AND e.deleted_at IS NULL
               ), 0) AS quantidade_recebida
        FROM pedido_itens pi JOIN produtos p ON p.id = pi.produto_id
        WHERE pi.pedido_id = ?
        ORDER BY pi.id
    ''', (pedido_id,)).fetchall()
    itens = []
    for r in rows:
        d = dict(r)
        d['saldo'] = max(d['quantidade_pedida'] - d['quantidade_recebida'] - d['quantidade_anulada'], 0)
        d['status'] = _pedido_item_status(d['quantidade_pedida'], d['quantidade_recebida'], d['quantidade_anulada'])
        itens.append(d)
    return itens

def _pedido_status_agregado(status_coluna, itens):
    """Status exibido do pedido: 'cancelado' é o único valor manual (setado só por
    _cancelar_pedido); qualquer outra coisa é sempre recalculada a partir dos itens,
    nunca lida da coluna — evita a coluna e os itens saírem de sincronia."""
    if status_coluna == 'cancelado':
        return 'cancelado'
    if not itens:
        return 'aberto'
    if any(i['status'] in ('aberto', 'parcial') for i in itens):
        return 'aberto'
    if all(i['status'] == 'atendido' for i in itens):
        return 'atendido'
    return 'encerrado_parcial'

def _consumir_fefo(conn, produto_id, quantidade_solicitada):
    """Consome `quantidade_solicitada` unidades do produto, priorizando o lote
    com validade mais próxima (FEFO); lotes sem validade (incl. saldo inicial)
    são consumidos por último, em ordem de chegada. Levanta EstoqueInsuficiente
    sem alterar nenhuma linha se o total disponível não cobrir o pedido — quem
    chama roda isso dentro do mesmo `with get_db()` do resto da operação, então
    qualquer exceção desfaz tudo via _ConnAutoClose."""
    lotes = conn.execute('''
        SELECT id, quantidade_atual, valor_unitario_custo
        FROM lotes
        WHERE produto_id = ? AND quantidade_atual > 0
        ORDER BY (data_validade IS NULL) ASC, data_validade ASC, id ASC
    ''', (produto_id,)).fetchall()

    disponivel = sum(l['quantidade_atual'] for l in lotes)
    if disponivel < quantidade_solicitada:
        raise EstoqueInsuficiente(produto_id, quantidade_solicitada, disponivel)

    restante, consumos = quantidade_solicitada, []
    for l in lotes:
        if restante <= 0:
            break
        qtd = min(l['quantidade_atual'], restante)
        conn.execute('UPDATE lotes SET quantidade_atual = quantidade_atual - ? WHERE id = ?', (qtd, l['id']))
        consumos.append((l['id'], qtd, l['valor_unitario_custo']))
        restante -= qtd

    valor_total = sum(q * c for _, q, c in consumos)
    valor_medio = valor_total / quantidade_solicitada if quantidade_solicitada else 0
    return consumos, valor_medio, valor_total

def _lotes_vencendo(dias):
    """Lotes com saldo vencidos ou vencendo dentro de `dias`. Compartilhado entre
    GET /api/alertas/validade e o alerta diário por e-mail (_send_daily_alerts)."""
    limite = time.strftime('%Y-%m-%d', time.localtime(time.time() + dias * 86400))
    hoje = time.strftime('%Y-%m-%d')
    with get_db() as conn:
        rows = conn.execute('''
            SELECT l.*, p.nome AS produto_nome, p.codigo_fiorilli, p.unidade_consumo,
                   c.nome AS centro_custo_nome
            FROM lotes l
            JOIN produtos p ON p.id=l.produto_id
            LEFT JOIN centros_custo c ON c.id=p.centro_custo_id
            WHERE l.quantidade_atual > 0 AND l.data_validade IS NOT NULL AND l.data_validade <= ?
            ORDER BY l.data_validade ASC
        ''', (limite,)).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d['vencido'] = d['data_validade'] < hoje
        items.append(d)
    return items

def _find_browser():
    for c in [
        os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe'),
        os.path.expandvars(r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe'),
        os.path.expandvars(r'%LocalAppData%\Google\Chrome\Application\chrome.exe'),
        os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'),
    ]:
        if os.path.isfile(c):
            return c
    return None

# ── CRUD genérico de cadastros mestre ───────────────────────────────────────
# centros_custo/fornecedores/funcionarios/frota/pedidos têm a mesma forma
# (id + colunas simples + ativo/status + created_at/updated_at), então um
# único motor parametrizado evita reescrever list/get/create/update 5 vezes.

CRUD_TABLES = {
    'centros_custo': {
        'id_type': 'int', 'fields': ['codigo', 'nome', 'ativo'],
        'required': ['nome'], 'order': 'nome ASC', 'search_fields': ['nome', 'codigo'],
    },
    'fornecedores': {
        'id_type': 'uuid', 'fields': ['cnpj', 'razao_social', 'nome_fantasia', 'telefone', 'email', 'ativo'],
        'required': ['razao_social'], 'order': 'razao_social ASC',
        'search_fields': ['razao_social', 'nome_fantasia', 'cnpj'],
    },
    'funcionarios': {
        'id_type': 'int', 'fields': ['nome', 'cargo', 'unidade', 'matricula', 'ativo'],
        'required': ['nome'], 'order': 'nome ASC', 'search_fields': ['nome', 'cargo', 'unidade'],
    },
    'frota': {
        'id_type': 'int', 'fields': ['numero', 'placa', 'marca', 'modelo', 'combustivel', 'centro_custo_id', 'ativo'],
        'required': ['numero'], 'order': 'numero ASC', 'search_fields': ['numero', 'placa', 'modelo'],
    },
}
CRUD_ROUTES = {  # segmento da URL -> tabela
    'centros-custo': 'centros_custo', 'fornecedores': 'fornecedores',
    'funcionarios': 'funcionarios', 'frota': 'frota',
    # pedidos NÃO está aqui — tem itens, o motor genérico não suporta; handlers
    # dedicados abaixo (_get_pedido_dict/_create_pedido/_update_pedido/etc).
}

def _crud_list(table, qs):
    cfg = CRUD_TABLES[table]
    q = (qs.get('q', [''])[0] or '').strip()
    where, params = [], []
    if q and cfg['search_fields']:
        ors = ' OR '.join(f'{f} LIKE ?' for f in cfg['search_fields'])
        where.append(f'({ors})')
        params += [f'%{q}%'] * len(cfg['search_fields'])
    w = ('WHERE ' + ' AND '.join(where)) if where else ''
    with get_db() as conn:
        rows = conn.execute(f'SELECT * FROM {table} {w} ORDER BY {cfg["order"]}', params).fetchall()
    return [dict(r) for r in rows]

def _crud_get(table, id_):
    with get_db() as conn:
        row = conn.execute(f'SELECT * FROM {table} WHERE id=?', (id_,)).fetchone()
    return dict(row) if row else None

def _crud_create(table, data):
    cfg = CRUD_TABLES[table]
    _require(data, *cfg['required'])
    fields = {k: data[k] for k in cfg['fields'] if k in data}
    cols, vals = list(fields.keys()), list(fields.values())
    with get_db() as conn:
        if cfg['id_type'] == 'uuid':
            new_id = str(uuid.uuid4())
            conn.execute(f'INSERT INTO {table} (id,{",".join(cols)}) VALUES (?,{",".join("?" * len(cols))})',
                         [new_id] + vals)
        else:
            cur = conn.execute(f'INSERT INTO {table} ({",".join(cols)}) VALUES ({",".join("?" * len(cols))})', vals)
            new_id = cur.lastrowid
        row = conn.execute(f'SELECT * FROM {table} WHERE id=?', (new_id,)).fetchone()
    return dict(row)

def _crud_update(table, id_, data):
    cfg = CRUD_TABLES[table]
    fields = {k: data[k] for k in cfg['fields'] if k in data}
    with get_db() as conn:
        if fields:
            fields['updated_at'] = _now()
            conn.execute(f'UPDATE {table} SET {",".join(f"{k}=?" for k in fields)} WHERE id=?',
                         list(fields.values()) + [id_])
        row = conn.execute(f'SELECT * FROM {table} WHERE id=?', (id_,)).fetchone()
    return dict(row) if row else None

def _crud_delete(table, id_):
    with get_db() as conn:
        conn.execute(f'DELETE FROM {table} WHERE id=?', (id_,))

# ── HTTP Handler ──────────────────────────────────────────────────────────────

class SGEAHandler(http.server.SimpleHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def end_headers(self):
        # SGEA.html muda com frequência entre versões; sem isso o navegador
        # pode servir do cache sem revalidar com o servidor.
        if self.command == 'GET' and urlparse(self.path).path.rstrip('/').endswith(('.html', '.js', '.css')):
            self.send_header('Cache-Control', 'no-cache, must-revalidate')
        super().end_headers()

    def _safe_dispatch(self, inner):
        # handle_error (do socketserver.BaseServer) nunca é chamado de verdade
        # para exceções dentro do request handler — sem isto, um erro não
        # tratado só derrubaria a conexão em silêncio, sem nada no log.
        try:
            inner()
        except Exception as e:
            _log.error('Erro não tratado em %s %s: %s', self.command, self.path, e)
            try:
                self._json(500, {'error': 'Erro interno no servidor.'})
            except Exception:
                pass

    def do_GET(self):
        self._safe_dispatch(self._do_GET)

    def _do_GET(self):
        parsed = urlparse(self.path)
        p = parsed.path.rstrip('/')
        qs = parse_qs(parsed.query)

        if p == '/health':
            self._json(200, {'ok': True})
        elif p == '/api/public/org-info':
            with get_db() as conn:
                row = conn.execute("SELECT value FROM sys_settings WHERE key='orgao'").fetchone()
            self._json(200, {'orgao': row['value'] if row else ''})
        elif p == '/api/public/last-backup':
            with get_db() as conn:
                row = conn.execute("SELECT value FROM sys_settings WHERE key='auto_backup_last'").fetchone()
            self._json(200, {'ts': row['value'] if row else None})
        elif p == '/api/auth/logout':
            tok = qs.get('token', [None])[0] or self._token()
            delete_session(tok)
            self._json(200, {'ok': True})
            threading.Thread(target=_check_shutdown, daemon=True).start()
        elif p.startswith('/cnpj/'):
            self._proxy_cnpj(p[6:].strip('/'))
        elif p.startswith('/api/'):
            s = self._auth()
            if s:
                self._route_get(p, qs, s)
        else:
            super().do_GET()

    def do_POST(self):
        self._safe_dispatch(self._do_POST)

    def _do_POST(self):
        parsed = urlparse(self.path)
        p = parsed.path.rstrip('/')

        if p == '/api/auth/login':
            self._login(self._body())
            return
        if p == '/api/auth/logout':
            qs_tok = parse_qs(parsed.query).get('token', [None])[0]
            delete_session(qs_tok or self._token())
            self._json(200, {'ok': True})
            threading.Thread(target=_check_shutdown, daemon=True).start()
            return

        s = self._auth()
        if not s:
            return
        self._route_post(p, self._body(), s)

    def do_PUT(self):
        self._safe_dispatch(self._do_PUT)

    def _do_PUT(self):
        p = urlparse(self.path).path.rstrip('/')
        s = self._auth()
        if not s:
            return
        self._route_put(p, self._body(), s)

    def do_DELETE(self):
        self._safe_dispatch(self._do_DELETE)

    def _do_DELETE(self):
        parsed = urlparse(self.path)
        p = parsed.path.rstrip('/')
        qs = parse_qs(parsed.query)
        s = self._auth()
        if not s:
            return
        self._route_delete(p, qs, s)

    # ── Roteamento ────────────────────────────────────────────────────────────

    def _route_get(self, p, qs, s):
        def qp(k, d=None):
            v = qs.get(k)
            return v[0] if v else d

        if p == '/api/auth/ping':
            renew_session(self._token())
            self._json(200, {'ok': True})
        elif p == '/api/auth/me':
            self._json(200, self._user_dict(s))

        elif p == '/api/produtos':
            self._list_produtos(qs)
        elif re.fullmatch(r'/api/produtos/[^/]+/lotes', p):
            self._list_lotes(p.split('/')[3])
        elif re.fullmatch(r'/api/produtos/[^/]+', p):
            self._get_produto(p.split('/')[-1])

        elif p == '/api/alertas/validade':
            self._alertas_validade(qs)

        elif p == '/api/pedidos':
            self._list_pedidos(qs)
        elif re.fullmatch(r'/api/pedidos/[^/]+', p):
            item = self._get_pedido_dict(p.split('/')[-1])
            self._json(200, item) if item else self._json(404, {'error': 'Não encontrado'})

        elif p == '/api/entradas':
            self._list_entradas(qs.get('trash', ['0'])[0] == '1')
        elif re.fullmatch(r'/api/entradas/[^/]+', p):
            item = self._get_entrada_dict(p.split('/')[-1])
            self._json(200, item) if item else self._json(404, {'error': 'Não encontrada'})

        elif p == '/api/saidas':
            self._list_saidas(qs.get('trash', ['0'])[0] == '1')
        elif re.fullmatch(r'/api/saidas/[^/]+', p):
            item = self._get_saida_dict(p.split('/')[-1])
            self._json(200, item) if item else self._json(404, {'error': 'Não encontrada'})

        elif p == '/api/audit':
            self._list_audit(qs)

        elif p == '/api/usuarios':
            if not s['admin']:
                self._json(403, {'error': 'Acesso restrito'}); return
            with get_db() as conn:
                rows = conn.execute('SELECT id,username,nome,admin,ativo,cpf,email,cargo,matricula,criado_em FROM usuarios').fetchall()
            self._json(200, [dict(r) for r in rows])

        elif p == '/api/relatorio/integridade':
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            self._relatorio_integridade()

        elif p == '/api/settings':
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT key,value FROM sys_settings WHERE key IN "
                    "('orgao','municipio','cnpj_orgao','aut_nome','aut_cargo',"
                    "'auto_backup_enabled','auto_backup_keep')"
                ).fetchall()
            self._json(200, {r['key']: r['value'] for r in rows})

        elif p in ('/api/settings/smtp', '/api/settings/smtp/'):
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            with get_db() as conn:
                rows = conn.execute("SELECT key,value FROM sys_settings WHERE key LIKE 'smtp_%'").fetchall()
            cfg = {r['key']: r['value'] for r in rows}
            cfg.pop('smtp_pass', None)  # senha nunca volta pro cliente depois de salva
            self._json(200, cfg)

        elif p in ('/api/settings/brasao', '/api/settings/brasao/'):
            # Endpoint separado de /api/settings: o brasão em base64 pode ter alguns
            # MB, incluí-lo na rota geral deixaria toda tela inicial mais lenta.
            with get_db() as conn:
                row = conn.execute("SELECT value FROM sys_settings WHERE key='brasao_dataurl'").fetchone()
            self._json(200, {'brasao_dataurl': row['value'] if row else ''})

        elif p == '/api/backup':
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            self._export_backup()
        elif p == '/api/backup/db':
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            self._export_db_backup()
        elif p == '/api/backups/cfg':
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            self._json(200, _get_backup_cfg())
        elif p == '/api/backups/db':
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            self._list_db_backups()
        elif p.startswith('/api/backups/db/download'):
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            self._download_db_backup(qp('name'))
        elif p == '/api/dialog/folder':
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            self._dialog_folder()

        else:
            # Cadastros mestre (CRUD genérico)
            for seg, table in CRUD_ROUTES.items():
                if p == f'/api/{seg}':
                    self._json(200, {'items': _crud_list(table, qs)}); return
                if re.fullmatch(rf'/api/{seg}/[^/]+', p):
                    item = _crud_get(table, p.split('/')[-1])
                    self._json(200, item) if item else self._json(404, {'error': 'Não encontrado'})
                    return
            self._json(404, {'error': 'Rota não encontrada'})

    def _route_post(self, p, body, s):
        if p == '/api/backups/db/restore':
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            self._restore_db_backup(body, s)
            return

        data = self._parse_json(body)

        if p == '/api/produtos':
            self._create_produto(data)
        elif p == '/api/pedidos':
            self._create_pedido(data)
        elif p == '/api/entradas':
            self._create_entrada(data, s)
        elif p == '/api/saidas':
            self._create_saida(data, s)
        elif p == '/api/usuarios':
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            self._create_user(data)
        elif p == '/api/audit':
            self._add_audit(data, s)
        elif p == '/send-email':
            self._send_email(data)
        elif p == '/api/backup/restore':
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            self._restore_backup(data, s)
        elif p == '/api/backups/db/now':
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            name = _do_db_backup()
            self._json(200, {'ok': bool(name), 'name': name})
        else:
            for seg, table in CRUD_ROUTES.items():
                if p == f'/api/{seg}':
                    try:
                        self._json(201, _crud_create(table, data))
                    except ValueError as e:
                        self._json(400, {'error': str(e)})
                    except sqlite3.IntegrityError:
                        self._json(409, {'error': 'Já existe um registro com esses dados'})
                    return
            self._json(404, {'error': 'Rota não encontrada'})

    def _route_put(self, p, body, s):
        data = self._parse_json(body)

        if re.fullmatch(r'/api/entradas/[^/]+/restore', p):
            self._restore_entrada(p.split('/')[-2])
        elif re.fullmatch(r'/api/saidas/[^/]+/restore', p):
            self._restore_saida(p.split('/')[-2])
        elif re.fullmatch(r'/api/produtos/[^/]+', p):
            self._update_produto(p.split('/')[-1], data)
        elif re.fullmatch(r'/api/pedidos/[^/]+/cancelar', p):
            self._cancelar_pedido(p.split('/')[-2])
        elif re.fullmatch(r'/api/pedidos/[^/]+/itens/[^/]+/anular', p):
            self._anular_saldo_pedido_item(p.split('/')[-2])
        elif re.fullmatch(r'/api/pedidos/[^/]+', p):
            self._update_pedido(p.split('/')[-1], data)
        elif re.fullmatch(r'/api/entradas/[^/]+', p):
            self._update_entrada(p.split('/')[-1], data)
        elif p in ('/api/settings', '/api/settings/'):
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            allowed = {'backup_path', 'auto_backup_enabled', 'auto_backup_keep'}
            self._save_settings({k: v for k, v in data.items() if k in allowed})
        elif p in ('/api/settings/org', '/api/settings/org/'):
            allowed = {'orgao', 'municipio', 'cnpj_orgao', 'aut_nome', 'aut_cargo'}
            self._save_settings({k: v for k, v in data.items() if k in allowed})
        elif p in ('/api/settings/smtp', '/api/settings/smtp/'):
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            allowed = {'smtp_host', 'smtp_port', 'smtp_secure', 'smtp_require_tls',
                       'smtp_ignore_ssl', 'smtp_user', 'smtp_pass', 'smtp_from_name', 'smtp_to'}
            # _save_settings ignora valores vazios, então smtp_pass em branco preserva a senha salva
            self._save_settings({k: v for k, v in data.items() if k in allowed})
        elif p in ('/api/settings/brasao', '/api/settings/brasao/'):
            # Vazio aqui é o sinal explícito de "remover o brasão", ao contrário de
            # /api/settings/org onde um campo vazio nunca sobrescreve o valor salvo.
            dataurl = data.get('brasao_dataurl', '')
            with get_db() as conn:
                if dataurl:
                    conn.execute('INSERT OR REPLACE INTO sys_settings (key,value) VALUES (?,?)', ('brasao_dataurl', dataurl))
                else:
                    conn.execute("DELETE FROM sys_settings WHERE key='brasao_dataurl'")
            self._json(200, {'ok': True})
        elif re.fullmatch(r'/api/usuarios/[^/]+', p):
            uid = int(p.split('/')[-1])
            if not s['admin']:
                if uid != s['user_id']:
                    self._json(403, {'error': 'Acesso restrito'}); return
                data = {k: data[k] for k in ('password', 'old_password') if k in data}
            self._update_user(uid, data)
        else:
            for seg, table in CRUD_ROUTES.items():
                if re.fullmatch(rf'/api/{seg}/[^/]+', p):
                    try:
                        item = _crud_update(table, p.split('/')[-1], data)
                        self._json(200, item) if item else self._json(404, {'error': 'Não encontrado'})
                    except sqlite3.IntegrityError:
                        self._json(409, {'error': 'Já existe um registro com esses dados'})
                    return
            self._json(404, {'error': 'Rota não encontrada'})

    def _route_delete(self, p, qs, s):
        if re.fullmatch(r'/api/produtos/[^/]+', p):
            try:
                _crud_delete('produtos', p.split('/')[-1])
                self._json(200, {'ok': True})
            except sqlite3.IntegrityError:
                self._json(409, {'error': 'Não é possível excluir: produto possui lotes/movimentações'})
        elif re.fullmatch(r'/api/entradas/[^/]+', p):
            self._delete_entrada(p.split('/')[-1])
        elif re.fullmatch(r'/api/saidas/[^/]+', p):
            self._delete_saida(p.split('/')[-1])
        elif re.fullmatch(r'/api/usuarios/[^/]+', p):
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            uid = int(p.split('/')[-1])
            if uid == s['user_id']:
                self._json(400, {'error': 'Não é possível excluir o próprio usuário'}); return
            with get_db() as conn:
                conn.execute('DELETE FROM usuarios WHERE id=?', (uid,))
            self._json(200, {'ok': True})
        elif p == '/api/wipe':
            if not s['admin']: self._json(403, {'error': 'Acesso restrito'}); return
            with get_db() as conn:
                # Mesma ordem (filho antes do pai) de _BACKUP_TABLES invertida — já
                # validada para respeitar FKs — só tirando sys_settings (mantido) e
                # somando audit_global (não faz parte do backup, mas some no wipe).
                for tbl in reversed(_BACKUP_TABLES):
                    if tbl != 'sys_settings':
                        conn.execute(f'DELETE FROM {tbl}')
                conn.execute('DELETE FROM audit_global')
                _insert_audit_raw(conn, {'type': 'FACTORY_RESET', 'ts': _now(),
                                          'user_id': s['user_id'], 'user_nome': s['nome'],
                                          'label': 'Todos os dados apagados', 'detail': 'Reset de fábrica'})
            self._json(200, {'ok': True})
        else:
            for seg, table in CRUD_ROUTES.items():
                if re.fullmatch(rf'/api/{seg}/[^/]+', p):
                    try:
                        _crud_delete(table, p.split('/')[-1])
                        self._json(200, {'ok': True})
                    except sqlite3.IntegrityError:
                        self._json(409, {'error': 'Não é possível excluir: registro em uso'})
                    return
            self._json(404, {'error': 'Rota não encontrada'})

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _token(self):
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            return auth[7:]
        return parse_qs(urlparse(self.path).query).get('token', [None])[0]

    def _auth(self):
        s = get_session(self._token())
        if not s:
            self._json(401, {'error': 'Não autenticado'})
        return s

    def _user_dict(self, s):
        return {'id': s['user_id'], 'username': s['username'], 'nome': s['nome'], 'admin': bool(s['admin'])}

    def _login(self, body):
        try:
            data = json.loads(body)
            username = data.get('username', '').strip()
            password = data.get('password', '')
        except Exception:
            self._json(400, {'error': 'JSON inválido'}); return

        if _login_rate_limited(username):
            self._json(429, {'error': 'Muitas tentativas de login. Aguarde alguns minutos e tente novamente.'}); return

        with get_db() as conn:
            row = conn.execute('SELECT * FROM usuarios WHERE username=? COLLATE NOCASE AND ativo=1', (username,)).fetchone()

        if not row or not _verify_password(password, row['senha_hash']):
            _record_login_failure(username)
            self._json(401, {'error': 'Usuário ou senha incorretos'}); return

        _clear_login_failures(username)
        global _had_session, _backup_pos_sess
        _had_session = True
        _backup_pos_sess = False
        token = create_session(row['id'])
        self._json(200, {
            'token': token,
            'user': {
                'id': row['id'], 'username': row['username'], 'nome': row['nome'], 'admin': bool(row['admin']),
                'mustChangePassword': bool(row['must_change_password'])
            }
        })

    def _create_user(self, data):
        nome, username, password = (data.get('nome') or '').strip(), (data.get('username') or '').strip(), data.get('password') or ''
        if not nome or not username or not password:
            self._json(400, {'error': 'Nome, usuário e senha são obrigatórios'}); return
        if len(password) < 6:
            self._json(400, {'error': 'Senha mínima: 6 caracteres'}); return
        try:
            with get_db() as conn:
                conn.execute('INSERT INTO usuarios (username,nome,senha_hash,admin,cpf,email,cargo,matricula) VALUES (?,?,?,?,?,?,?,?)',
                             (username, nome, _hash_password(password), int(bool(data.get('admin'))),
                              (data.get('cpf') or '').strip(), (data.get('email') or '').strip(),
                              (data.get('cargo') or '').strip(), (data.get('matricula') or '').strip()))
                uid = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            self._json(201, {'id': uid, 'username': username, 'nome': nome})
        except sqlite3.IntegrityError:
            self._json(409, {'error': f'Usuário "{username}" já existe'})

    def _update_user(self, uid, data):
        with get_db() as conn:
            if not conn.execute('SELECT 1 FROM usuarios WHERE id=?', (uid,)).fetchone():
                self._json(404, {'error': 'Usuário não encontrado'}); return
            fields, params = [], []
            if 'nome' in data: fields.append('nome=?'); params.append(data['nome'])
            if 'admin' in data: fields.append('admin=?'); params.append(int(bool(data['admin'])))
            if 'ativo' in data: fields.append('ativo=?'); params.append(int(bool(data['ativo'])))
            if 'cpf' in data: fields.append('cpf=?'); params.append((data['cpf'] or '').strip())
            if 'email' in data: fields.append('email=?'); params.append((data['email'] or '').strip())
            if 'cargo' in data: fields.append('cargo=?'); params.append((data['cargo'] or '').strip())
            if 'matricula' in data: fields.append('matricula=?'); params.append((data['matricula'] or '').strip())
            if data.get('password'):
                if len(data['password']) < 6:
                    self._json(400, {'error': 'Senha mínima: 6 caracteres'}); return
                if 'old_password' in data:
                    row = conn.execute('SELECT senha_hash FROM usuarios WHERE id=?', (uid,)).fetchone()
                    if not row or not _verify_password(data['old_password'], row['senha_hash']):
                        self._json(403, {'error': 'Senha atual incorreta'}); return
                fields.append('senha_hash=?'); params.append(_hash_password(data['password']))
                fields.append('must_change_password=0')
            if fields:
                conn.execute(f'UPDATE usuarios SET {",".join(fields)} WHERE id=?', params + [uid])
        self._json(200, {'ok': True})

    def _save_settings(self, data):
        # ponytail: string vazia nunca sobrescreve um valor já salvo — evita que um
        # formulário em branco (ex.: senha SMTP não recarregada) apague a configuração
        # real ao salvar. Para limpar um campo de propósito, edite o banco direto.
        with get_db() as conn:
            for key, value in data.items():
                if value == '' or value is None:
                    continue
                conn.execute('INSERT OR REPLACE INTO sys_settings (key,value) VALUES (?,?)', (key, str(value)))
        self._json(200, {'ok': True})

    # ── Auditoria ────────────────────────────────────────────────────────────

    def _add_audit(self, data, s):
        # user_id/user_nome sempre vêm da sessão autenticada, nunca do body —
        # senão qualquer chamada poderia forjar auditoria em nome de outro usuário.
        with get_db() as conn:
            conn.execute(
                '''INSERT INTO audit_global (id,ts,user_id,user_nome,type,label,detail,process_id)
                   VALUES (?,?,?,?,?,?,?,?)''',
                (str(uuid.uuid4()), _now(), s['user_id'], s['nome'],
                 data.get('type'), data.get('type'), data.get('detail'), data.get('processId'))
            )
        self._json(200, {'ok': True})

    def _list_audit(self, qs):
        def qp(k, d=None):
            v = qs.get(k)
            return v[0] if v else d
        page = int(qp('page', 1)); per = min(int(qp('per', 50)), 2000)
        q, tipo, de, ate = (qp('q') or '').strip(), qp('tipo') or '', qp('de') or '', qp('ate') or ''
        process_id = qp('processId') or qp('process_id') or ''
        where, params = [], []
        if q:    where.append('(user_nome LIKE ? OR detail LIKE ?)'); params += [f'%{q}%', f'%{q}%']
        if tipo: where.append('type=?'); params.append(tipo)
        if de:   where.append('ts >= ?'); params.append(de)
        if ate:  where.append('ts <= ?'); params.append(ate + 'T23:59:59')
        if process_id: where.append('process_id=?'); params.append(process_id)
        w = ('WHERE ' + ' AND '.join(where)) if where else ''
        with get_db() as conn:
            total = conn.execute(f'SELECT COUNT(*) FROM audit_global {w}', params).fetchone()[0]
            rows = conn.execute(
                f'SELECT * FROM audit_global {w} ORDER BY ts DESC LIMIT ? OFFSET ?',
                params + [per, (page - 1) * per]
            ).fetchall()
        self._json(200, {'total': total, 'page': page, 'per': per, 'items': [dict(r) for r in rows]})

    # ── Produtos / Estoque ───────────────────────────────────────────────────

    def _list_produtos(self, qs):
        q = (qs.get('q', [''])[0] or '').strip()
        somente_ativos = qs.get('somente_ativos', ['0'])[0] == '1'
        where, params = [], []
        if q:
            where.append('(p.nome LIKE ? OR p.codigo_fiorilli LIKE ?)')
            params += [f'%{q}%', f'%{q}%']
        if somente_ativos:
            where.append('p.ativo=1')
        w = ('WHERE ' + ' AND '.join(where)) if where else ''
        with get_db() as conn:
            rows = conn.execute(f'''
                SELECT p.*, c.nome AS centro_custo_nome,
                       COALESCE(v.estoque_fisico,0) AS estoque_fisico,
                       COALESCE(v.estoque_financeiro,0) AS estoque_financeiro,
                       v.proxima_validade
                FROM produtos p
                LEFT JOIN centros_custo c ON c.id=p.centro_custo_id
                LEFT JOIN v_estoque v ON v.produto_id=p.id
                {w} ORDER BY p.nome ASC
            ''', params).fetchall()
        self._json(200, {'items': [dict(r) for r in rows]})

    def _get_produto(self, pid):
        with get_db() as conn:
            row = conn.execute('''
                SELECT p.*, c.nome AS centro_custo_nome,
                       COALESCE(v.estoque_fisico,0) AS estoque_fisico,
                       COALESCE(v.estoque_financeiro,0) AS estoque_financeiro,
                       v.proxima_validade
                FROM produtos p
                LEFT JOIN centros_custo c ON c.id=p.centro_custo_id
                LEFT JOIN v_estoque v ON v.produto_id=p.id
                WHERE p.id=?
            ''', (pid,)).fetchone()
        self._json(200, dict(row)) if row else self._json(404, {'error': 'Produto não encontrado'})

    def _list_lotes(self, pid):
        with get_db() as conn:
            rows = conn.execute('''
                SELECT * FROM lotes WHERE produto_id=? AND quantidade_atual > 0
                ORDER BY (data_validade IS NULL) ASC, data_validade ASC, id ASC
            ''', (pid,)).fetchall()
        self._json(200, {'items': [dict(r) for r in rows]})

    def _create_produto(self, data):
        try:
            _require(data, 'codigo_fiorilli', 'nome')
        except ValueError as e:
            self._json(400, {'error': str(e)}); return
        pid = str(uuid.uuid4())
        qtd_emb = int(data.get('qtd_por_embalagem') or 1)
        saldo_inicial = int(data['saldo_inicial']) if data.get('saldo_inicial') else 0
        valor_inicial = _float(data.get('valor_unitario_inicial')) or 0
        try:
            with get_db() as conn:
                conn.execute('''INSERT INTO produtos
                    (id,codigo_fiorilli,nome,centro_custo_id,unidade_licitada,qtd_por_embalagem,
                     unidade_consumo,situacao_licitacao,codigo_licitacao,objeto_licitacao,ativo)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                    (pid, data['codigo_fiorilli'].strip(), data['nome'].strip(), data.get('centro_custo_id'),
                     data.get('unidade_licitada'), qtd_emb, data.get('unidade_consumo') or 'UN',
                     data.get('situacao_licitacao'), data.get('codigo_licitacao'), data.get('objeto_licitacao'),
                     int(bool(data.get('ativo', True)))))
                if saldo_inicial > 0:
                    conn.execute('''INSERT INTO lotes
                        (produto_id,lote_numero,data_validade,quantidade_recebida,quantidade_atual,valor_unitario_custo,entrada_item_id)
                        VALUES (?,?,?,?,?,?,NULL)''',
                        (pid, 'SALDO INICIAL', None, saldo_inicial, saldo_inicial, valor_inicial))
        except sqlite3.IntegrityError:
            self._json(409, {'error': f"Já existe produto com código Fiorilli \"{data['codigo_fiorilli']}\""}); return
        with get_db() as conn:
            row = conn.execute('SELECT * FROM produtos WHERE id=?', (pid,)).fetchone()
        self._json(201, dict(row))

    def _update_produto(self, pid, data):
        cols = ['nome', 'centro_custo_id', 'unidade_licitada', 'qtd_por_embalagem', 'unidade_consumo',
                'situacao_licitacao', 'codigo_licitacao', 'objeto_licitacao', 'ativo', 'codigo_fiorilli']
        fields = {k: data[k] for k in cols if k in data}
        if 'ativo' in fields:
            fields['ativo'] = int(bool(fields['ativo']))
        try:
            with get_db() as conn:
                if fields:
                    fields['updated_at'] = _now()
                    conn.execute(f'UPDATE produtos SET {",".join(f"{k}=?" for k in fields)} WHERE id=?',
                                 list(fields.values()) + [pid])
                row = conn.execute('SELECT * FROM produtos WHERE id=?', (pid,)).fetchone()
        except sqlite3.IntegrityError:
            self._json(409, {'error': 'Código Fiorilli já usado por outro produto'}); return
        self._json(200, dict(row)) if row else self._json(404, {'error': 'Produto não encontrado'})

    def _alertas_validade(self, qs):
        dias = int((qs.get('dias', ['30'])[0]) or 30)
        self._json(200, {'items': _lotes_vencendo(dias), 'dias': dias})

    # ── Pedidos ──────────────────────────────────────────────────────────────
    # Fora do motor CRUD genérico (CRUD_TABLES/_crud_*) porque tem itens — o
    # motor só sabe renderizar/gravar campos escalares (ver openCrudModal/
    # saveCrudModal no SGEA.html).

    def _list_pedidos(self, qs):
        q = (qs.get('q', [''])[0] or '').strip()
        where, params = [], []
        if q:
            where.append('(numero LIKE ? OR codigo_licitacao LIKE ?)')
            params += [f'%{q}%', f'%{q}%']
        w = ('WHERE ' + ' AND '.join(where)) if where else ''
        with get_db() as conn:
            rows = conn.execute(f'''
                SELECT pe.*, f.razao_social AS fornecedor_nome
                FROM pedidos pe LEFT JOIN fornecedores f ON f.id=pe.fornecedor_id
                {w} ORDER BY pe.created_at DESC''', params).fetchall()
            items = []
            for r in rows:
                d = dict(r)
                itens = _pedido_itens_com_saldo(conn, d['id'])
                d['status'] = _pedido_status_agregado(d['status'], itens)
                items.append(d)
        self._json(200, {'items': items})

    def _get_pedido_dict(self, pid):
        with get_db() as conn:
            pe = conn.execute('''
                SELECT pe.*, f.razao_social AS fornecedor_nome
                FROM pedidos pe LEFT JOIN fornecedores f ON f.id=pe.fornecedor_id
                WHERE pe.id=?''', (pid,)).fetchone()
            if not pe:
                return None
            itens = _pedido_itens_com_saldo(conn, pid)
        result = dict(pe)
        result['itens'] = itens
        result['status'] = _pedido_status_agregado(result['status'], itens)
        return result

    def _create_pedido(self, data):
        try:
            _require(data, 'numero')
        except ValueError as e:
            self._json(400, {'error': str(e)}); return
        itens = data.get('itens') or []
        if not itens:
            self._json(400, {'error': 'Informe ao menos um item'}); return

        pid = str(uuid.uuid4())
        try:
            with get_db() as conn:
                conn.execute('''INSERT INTO pedidos
                    (id,numero,codigo_licitacao,data_pedido,fornecedor_id,status)
                    VALUES (?,?,?,?,?,'aberto')''',
                    (pid, data['numero'], data.get('codigo_licitacao'), data.get('data_pedido'),
                     data.get('fornecedor_id')))
                for it in itens:
                    pid_prod = it.get('produto_id')
                    qtd = int(it.get('quantidade_pedida') or 0)
                    if not pid_prod or qtd <= 0:
                        raise ValueError('Item inválido: produto e quantidade pedida são obrigatórios')
                    conn.execute('''INSERT INTO pedido_itens (pedido_id,produto_id,quantidade_pedida)
                        VALUES (?,?,?)''', (pid, pid_prod, qtd))
        except ValueError as e:
            self._json(400, {'error': str(e)}); return
        except sqlite3.IntegrityError:
            self._json(409, {'error': 'Já existe um pedido com esse número/licitação, ou item duplicado'}); return
        self._json(201, self._get_pedido_dict(pid))

    def _update_pedido(self, pid, data):
        # Só cabeçalho — itens são imutáveis após criação (o saldo de outras
        # entradas já pode depender da quantidade_pedida original) e status
        # não é mais editável aqui, só via _cancelar_pedido.
        cols = ['numero', 'codigo_licitacao', 'data_pedido', 'fornecedor_id']
        fields = {k: data[k] for k in cols if k in data}
        with get_db() as conn:
            row = conn.execute('SELECT id FROM pedidos WHERE id=?', (pid,)).fetchone()
            if not row:
                self._json(404, {'error': 'Não encontrado'}); return
            if fields:
                fields['updated_at'] = _now()
                conn.execute(f'UPDATE pedidos SET {",".join(f"{k}=?" for k in fields)} WHERE id=?',
                             list(fields.values()) + [pid])
        self._json(200, self._get_pedido_dict(pid))

    def _anular_saldo_pedido_item(self, item_id):
        with get_db() as conn:
            item = conn.execute('SELECT * FROM pedido_itens WHERE id=?', (item_id,)).fetchone()
            if not item:
                self._json(404, {'error': 'Item de pedido não encontrado'}); return
            itens = _pedido_itens_com_saldo(conn, item['pedido_id'])
            alvo = next((i for i in itens if i['id'] == int(item_id)), None)
            if not alvo or alvo['saldo'] <= 0:
                self._json(409, {'error': 'Este item não tem saldo remanescente para anular'}); return
            conn.execute('UPDATE pedido_itens SET quantidade_anulada = quantidade_anulada + ? WHERE id=?',
                         (alvo['saldo'], item_id))
        self._json(200, self._get_pedido_dict(item['pedido_id']))

    def _cancelar_pedido(self, pid):
        with get_db() as conn:
            row = conn.execute('SELECT * FROM pedidos WHERE id=?', (pid,)).fetchone()
            if not row:
                self._json(404, {'error': 'Não encontrado'}); return
            itens = _pedido_itens_com_saldo(conn, pid)
            status_atual = _pedido_status_agregado(row['status'], itens)
            if status_atual in ('atendido', 'cancelado'):
                self._json(409, {'error': f'Pedido já está {status_atual}, não há o que cancelar'}); return
            for it in itens:
                if it['saldo'] > 0:
                    conn.execute('UPDATE pedido_itens SET quantidade_anulada = quantidade_anulada + ? WHERE id=?',
                                 (it['saldo'], it['id']))
            conn.execute("UPDATE pedidos SET status='cancelado', updated_at=? WHERE id=?", (_now(), pid))
        self._json(200, self._get_pedido_dict(pid))

    # ── Entradas ─────────────────────────────────────────────────────────────

    def _list_entradas(self, trash=False):
        cmp = 'IS NOT NULL' if trash else 'IS NULL'
        order = 'e.deleted_at DESC' if trash else 'e.data_entrega DESC, e.created_at DESC'
        with get_db() as conn:
            rows = conn.execute(f'''
                SELECT e.*, f.razao_social AS fornecedor_nome, pe.numero AS pedido_numero,
                       c.nome AS centro_custo_nome, fu.nome AS recebedor_nome
                FROM entradas e
                LEFT JOIN fornecedores f ON f.id=e.fornecedor_id
                LEFT JOIN pedidos pe ON pe.id=e.pedido_id
                LEFT JOIN centros_custo c ON c.id=e.centro_custo_id
                LEFT JOIN funcionarios fu ON fu.id=e.recebedor_id
                WHERE e.deleted_at {cmp}
                ORDER BY {order}
            ''').fetchall()
        self._json(200, {'items': [dict(r) for r in rows]})

    def _get_entrada_dict(self, eid):
        with get_db() as conn:
            e = conn.execute('''
                SELECT e.*, f.razao_social AS fornecedor_nome, pe.numero AS pedido_numero,
                       c.nome AS centro_custo_nome, fu.nome AS recebedor_nome
                FROM entradas e
                LEFT JOIN fornecedores f ON f.id=e.fornecedor_id
                LEFT JOIN pedidos pe ON pe.id=e.pedido_id
                LEFT JOIN centros_custo c ON c.id=e.centro_custo_id
                LEFT JOIN funcionarios fu ON fu.id=e.recebedor_id
                WHERE e.id=?''', (eid,)).fetchone()
            if not e:
                return None
            itens = conn.execute('''
                SELECT ei.*, p.nome AS produto_nome, p.unidade_consumo
                FROM entrada_itens ei JOIN produtos p ON p.id=ei.produto_id
                WHERE ei.entrada_id=?''', (eid,)).fetchall()
        result = dict(e)
        result['itens'] = [dict(i) for i in itens]
        return result

    def _create_entrada(self, data, s):
        tipo = data.get('tipo') or ('pedido' if data.get('pedido_id') else 'compra_direta')
        if tipo not in ('pedido', 'compra_direta'):
            self._json(400, {'error': 'Tipo inválido'}); return
        itens = data.get('itens') or []
        if not itens:
            self._json(400, {'error': 'Informe ao menos um item'}); return
        try:
            _require(data, 'data_entrega')
        except ValueError as e:
            self._json(400, {'error': str(e)}); return

        eid = str(uuid.uuid4())
        pedido_id = data.get('pedido_id') if tipo == 'pedido' else None
        try:
            with get_db() as conn:
                # 1ª passada: resolve quantidade_unidades de cada item (conversão
                # embalagem→unidade incluída) antes de inserir qualquer coisa —
                # precisamos do total por produto pra validar contra o saldo do
                # pedido (passo seguinte) sem já ter gravado nada.
                resolvidos = []
                for it in itens:
                    pid = it.get('produto_id')
                    if not pid:
                        raise ValueError('Item sem produto_id')
                    produto = conn.execute('SELECT qtd_por_embalagem FROM produtos WHERE id=?', (pid,)).fetchone()
                    if not produto:
                        raise ValueError(f'Produto {pid} não encontrado')
                    qtd_emb = _float(it.get('quantidade_embalagem'))
                    qtd_un = it.get('quantidade_unidades')
                    if qtd_un is None:
                        if qtd_emb is None:
                            raise ValueError('Informe quantidade_embalagem ou quantidade_unidades')
                        qtd_un = round(qtd_emb * produto['qtd_por_embalagem'])
                    qtd_un = int(qtd_un)
                    if qtd_un <= 0:
                        raise ValueError('Quantidade deve ser maior que zero')
                    valor_unit = _float(it.get('valor_unitario')) or 0
                    resolvidos.append({
                        'produto_id': pid, 'qtd_emb': qtd_emb, 'qtd_un': qtd_un, 'valor_unit': valor_unit,
                        'lote_numero': it.get('lote_numero'), 'data_validade': it.get('data_validade'),
                    })

                if pedido_id:
                    agregado = {}
                    for r in resolvidos:
                        agregado[r['produto_id']] = agregado.get(r['produto_id'], 0) + r['qtd_un']
                    pedido_itens = {i['produto_id']: i for i in _pedido_itens_com_saldo(conn, pedido_id)}
                    for produto_id, qtd_solicitada in agregado.items():
                        pi = pedido_itens.get(produto_id)
                        if not pi:
                            raise SaldoPedidoExcedido(f'Produto {produto_id} não faz parte deste pedido')
                        if qtd_solicitada > pi['saldo']:
                            raise SaldoPedidoExcedido(
                                f'Quantidade solicitada ({qtd_solicitada}) excede o saldo do pedido '
                                f'para {pi["produto_nome"]} (saldo: {pi["saldo"]})')

                conn.execute('''INSERT INTO entradas
                    (id,pedido_id,tipo,fornecedor_id,nfe_numero,nfe_chave_acesso,data_entrega,
                     recebedor_id,centro_custo_id,observacao,created_by)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                    (eid, data.get('pedido_id'), tipo, data.get('fornecedor_id'), data.get('nfe_numero'),
                     data.get('nfe_chave_acesso'), data['data_entrega'], data.get('recebedor_id'),
                     data.get('centro_custo_id'), data.get('observacao'), s['user_id']))
                for r in resolvidos:
                    valor_total = round(r['valor_unit'] * r['qtd_un'], 2)
                    cur = conn.execute('''INSERT INTO entrada_itens
                        (entrada_id,produto_id,quantidade_embalagem,quantidade_unidades,valor_unitario,valor_total,lote_numero,data_validade)
                        VALUES (?,?,?,?,?,?,?,?)''',
                        (eid, r['produto_id'], r['qtd_emb'], r['qtd_un'], r['valor_unit'], valor_total,
                         r['lote_numero'], r['data_validade']))
                    item_id = cur.lastrowid
                    conn.execute('''INSERT INTO lotes
                        (produto_id,lote_numero,data_validade,quantidade_recebida,quantidade_atual,valor_unitario_custo,entrada_item_id)
                        VALUES (?,?,?,?,?,?,?)''',
                        (r['produto_id'], r['lote_numero'], r['data_validade'], r['qtd_un'], r['qtd_un'],
                         r['valor_unit'], item_id))
        except SaldoPedidoExcedido as e:
            self._json(409, {'error': str(e)}); return
        except ValueError as e:
            self._json(400, {'error': str(e)}); return
        self._json(201, self._get_entrada_dict(eid))

    def _update_entrada(self, eid, data):
        # Só campos de cabeçalho — quantidades/valores já viraram lote(s) e são imutáveis.
        cols = ['nfe_numero', 'nfe_chave_acesso', 'observacao', 'recebedor_id', 'fornecedor_id', 'centro_custo_id']
        fields = {k: data[k] for k in cols if k in data}
        with get_db() as conn:
            row = conn.execute('SELECT id FROM entradas WHERE id=? AND deleted_at IS NULL', (eid,)).fetchone()
            if not row:
                self._json(404, {'error': 'Não encontrada'}); return
            if fields:
                fields['updated_at'] = _now()
                conn.execute(f'UPDATE entradas SET {",".join(f"{k}=?" for k in fields)} WHERE id=?',
                             list(fields.values()) + [eid])
        self._json(200, self._get_entrada_dict(eid))

    def _delete_entrada(self, eid):
        with get_db() as conn:
            row = conn.execute('SELECT id FROM entradas WHERE id=? AND deleted_at IS NULL', (eid,)).fetchone()
            if not row:
                self._json(404, {'error': 'Não encontrada'}); return
            consumido = conn.execute('''
                SELECT COUNT(*) FROM lotes l JOIN entrada_itens ei ON ei.id=l.entrada_item_id
                WHERE ei.entrada_id=? AND l.quantidade_atual < l.quantidade_recebida
            ''', (eid,)).fetchone()[0]
            if consumido:
                self._json(409, {'error': 'Não é possível excluir: já há saída consumindo lote(s) desta entrada'}); return
            # O bloqueio acima garante que, neste ponto, todo lote desta entrada
            # está intacto (quantidade_atual == quantidade_recebida) — zera para
            # que o estoque reflita de fato a exclusão, não só some da listagem.
            conn.execute('''
                UPDATE lotes SET quantidade_atual = 0
                WHERE entrada_item_id IN (SELECT id FROM entrada_itens WHERE entrada_id=?)
            ''', (eid,))
            conn.execute('UPDATE entradas SET deleted_at=? WHERE id=?', (_now(), eid))
        self._json(200, {'ok': True})

    def _restore_entrada(self, eid):
        with get_db() as conn:
            row = conn.execute('SELECT id FROM entradas WHERE id=? AND deleted_at IS NOT NULL', (eid,)).fetchone()
            if not row:
                self._json(404, {'error': 'Não encontrada na lixeira'}); return
            conn.execute('''
                UPDATE lotes SET quantidade_atual = quantidade_recebida
                WHERE entrada_item_id IN (SELECT id FROM entrada_itens WHERE entrada_id=?)
            ''', (eid,))
            conn.execute('UPDATE entradas SET deleted_at=NULL WHERE id=?', (eid,))
        self._json(200, self._get_entrada_dict(eid))

    # ── Saídas ───────────────────────────────────────────────────────────────

    def _list_saidas(self, trash=False):
        cmp = 'IS NOT NULL' if trash else 'IS NULL'
        order = 'sa.deleted_at DESC' if trash else 'sa.data DESC, sa.created_at DESC'
        with get_db() as conn:
            rows = conn.execute(f'''
                SELECT sa.*, c.nome AS centro_custo_nome, fr.numero AS frota_numero
                FROM saidas sa
                LEFT JOIN centros_custo c ON c.id=sa.centro_custo_id
                LEFT JOIN frota fr ON fr.id=sa.frota_id
                WHERE sa.deleted_at {cmp}
                ORDER BY {order}
            ''').fetchall()
        self._json(200, {'items': [dict(r) for r in rows]})

    def _get_saida_dict(self, sid):
        with get_db() as conn:
            sa = conn.execute('''
                SELECT sa.*, c.nome AS centro_custo_nome, fr.numero AS frota_numero
                FROM saidas sa
                LEFT JOIN centros_custo c ON c.id=sa.centro_custo_id
                LEFT JOIN frota fr ON fr.id=sa.frota_id
                WHERE sa.id=?''', (sid,)).fetchone()
            if not sa:
                return None
            itens = conn.execute('''
                SELECT si.*, p.nome AS produto_nome, p.unidade_consumo
                FROM saida_itens si JOIN produtos p ON p.id=si.produto_id
                WHERE si.saida_id=?''', (sid,)).fetchall()
            item_ids = [i['id'] for i in itens]
            lotes_map = {}
            if item_ids:
                qmarks = ','.join('?' * len(item_ids))
                lrows = conn.execute(f'''
                    SELECT sil.*, l.lote_numero, l.data_validade FROM saida_item_lotes sil
                    JOIN lotes l ON l.id=sil.lote_id
                    WHERE sil.saida_item_id IN ({qmarks})''', item_ids).fetchall()
                for lr in lrows:
                    lotes_map.setdefault(lr['saida_item_id'], []).append(dict(lr))
        result = dict(sa)
        result['itens'] = []
        for i in itens:
            d = dict(i)
            d['lotes'] = lotes_map.get(i['id'], [])
            result['itens'].append(d)
        return result

    def _create_saida(self, data, s):
        itens = data.get('itens') or []
        if not itens:
            self._json(400, {'error': 'Informe ao menos um item'}); return
        try:
            _require(data, 'data')
        except ValueError as e:
            self._json(400, {'error': str(e)}); return

        sid = str(uuid.uuid4())
        try:
            with get_db() as conn:
                conn.execute('''INSERT INTO saidas
                    (id,data,solicitante_id,solicitante_nome,solicitante_cargo,centro_custo_id,frota_id,
                     numero_solicitacao,observacao,created_by)
                    VALUES (?,?,?,?,?,?,?,?,?,?)''',
                    (sid, data['data'], data.get('solicitante_id'), data.get('solicitante_nome'),
                     data.get('solicitante_cargo'), data.get('centro_custo_id'), data.get('frota_id'),
                     data.get('numero_solicitacao'), data.get('observacao'), s['user_id']))
                for it in itens:
                    pid = it.get('produto_id')
                    qtd = int(it.get('quantidade') or 0)
                    if not pid or qtd <= 0:
                        raise ValueError('Item inválido: produto e quantidade são obrigatórios')
                    consumos, valor_medio, valor_total = _consumir_fefo(conn, pid, qtd)
                    cur = conn.execute('''INSERT INTO saida_itens
                        (saida_id,produto_id,quantidade,valor_unitario_medio,valor_total)
                        VALUES (?,?,?,?,?)''', (sid, pid, qtd, valor_medio, valor_total))
                    item_id = cur.lastrowid
                    for lote_id, qtd_consumida, custo in consumos:
                        conn.execute('''INSERT INTO saida_item_lotes
                            (saida_item_id,lote_id,quantidade,valor_unitario_custo)
                            VALUES (?,?,?,?)''', (item_id, lote_id, qtd_consumida, custo))
        except EstoqueInsuficiente as e:
            self._json(409, {'error': str(e)}); return
        except ValueError as e:
            self._json(400, {'error': str(e)}); return
        self._json(201, self._get_saida_dict(sid))

    def _delete_saida(self, sid):
        with get_db() as conn:
            row = conn.execute('SELECT id FROM saidas WHERE id=? AND deleted_at IS NULL', (sid,)).fetchone()
            if not row:
                self._json(404, {'error': 'Não encontrada'}); return
            rows = conn.execute('''
                SELECT sil.lote_id, sil.quantidade FROM saida_item_lotes sil
                JOIN saida_itens si ON si.id=sil.saida_item_id
                WHERE si.saida_id=?''', (sid,)).fetchall()
            for r in rows:
                conn.execute('UPDATE lotes SET quantidade_atual = quantidade_atual + ? WHERE id=?',
                             (r['quantidade'], r['lote_id']))
            conn.execute('UPDATE saidas SET deleted_at=? WHERE id=?', (_now(), sid))
        self._json(200, {'ok': True})

    def _restore_saida(self, sid):
        # ponytail: restaurar reconsome via FEFO no momento da restauração, em vez
        # de tentar "desfazer o desfazer" com os lotes exatos de origem — mais simples,
        # e o efeito no estoque final é idêntico; só a composição por lote pode diferir
        # se o saldo mudou nesse meio-tempo (aceitável: é uma saída nova em espírito).
        try:
            with get_db() as conn:
                row = conn.execute('SELECT id FROM saidas WHERE id=? AND deleted_at IS NOT NULL', (sid,)).fetchone()
                if not row:
                    self._json(404, {'error': 'Não encontrada na lixeira'}); return
                itens = conn.execute('SELECT id, produto_id, quantidade FROM saida_itens WHERE saida_id=?', (sid,)).fetchall()
                for it in itens:
                    conn.execute('DELETE FROM saida_item_lotes WHERE saida_item_id=?', (it['id'],))
                    consumos, valor_medio, valor_total = _consumir_fefo(conn, it['produto_id'], it['quantidade'])
                    conn.execute('UPDATE saida_itens SET valor_unitario_medio=?, valor_total=? WHERE id=?',
                                 (valor_medio, valor_total, it['id']))
                    for lote_id, qtd_consumida, custo in consumos:
                        conn.execute('''INSERT INTO saida_item_lotes
                            (saida_item_id,lote_id,quantidade,valor_unitario_custo)
                            VALUES (?,?,?,?)''', (it['id'], lote_id, qtd_consumida, custo))
                conn.execute('UPDATE saidas SET deleted_at=NULL WHERE id=?', (sid,))
        except EstoqueInsuficiente as e:
            self._json(409, {'error': f'Não é possível restaurar: {e}'}); return
        self._json(200, self._get_saida_dict(sid))

    # ── Proxy CNPJ ───────────────────────────────────────────────────────────

    def _proxy_cnpj(self, digits):
        if not digits.isdigit() or len(digits) != 14:
            self._json(400, {'status': 'ERROR', 'message': 'CNPJ inválido'}); return
        url = f'https://receitaws.com.br/v1/cnpj/{digits}'
        req = urllib.request.Request(url, headers={'User-Agent': 'SGEA/1.0'})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read()
                self.send_response(resp.status); self._cors()
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
        except urllib.error.HTTPError as e:
            body = e.read()
            self.send_response(e.code); self._cors()
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers(); self.wfile.write(body)
        except Exception as e:
            self._json(502, {'status': 'ERROR', 'message': str(e)})

    # ── E-mail ───────────────────────────────────────────────────────────────

    def _send_email(self, data):
        # Autenticado (não precisa admin) — usado tanto pelo "Testar conexão"
        # da aba Comunicação quanto por qualquer envio futuro no app.
        try:
            _send_email_raw(data['smtp'], data['from'], data['to'], data['subject'], data['html'], data.get('text', ''))
            self._json(200, {'ok': True})
        except Exception as e:
            self._json(500, {'ok': False, 'error': str(e)})

    # ── Backup ───────────────────────────────────────────────────────────────

    def _export_backup(self):
        payload = _build_backup_payload()
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        name = time.strftime('SIS_SGEA_BACKUP_%Y-%m-%d_%H-%M-%S.json')
        self.send_response(200); self._cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Content-Disposition', f'attachment; filename="{name}"')
        self.end_headers(); self.wfile.write(body)

    def _export_db_backup(self):
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmp.close()
        try:
            with sqlite3.connect(DB_PATH, factory=_ConnAutoClose) as src, \
                 sqlite3.connect(tmp.name, factory=_ConnAutoClose) as bk:
                src.backup(bk)
            with open(tmp.name, 'rb') as f:
                data_bytes = f.read()
            name = time.strftime('DB_SGEA_BACKUP_%Y-%m-%d_%H-%M-%S.db')
            self.send_response(200); self._cors()
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(data_bytes)))
            self.send_header('Content-Disposition', f'attachment; filename="{name}"')
            self.end_headers(); self.wfile.write(data_bytes)
        finally:
            try: os.remove(tmp.name)
            except Exception: pass

    def _list_db_backups(self):
        cfg = _get_backup_cfg()
        bdir = cfg['path']
        files = sorted(
            (f for f in os.listdir(bdir) if f.startswith('DB_SGEA_BACKUP_') and f.endswith('.db')), reverse=True
        ) if os.path.isdir(bdir) else []
        def _parse_ts(f):
            d = f[15:25]; t = f[26:34].replace('-', ':')
            return f'{d}T{t}'
        items = [{'name': f, 'size': os.path.getsize(os.path.join(bdir, f)), 'ts': _parse_ts(f)} for f in files]
        with get_db() as conn:
            last_row = conn.execute("SELECT value FROM sys_settings WHERE key='auto_backup_last'").fetchone()
        self._json(200, {'items': items, 'path': bdir, 'cfg': cfg, 'last_backup': last_row['value'] if last_row else None})

    def _download_db_backup(self, name):
        if not name or not name.startswith('DB_SGEA_BACKUP_') or not name.endswith('.db') or '/' in name or '\\' in name:
            self._json(400, {'error': 'Nome inválido'}); return
        cfg = _get_backup_cfg()
        fp = os.path.join(cfg['path'], name)
        if not os.path.exists(fp):
            self._json(404, {'error': 'Arquivo não encontrado'}); return
        with open(fp, 'rb') as f:
            data_bytes = f.read()
        self.send_response(200); self._cors()
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(len(data_bytes)))
        self.send_header('Content-Disposition', f'attachment; filename="{name}"')
        self.end_headers(); self.wfile.write(data_bytes)

    def _dialog_folder(self):
        global _watchdog_paused
        _watchdog_paused = True
        try:
            ps_cmd = (
                'Add-Type -AssemblyName System.Windows.Forms;'
                '$d=New-Object System.Windows.Forms.FolderBrowserDialog;'
                '$d.Description="Selecione a pasta de backup do SGEA";'
                '$d.ShowNewFolderButton=$true;'
                'if($d.ShowDialog()-eq"OK"){Write-Output $d.SelectedPath}'
            )
            r = subprocess.run(['powershell', '-Sta', '-WindowStyle', 'Hidden', '-Command', ps_cmd],
                                capture_output=True, text=True, timeout=120)
            path = r.stdout.strip()
            self._json(200, {'path': path or None})
        except Exception as e:
            self._json(500, {'error': str(e)})
        finally:
            _watchdog_paused = False

    def _restore_backup(self, data, s):
        if not data.get('_sgea'):
            self._json(400, {'error': 'Arquivo não é um backup SGEA válido'}); return
        _do_db_backup()  # segurança antes de substituir tudo
        try:
            with get_db() as conn:
                for t in reversed(_BACKUP_TABLES):
                    conn.execute(f'DELETE FROM {t}')
                for t in _BACKUP_TABLES:
                    for row in (data.get(t) or []):
                        cols = list(row.keys())
                        conn.execute(f'INSERT INTO {t} ({",".join(cols)}) VALUES ({",".join("?" * len(cols))})',
                                     [row[c] for c in cols])
                _insert_audit_raw(conn, {'type': 'RESTAURAR_BACKUP', 'ts': _now(),
                                          'user_id': s['user_id'], 'user_nome': s['nome'],
                                          'label': 'Backup do sistema restaurado', 'detail': 'Restauração via arquivo JSON'})
        except Exception as e:
            _log.error('Erro ao restaurar backup JSON: %s', e)
            self._json(500, {'error': f'Falha ao restaurar: {e}'}); return
        self._json(200, {'ok': True})

    def _restore_db_backup(self, raw_bytes, s):
        if len(raw_bytes) < 16 or raw_bytes[:16] != b'SQLite format 3\x00':
            self._json(400, {'error': 'Arquivo não é um banco SQLite válido'}); return
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        try:
            tmp.write(raw_bytes); tmp.close()
            with sqlite3.connect(tmp.name, factory=_ConnAutoClose) as test_conn:
                tables = {r[0] for r in test_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            required = {'produtos', 'lotes', 'entradas', 'saidas', 'sys_settings'}
            if not required.issubset(tables):
                self._json(400, {'error': 'Banco inválido: tabelas obrigatórias ausentes'}); return
            _do_db_backup()
            with sqlite3.connect(tmp.name, factory=_ConnAutoClose) as src, get_db() as dst:
                src.backup(dst)
                # Registrado na conexão já restaurada — o backup() acima substitui todo o
                # banco, então logar antes seria sobrescrito pelo conteúdo do arquivo restaurado.
                _insert_audit_raw(dst, {'type': 'RESTAURAR_DB', 'ts': _now(),
                                         'user_id': s['user_id'], 'user_nome': s['nome'],
                                         'label': 'Banco de dados restaurado', 'detail': 'Restauração via arquivo .db'})
            self._json(200, {'ok': True})
        except Exception as e:
            _log.error('Erro ao restaurar banco: %s', e)
            self._json(500, {'error': str(e)})
        finally:
            try: os.remove(tmp.name)
            except Exception: pass

    def _relatorio_integridade(self):
        cfg = _get_backup_cfg()
        bdir = cfg['path']
        backups_db = sorted(
            (f for f in os.listdir(bdir) if f.startswith('DB_SGEA_BACKUP_') and f.endswith('.db')),
            reverse=True
        ) if os.path.isdir(bdir) else []
        backups_json = sorted(
            (f for f in os.listdir(bdir) if f.startswith('SIS_SGEA_BACKUP_') and f.endswith('.json')),
            reverse=True
        ) if os.path.isdir(bdir) else []

        with get_db() as conn:
            cadastros_apoio = sum(conn.execute(f'SELECT COUNT(*) FROM {t} WHERE ativo=1').fetchone()[0]
                                   for t in ('centros_custo', 'fornecedores', 'funcionarios', 'frota'))
            contagens = {
                'produtos_ativos': conn.execute('SELECT COUNT(*) FROM produtos WHERE ativo=1').fetchone()[0],
                'entradas_ativas': conn.execute('SELECT COUNT(*) FROM entradas WHERE deleted_at IS NULL').fetchone()[0],
                'saidas_ativas': conn.execute('SELECT COUNT(*) FROM saidas WHERE deleted_at IS NULL').fetchone()[0],
                'lotes': conn.execute('SELECT COUNT(*) FROM lotes').fetchone()[0],
                'usuarios_ativos': conn.execute('SELECT COUNT(*) FROM usuarios WHERE ativo=1').fetchone()[0],
                'cadastros_apoio': cadastros_apoio,
            }
            eventos = [dict(r) for r in conn.execute(
                '''SELECT * FROM audit_global WHERE type IN
                   ('RESTAURAR_BACKUP','RESTAURAR_DB','FACTORY_RESET')
                   ORDER BY ts DESC LIMIT 15''').fetchall()]
            last_row = conn.execute("SELECT value FROM sys_settings WHERE key='auto_backup_last'").fetchone()

        self._json(200, {
            'auto_backup_enabled': cfg['enabled'], 'auto_backup_keep': cfg['keep'], 'backup_path': bdir,
            'last_backup': last_row['value'] if last_row else None,
            'db_size_bytes': os.path.getsize(DB_PATH) if os.path.isfile(DB_PATH) else 0,
            'backups_db_count': len(backups_db), 'backups_json_count': len(backups_json),
            'backups_db_size_bytes': sum(os.path.getsize(os.path.join(bdir, f)) for f in backups_db),
            'contagens': contagens, 'eventos_recentes': eventos,
        })

    # ── Helpers HTTP ─────────────────────────────────────────────────────────

    def _body(self):
        n = int(self.headers.get('Content-Length', 0))
        return self.rfile.read(n) if n else b''

    def _parse_json(self, body):
        try:
            return json.loads(body) if body else {}
        except Exception:
            return {}

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type,Authorization')

    def _json(self, status, obj):
        payload = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status); self._cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers(); self.wfile.write(payload)

    def log_message(self, fmt, *args): pass

# ── E-mail ───────────────────────────────────────────────────────────────────

_send_email_raw = sgx_base.send_email_raw

def _send_daily_alerts():
    """Resumo diário por e-mail de lotes vencidos/vencendo. Só envia se SMTP
    estiver configurado e ainda não tiver enviado hoje (chamado a cada 5s pelo
    watchdog — o dedup por data é o que garante 1x/dia, não o intervalo)."""
    with get_db() as conn:
        cfg = {r['key']: r['value'] for r in conn.execute(
            "SELECT key,value FROM sys_settings WHERE key LIKE 'smtp_%' OR key='alert_email_last_sent'"
        ).fetchall()}
    if not (cfg.get('smtp_host') and cfg.get('smtp_user') and cfg.get('smtp_pass')):
        return
    hoje = time.strftime('%Y-%m-%d')
    if cfg.get('alert_email_last_sent') == hoje:
        return

    itens = _lotes_vencendo(7)
    if not itens:
        with get_db() as conn:
            conn.execute("INSERT OR REPLACE INTO sys_settings (key,value) VALUES ('alert_email_last_sent',?)", (hoje,))
        return

    smtp_cfg = {
        'host': cfg['smtp_host'], 'port': cfg.get('smtp_port', 587),
        'secure': cfg.get('smtp_secure') == '1', 'requireTLS': cfg.get('smtp_require_tls') != '0',
        'ignoreSSL': cfg.get('smtp_ignore_ssl') == '1',
        'auth': {'user': cfg['smtp_user'], 'pass': cfg['smtp_pass']},
    }
    frm = {'name': cfg.get('smtp_from_name') or 'SGEA', 'email': cfg['smtp_user']}

    if cfg.get('smtp_to'):
        linhas = ''.join(
            f"<li><strong>{l['produto_nome']}</strong> ({l['codigo_fiorilli']}) — lote {l.get('lote_numero') or 's/nº'} "
            f"— {'vencido em' if l['vencido'] else 'vence em'} {l['data_validade']} — saldo {l['quantidade_atual']} {l['unidade_consumo']}</li>"
            for l in sorted(itens, key=lambda x: x['data_validade'])
        )
        corpo = f"<p>Resumo automático do SGEA — {hoje}</p><p>Lotes vencidos ou vencendo nos próximos 7 dias:</p><ul>{linhas}</ul>"
        try:
            _send_email_raw(smtp_cfg, frm, cfg['smtp_to'], f'SGEA — Lotes vencendo ({hoje})', corpo)
            print(f'  [ALERTAS] E-mail de validade enviado ({len(itens)} lote(s))', flush=True)
        except Exception as e:
            _log.error('Falha ao enviar e-mail de alertas: %s', e)

    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO sys_settings (key,value) VALUES ('alert_email_last_sent',?)", (hoje,))

# ── Backup automático do banco ─────────────────────────────────────────────────
# Tabelas exportadas na íntegra no backup JSON — `usuarios` fica de fora de
# propósito (mesma decisão do SGCA): senha_hash não deve viajar num export
# casual, e uma restauração não deveria conseguir clonar contas de login.
_BACKUP_TABLES = ('centros_custo', 'fornecedores', 'funcionarios', 'frota', 'produtos', 'pedidos',
                   'entradas', 'entrada_itens', 'lotes', 'saidas', 'saida_itens', 'saida_item_lotes',
                   'sys_settings')

def _build_backup_payload():
    with get_db() as conn:
        payload = {'_sgea': True, 'version': 1, 'exportedAt': _now()}
        for t in _BACKUP_TABLES:
            payload[t] = [dict(r) for r in conn.execute(f'SELECT * FROM {t}').fetchall()]
    return payload

def _do_json_backup(cfg=None):
    if cfg is None: cfg = _get_backup_cfg()
    bdir = cfg['path']
    os.makedirs(bdir, exist_ok=True)
    name = time.strftime('SIS_SGEA_BACKUP_%Y-%m-%d_%H-%M-%S.json')
    dst = os.path.join(bdir, name)
    try:
        with open(dst, 'w', encoding='utf-8') as f:
            json.dump(_build_backup_payload(), f, ensure_ascii=False)
        print(f'Backup JSON automático: {name}')
        return name
    except Exception as e:
        _log.error('Falha no backup JSON automático: %s', e)
        return None

def _rotate_backups(cfg=None):
    if cfg is None: cfg = _get_backup_cfg()
    bdir, keep = cfg['path'], cfg['keep']
    if not os.path.isdir(bdir): return
    for prefix, ext in [('DB_SGEA_BACKUP_', '.db'), ('SIS_SGEA_BACKUP_', '.json')]:
        files = sorted(f for f in os.listdir(bdir) if f.startswith(prefix) and f.endswith(ext))
        for old in (files[:-keep] if keep else files):
            fp = os.path.join(bdir, old)
            for attempt in range(6):  # tenta por até ~10s (OneDrive pode manter o arquivo aberto)
                try:
                    os.remove(fp)
                    print(f'Rotação: removido {old}')
                    break
                except PermissionError:
                    if attempt < 5: time.sleep(2)
                    else: _log.error('Falha ao remover backup %s: arquivo bloqueado (OneDrive/antivírus).', old)
                except Exception as e:
                    _log.error('Falha ao remover backup %s: %s', old, e)
                    break

def _insert_audit_raw(conn, a):
    conn.execute(
        '''INSERT INTO audit_global (id,ts,user_id,user_nome,type,label,detail,process_id)
           VALUES (?,?,?,?,?,?,?,?)''',
        (a.get('id') or str(uuid.uuid4()), a.get('ts'), a.get('user_id'), a.get('user_nome'),
         a.get('type'), a.get('label'), a.get('detail'), a.get('process_id'))
    )

def _get_backup_cfg():
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT key,value FROM sys_settings WHERE key IN ('backup_path','auto_backup_enabled','auto_backup_keep')"
            ).fetchall()
        cfg = {r['key']: r['value'] for r in rows}
    except Exception:
        cfg = {}
    try:
        keep = max(1, int(cfg.get('auto_backup_keep') or BACKUP_KEEP))
    except (TypeError, ValueError):
        keep = BACKUP_KEEP
    return {'path': cfg.get('backup_path') or BACKUP_DIR, 'enabled': cfg.get('auto_backup_enabled', '1') != '0', 'keep': keep}

def _do_db_backup(cfg=None):
    if cfg is None: cfg = _get_backup_cfg()
    bdir = cfg['path']
    os.makedirs(bdir, exist_ok=True)
    name = time.strftime('DB_SGEA_BACKUP_%Y-%m-%d_%H-%M-%S.db')
    dst = os.path.join(bdir, name)
    try:
        with sqlite3.connect(DB_PATH, factory=_ConnAutoClose) as src, sqlite3.connect(dst, factory=_ConnAutoClose) as bk:
            src.backup(bk)
        with get_db() as conn:
            conn.execute("INSERT OR REPLACE INTO sys_settings (key,value) VALUES ('auto_backup_last',?)", (_now(),))
        print(f'Backup automático: {name}')
        _rotate_backups(cfg)
        return name
    except Exception as e:
        _log.error('Falha no backup automático: %s', e)
        return None

def _purge_old_trash():
    """Apaga de vez entradas/saídas na lixeira há mais de TRASH_RETENTION_DIAS dias.
    ON DELETE CASCADE do schema cuida de entrada_itens/lotes e saida_itens/saida_item_lotes."""
    global _last_trash_purge
    _last_trash_purge = time.time()
    limite = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(time.time() - TRASH_RETENTION_DIAS * 86400))
    with get_db() as conn:
        conn.execute('DELETE FROM entradas WHERE deleted_at IS NOT NULL AND deleted_at < ?', (limite,))
        conn.execute('DELETE FROM saidas WHERE deleted_at IS NOT NULL AND deleted_at < ?', (limite,))

def _watchdog():
    # Limpa sessões expiradas a cada 5s e dispara o backup pós-sessão.
    # SESSION_TTL=60s dá folga de sobra sobre o ping a cada 5s.
    while True:
        time.sleep(5)
        if _watchdog_paused:
            continue
        sgx_base.purge_expired_sessions(get_db)
        try:
            _check_shutdown()
        except Exception as e:
            _log.error('Erro em _check_shutdown: %s', e)
        if time.time() - _last_trash_purge > 3600:
            try:
                _purge_old_trash()
            except Exception as e:
                _log.error('Erro ao purgar lixeira: %s', e)
        try:
            _send_daily_alerts()
        except Exception as e:
            _log.error('Erro ao enviar alertas por e-mail: %s', e)

# ── Inicialização ─────────────────────────────────────────────────────────────

init_db()

def _check_db_integrity():
    try:
        with get_db() as conn:
            result = conn.execute('PRAGMA integrity_check').fetchone()[0]
            if result != 'ok':
                _log.error('INTEGRITY CHECK FALHOU: %s', result)
                print(f'[AVISO] Banco de dados com problema de integridade: {result}')
            else:
                print('[DB] Integridade verificada: ok')
    except Exception as e:
        _log.error('Erro ao verificar integridade do banco: %s', e)

def _selecionar_modo():
    print()
    print('  ╔══════════════════════════════════════════════════╗')
    print('  ║   SGEA — Sistema de Gestão de Estoque do Almox.   ║')
    print('  ╚══════════════════════════════════════════════════╝')
    print()
    print('  [1] Diagnóstico     — Verifica rede, porta e firewall')
    print('  [2] Iniciar Servidor')
    print()
    if not sys.stdin.isatty():
        op = '2'
    else:
        while True:
            try:
                op = input('  Opção [1/2]: ').strip()
            except (EOFError, KeyboardInterrupt):
                op = '2'
            if op in ('1', '2'):
                break
            print('  Digite 1 ou 2.')
    if op == '1':
        import subprocess as _sp
        diag = os.path.join(_BASE, 'diagnostico.py')
        _sp.run([sys.executable, diag])
        sys.exit(0)
    print()
    print('  ─────────────────────────────────────────────────')

if __name__ == '__main__':
    _selecionar_modo()
    _check_db_integrity()
    _rotate_backups(_get_backup_cfg())

    threading.Thread(target=_watchdog, daemon=True).start()

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(('', PORT), SGEAHandler) as httpd:
        print(f'  Servidor: http://localhost:{PORT}')
        import socket as _socket
        try:
            ip_local = _socket.gethostbyname(_socket.gethostname())
        except Exception:
            ip_local = 'desconhecido'
        print(f'  Rede:     http://{ip_local}:{PORT}/SGEA.html')
        print()

        browser = _find_browser()
        if browser:
            subprocess.Popen([
                browser, f'--app=http://localhost:{PORT}/SGEA.html', '--start-maximized',
                '--disable-background-mode', f'--user-data-dir={PROFILE_DIR}',
            ])
            print('  App aberto no navegador.')
        else:
            print(f'  Chrome/Edge não encontrado. Abra manualmente: http://localhost:{PORT}/SGEA.html')

        print('  Aguardando conexões... (Ctrl+C para encerrar)')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n  Encerrando servidor...')
