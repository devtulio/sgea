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
import logging
import os
import re
import secrets
import shutil
import smtplib
import ssl
import sqlite3
import subprocess
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


# ── Dinheiro: um parser só para a família ───────────────────────────────────
# Espelha base.js/parseValorBR — as duas implementações TÊM de concordar, senão
# o valor exibido na tela e o gravado na coluna divergem. Havia três parsers com
# regras diferentes; ver o comentário lá para o histórico.
def parse_valor(v):
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r'[R$\s ]', '', str(v))
    if not s:
        return None
    negativo = s.startswith('-') or (s.startswith('(') and s.endswith(')'))
    s = re.sub(r'[()-]', '', s)
    tem_ponto, tem_virgula = '.' in s, ',' in s
    if tem_ponto and tem_virgula:
        s = (s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.')
             else s.replace(',', ''))
    elif tem_virgula:
        s = s.replace(',', '.')
    elif tem_ponto and re.fullmatch(r'\d{1,3}(\.\d{3})+', s):
        s = s.replace('.', '')          # milhar: 1.234 / 1.234.567
    try:
        n = float(re.sub(r'[^\d.]', '', s))
    except ValueError:
        return None
    return -n if negativo else n


# ── Cadastro compartilhado de fornecedores (sync peer SGCD/SGCA/SGEA) ────────────
# Mesmo schema nos três; qualquer um cadastra/edita e propaga. Chave natural =
# CNPJ (só dígitos). Merge por last-write-wins via `updatedAt`, com detecção
# precisa de conflito por marca d'água `syncedAt` (estado no último sync): só é
# conflito quando OS DOIS lados mexeram desde então — aí vai pra revisão manual.
# Compliance (ceis/cnep/sancoes) é editável só no SGCD (regra de UI); o merge
# carrega esses campos, mas os receptores não os editam. Sync nunca apaga.

# Campos congelados do fornecedor canônico — contrato entre SGCD/SGCA/SGEA.
# SGCD já grava todos; SGCA idem (mesmo JSON); SGEA guarda em coluna `data`.
# updatedAt = última edição; syncedAt = estado no último sync (controle, não conteúdo).
CAMPOS_FORNECEDOR = (
    'cnpj', 'razao_social', 'nome_fantasia',
    'situacao', 'porte', 'natureza_juridica', 'capital_social', 'opcao_simples', 'opcao_mei',
    'logradouro', 'numero', 'complemento', 'bairro', 'municipio', 'uf', 'cep', 'endereco',
    'telefone', 'telefone2', 'email', 'website',
    'ceis', 'cnep', 'sancoes', 'qsa', 'obs',
    'updatedAt', 'syncedAt',
)
# Campos de conteúdo (comparados para decidir igualdade) — tudo menos os de controle.
_CONTROLE_FORNECEDOR = ('updatedAt', 'syncedAt')
CAMPOS_CONTEUDO_FORNECEDOR = tuple(c for c in CAMPOS_FORNECEDOR if c not in _CONTROLE_FORNECEDOR)

def cnpj_digits(v):
    """CNPJ só com dígitos — chave natural estável entre os sistemas."""
    return re.sub(r'\D', '', v or '')

def ts_ms(v):
    """updatedAt/syncedAt em milissegundos comparáveis. O campo chega em dois
    formatos na família — número epoch (Date.now() no front) ou string ISO com
    ms (_now_precise no server) — e comparar str com int estoura. Normaliza os
    dois para int-ms; vazio/inválido = 0."""
    if v is None or v == '':
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v)
    try:
        import datetime
        return int(datetime.datetime.fromisoformat(s).timestamp() * 1000)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return 0

def _fornecedores_iguais(a, b, campos=CAMPOS_CONTEUDO_FORNECEDOR):
    return all((a.get(c) or '') == (b.get(c) or '') for c in campos)

def classificar_merge(existente, novo):
    """Classifica um fornecedor `novo` (do arquivo de sync) contra o `existente`
    local (ou None). Devolve:
      'novo'      -> não existe local: inserir.
      'igual'     -> mesmo conteúdo: nada a fazer (idempotente).
      'conflito'  -> os dois mexeram desde o último sync: revisão manual.
      'atualizar' -> só o de fora mudou e é mais novo: aplica.
      'ignorar'   -> o local é mais novo / o de fora não avançou: mantém local.
    Nunca devolve ação de apagar — sync só insere/atualiza."""
    if existente is None:
        return 'novo'
    if _fornecedores_iguais(existente, novo):
        return 'igual'
    synced        = ts_ms(existente.get('syncedAt'))
    local_ts      = ts_ms(existente.get('updatedAt'))
    entrada_ts    = ts_ms(novo.get('updatedAt'))
    if local_ts > synced and entrada_ts > synced:
        return 'conflito'
    if entrada_ts > local_ts:
        return 'atualizar'
    return 'ignorar'

def planejar_sync_fornecedores(locais, entrada):
    """Planeja o import de fornecedores (função pura — não toca banco). Cada
    sistema monta `locais` (dict cnpj_digits -> registro local) e passa a lista
    `entrada` (do arquivo). Devolve os baldes para o sistema executar:
      {'inserir': [...], 'atualizar': [...], 'conflitos': [{'cnpj','local','entrada'}], 'ignorados': n}
    Entrada sem CNPJ é descartada — CNPJ é a chave; sem ela não há como casar."""
    plano = {'inserir': [], 'atualizar': [], 'conflitos': [], 'ignorados': 0, 'sem_cnpj': 0}
    for novo in entrada:
        cnpj = cnpj_digits(novo.get('cnpj'))
        if not cnpj:
            plano['sem_cnpj'] += 1
            continue
        existente = locais.get(cnpj)
        acao = classificar_merge(existente, novo)
        if acao == 'novo':
            plano['inserir'].append(novo)
        elif acao == 'atualizar':
            plano['atualizar'].append(novo)
        elif acao == 'conflito':
            plano['conflitos'].append({'cnpj': cnpj, 'local': existente, 'entrada': novo})
        else:  # 'igual' ou 'ignorar'
            plano['ignorados'] += 1
    return plano


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


# Senha de fábrica (admin/admin123, publicada no README/manual). Recusada como
# NOVA senha: sem isso a troca obrigatória vira contornável — o usuário digita o
# próprio padrão, o hash bate, a marca must_change_password zera e a conta segue
# com a senha de fábrica. Ver rota_liberada_sem_trocar_senha / marcar_senha_padrao.
SENHA_PADRAO = 'admin123'

def eh_senha_padrao(senha):
    return (senha or '') == SENHA_PADRAO


# O instalador cria o admin já com must_change_password=1, mas quem instalou
# antes dessa coluna existir recebeu 0 pelo DEFAULT do ALTER TABLE: ficou com a
# senha do manual e sem o bloqueio do servidor. Em vez de corrigir banco a banco,
# o servidor confere no boot quem ainda está na senha padrão e marca a troca.
# Pega também quem voltar à senha padrão depois e quem for cadastrado com ela.
# ponytail: um PBKDF2 (100k iterações, ~60ms) por conta ainda não marcada, a cada
# boot. Com dezenas de contas, restringir a checagem ao admin.
def marcar_senha_padrao(conn, padrao='admin123', tabela='usuarios'):
    """Marca troca obrigatória para todo usuário cuja senha ainda é a padrão.
    Devolve quantos foram marcados. Idempotente: quem já está marcado é pulado."""
    try:
        pendentes = conn.execute(
            f'SELECT id, senha_hash FROM {tabela} WHERE COALESCE(must_change_password,0)=0'
        ).fetchall()
    except sqlite3.OperationalError:
        return 0   # coluna ainda não migrada neste banco
    ids = [r[0] for r in pendentes if verify_password(padrao, r[1])]
    if ids:
        marcas = ','.join('?' * len(ids))
        conn.execute(
            f'UPDATE {tabela} SET must_change_password=1 WHERE id IN ({marcas})', ids)
        conn.commit()
    return len(ids)


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


# Rotas que um usuário com troca de senha pendente ainda pode chamar: só as de
# que o próprio front precisa para exibir a tela de troca e concluí-la.
#
# A troca obrigatória era imposta apenas no navegador: quem falasse direto com a
# API entrava com a senha padrão (admin/admin123, que está no README e no manual)
# e usava o sistema inteiro, inclusive as rotas de administrador, enquanto
# ninguém tivesse trocado a senha. Agora o servidor recusa qualquer outra rota
# até a senha sair do padrão.
def rota_liberada_sem_trocar_senha(path, metodo, user_id):
    base = (path or '').split('?')[0].rstrip('/')
    if base in ('/api/auth/me', '/api/auth/ping', '/api/auth/logout', '/api/auth/senha'):
        return True
    # trocar a própria senha (PUT /api/usuarios/<eu>) — é o que a tela faz
    return metodo == 'PUT' and base == f'/api/usuarios/{user_id}'


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

# Segundos por operação de socket no envio. Generoso o bastante para anexo
# grande em link lento, curto o bastante para não segurar uma thread do servidor.
SMTP_TIMEOUT = 30


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

    # timeout OBRIGATÓRIO: sem ele o socket usa o padrão do Python (None = espera
    # para sempre). Como os servidores são ThreadingTCPServer, um SMTP que aceita
    # a conexão e não responde prendia a thread permanentemente — e isso se repete
    # a cada envio, inclusive no resumo diário automático.
    if smtp.get('secure'):
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=SMTP_TIMEOUT) as s:
            s.login(user, pw); s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT) as s:
            s.ehlo()
            if smtp.get('requireTLS', True): s.starttls(context=ctx)
            s.login(user, pw); s.send_message(msg)


# ── Captura de falhas (crash log que sobrevive ao fechamento da janela) ─────────
# Quando o servidor cai, a janela do .bat fecha e leva o traceback junto. Isto
# grava a causa num arquivo persistente, cobrindo os três jeitos de o processo
# morrer: exceção não-tratada em qualquer thread, segfault de C (ex.: SQLite sob
# concorrência) e erro fatal na thread principal do serve_forever.

def instalar_captura_de_falhas(log_dir, sigla):
    """Arma faulthandler + threading.excepthook, gravando em <log_dir>/<sigla>_crash.log.
    Chamar uma vez no início do __main__. Devolve o caminho do arquivo."""
    import faulthandler, threading, traceback, datetime
    os.makedirs(log_dir, exist_ok=True)
    caminho = os.path.join(log_dir, f'{sigla}_crash.log')
    fh = open(caminho, 'a', buffering=1, encoding='utf-8', errors='replace')
    fh.write(f'\n=== captura armada em {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===\n')
    faulthandler.enable(file=fh, all_threads=True)   # pega segfault (traceback de C-level)
    def _hook(args):
        fh.write(f'\n--- exceção não tratada em thread "{args.thread.name}" '
                 f'({datetime.datetime.now():%Y-%m-%d %H:%M:%S}) ---\n')
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=fh)
        fh.flush()
    threading.excepthook = _hook
    return caminho


# ── Servidor WSGI (waitress) — substitui o http.server frágil ────────────────
# O ThreadingTCPServer/http.server é servidor de brinquedo (a própria doc do
# Python diz "não use em produção"): abre uma thread por request sem limite e o
# loop principal morre com erro de socket, derrubando o processo (candidato nº 1
# do bug do "servidor parou"). waitress (puro-Python, vendorizado) tem pool fixo
# e loop endurecido. Os handlers seguem escritos como SimpleHTTPRequestHandler;
# este adaptador expõe a MESMA interface a partir do WSGI, então o código de
# rota/handler não muda. ponytail: resposta bufferizada (junta os wfile.write e
# devolve de uma vez) — cabe em RAM na escala municipal; virar generator só se
# precisar servir download de centenas de MB.

class _HeadersWSGI:
    """Imita http.client.HTTPMessage (só o .get que os handlers usam) a partir do environ."""
    def __init__(self, environ):
        self._e = environ
    def get(self, nome, default=None):
        chave = nome.upper().replace('-', '_')
        if chave in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            return self._e.get(chave, default)
        return self._e.get('HTTP_' + chave, default)
    def __getitem__(self, nome):
        v = self.get(nome)
        if v is None:
            raise KeyError(nome)
        return v
    def __contains__(self, nome):
        return self.get(nome) is not None


def _wsgi_app(handler_class):
    import http.client
    razao = http.client.responses

    class _Adaptador(handler_class):
        # Não chama o __init__ do BaseHTTPRequestHandler (que exige um socket).
        def __init__(self, environ):
            self.environ = environ
            self.command = environ['REQUEST_METHOD']
            qs = environ.get('QUERY_STRING', '')
            self.path = environ.get('PATH_INFO', '') + (('?' + qs) if qs else '')
            self.request_version = 'HTTP/1.1'
            self.protocol_version = 'HTTP/1.1'
            self.close_connection = True
            self.requestline = f'{self.command} {self.path}'
            self.client_address = (environ.get('REMOTE_ADDR', ''), 0)
            self.directory = os.getcwd()          # SimpleHTTPRequestHandler serve estático daqui
            self.headers = _HeadersWSGI(environ)
            self.rfile = environ['wsgi.input']
            self._status = 500
            self._reason = None
            self._headers_out = []
            self._chunks = []
            self._headers_buffer = []             # BaseHTTPRequestHandler.end_headers escreve aqui
        # captura de resposta (não escreve no socket)
        def send_response(self, code, message=None):
            self._status = code; self._reason = message
        def send_response_only(self, code, message=None):
            self._status = code; self._reason = message
        def send_header(self, k, v):
            if k.lower() == 'content-length':     # waitress calcula do corpo devolvido
                return
            self._headers_out.append((str(k), str(v)))
        def flush_headers(self):                  # neutraliza o write que o end_headers herdado faria
            self._headers_buffer = []
        @property
        def wfile(self):
            return self
        def write(self, b):
            if isinstance(b, str):
                b = b.encode('utf-8')
            self._chunks.append(b); return len(b)
        def log_message(self, *a): pass
        def log_request(self, *a): pass

        def _wsgi(self, start_response):
            metodo = getattr(self, 'do_' + self.command, None)
            if metodo is None:
                self._status = 501
                start_response('501 Not Implemented', [('Content-Type', 'text/plain; charset=utf-8')])
                return [b'Metodo nao suportado']
            metodo()
            linha = f'{self._status} {self._reason or razao.get(self._status, "OK")}'
            start_response(linha, self._headers_out)
            return [b''.join(self._chunks)]

    def app(environ, start_response):
        return _Adaptador(environ)._wsgi(start_response)
    return app


def servir_wsgi(handler_class, host, port, threads=8, ident='SGx'):
    """Sobe o servidor via waitress (puro-Python, vendorizado). Os handlers
    continuam sendo subclasses de SimpleHTTPRequestHandler — ver _wsgi_app."""
    import waitress
    waitress.serve(_wsgi_app(handler_class), host=host or '0.0.0.0', port=port,
                   threads=threads, ident=ident)


# ── Motor de erros: logging, classificação, throttle ────────────────────────
# Um só ponto para logar, classificar e tratar erro. Três canais convergem para
# o mesmo arquivo <sigla>_errors.log (UTF-8, rotativo): erro de request (backend),
# erro de cliente (browser, via /api/log/client) e operacional recorrente. Falha
# fatal continua no <sigla>_crash.log (instalar_captura_de_falhas).
# Formato da linha: "<ts> | <NIVEL> | <categoria> | <detalhe...>".

class ErroCliente(Exception):
    """Erro por input inválido do cliente — NÃO é bug do servidor. Vira HTTP 400
    (ou `status`) + WARNING sem stack trace. Handlers levantam isto para dados ruins."""
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


def configurar_log(sigla, data_dir, forcar=False):
    """Logger do sistema: arquivo rotativo UTF-8 (2 MB × 3) + eco no console.
    Chamar uma vez no boot; idempotente. Devolve o logger. Substitui o basicConfig.
    `forcar=True` recria os handlers apontando para outro data_dir — os testes usam
    isso para o log ir ao diretório temporário, não poluir o log do repositório."""
    from logging.handlers import RotatingFileHandler
    os.makedirs(data_dir, exist_ok=True)
    logger = logging.getLogger(sigla.lower())
    logger.setLevel(logging.WARNING)          # captura WARNING (operacional) e ERROR
    if logger.handlers:
        if not forcar:                         # já configurado — não duplica handler
            return logger
        for h in list(logger.handlers):        # forcar: fecha e recria (aponta p/ novo dir)
            logger.removeHandler(h)
            try: h.close()
            except Exception: pass
    fmt = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', datefmt='%Y-%m-%dT%H:%M:%S')
    fh = RotatingFileHandler(os.path.join(data_dir, f'{sigla.lower()}_errors.log'),
                             maxBytes=2_000_000, backupCount=3, encoding='utf-8')
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()               # console, para desenvolvimento
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    logger.propagate = False
    return logger


def caminho_log_erros(data_dir, sigla):
    return os.path.join(data_dir, f'{sigla.lower()}_errors.log')


def tratar_excecao_request(logger, metodo, path, exc):
    """Classifica uma exceção de request e devolve (status, corpo_json). O
    _safe_dispatch chama no except. ErroCliente -> 400 + WARNING sem stack;
    qualquer outra -> 500 + ERROR com traceback completo."""
    import traceback
    if isinstance(exc, ErroCliente):
        logger.warning('cliente | %s %s | %s', metodo, path, exc)
        return exc.status, {'error': str(exc)}
    logger.error('servidor | %s %s | %s\n%s', metodo, path, repr(exc), traceback.format_exc())
    return 500, {'error': 'Erro interno no servidor.'}


_throttle_ops = {}   # chave -> (ultimo_ts_logado, repeticoes_desde_entao)

def registrar_operacional(logger, chave, msg, janela=300):
    """Erro operacional recorrente (SMTP fora, OneDrive travando, rede): loga 1×
    por `janela` segundos, acumulando o contador — evita afogar o log (ex.: os
    375× 'getaddrinfo failed' viram 1 linha periódica com a contagem)."""
    agora = time.time()
    ultimo, cont = _throttle_ops.get(chave, (0.0, 0))
    if agora - ultimo >= janela:
        extra = f' (repetido {cont}x desde o último registro)' if cont else ''
        logger.warning('operacional | %s%s', msg, extra)
        _throttle_ops[chave] = (agora, 0)
    else:
        _throttle_ops[chave] = (ultimo, cont + 1)


def registrar_erro_cliente_js(logger, dados):
    """Erro de JavaScript reportado pelo navegador (/api/log/client). Throttled
    por (view+msg) para um browser em loop não floodar."""
    view = str(dados.get('view') or '?')[:40]
    msg  = str(dados.get('msg')  or 'erro')[:200]
    stack = str(dados.get('stack') or '')[:500].replace('\n', ' | ')
    registrar_operacional(logger, f'js|{view}|{msg}', f'cliente-js | {view} | {msg} | {stack}', janela=60)


def int_param(qs, nome, default=None, minimo=None, maximo=None):
    """Lê um parâmetro numérico do dict de query string (parse_qs -> listas).
    Input inválido levanta ErroCliente (-> 400) em vez de estourar int() (-> 500)."""
    v = qs.get(nome)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else None
    if v is None or v == '':
        return default
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ErroCliente(f'Parâmetro "{nome}" deve ser um número inteiro.')
    if minimo is not None and n < minimo:
        n = minimo
    if maximo is not None and n > maximo:
        n = maximo
    return n


def ler_diagnostico_erros(data_dir, sigla, limite=400, dias=7):
    """Lê o final do <sigla>_errors.log + o <sigla>_crash.log e devolve os erros
    agrupados por (nível + categoria + rota), com contagem e último exemplo —
    para a tela admin de diagnóstico. Não levanta: em qualquer falha, devolve vazio.

    A tela se chama "Erros recentes": entra só o que é dos últimos <dias> dias.
    O mais antigo vira uma contagem em 'anteriores'. Sem esse corte, defeito já
    corrigido ficava no painel para sempre — o log só rotaciona aos 2 MB, o que
    na prática não acontece — e o painel deixava de responder "o que está
    quebrado agora". Nada é apagado: o arquivo continua íntegro."""
    import datetime
    grupos = {}   # chave -> {nivel, tipo, count, ultimo, exemplo}
    anteriores = 0
    # timestamp gravado é ISO, então comparar como texto ordena igual à data
    corte = (datetime.datetime.now() - datetime.timedelta(days=dias)).isoformat(timespec='seconds')
    try:
        caminho = caminho_log_erros(data_dir, sigla)
        if os.path.isfile(caminho):
            with open(caminho, encoding='utf-8', errors='replace') as f:
                linhas = f.readlines()[-limite:]
            for linha in linhas:
                partes = linha.rstrip('\n').split(' | ')
                if len(partes) < 3:
                    continue   # linha de continuação (traceback) — ignora no agrupamento
                ts, nivel, resto = partes[0], partes[1], ' | '.join(partes[2:])
                if ts < corte:
                    anteriores += 1
                    continue
                chave_partes = resto.split(' | ')[:2]   # categoria + rota/detalhe
                chave = f'{nivel} | ' + ' | '.join(chave_partes)
                g = grupos.get(chave)
                if g:
                    g['count'] += 1; g['ultimo'] = ts
                else:
                    grupos[chave] = {'nivel': nivel, 'tipo': ' | '.join(chave_partes),
                                     'count': 1, 'ultimo': ts, 'exemplo': resto[:300]}
    except Exception:
        pass
    crash = []
    try:
        cpath = os.path.join(data_dir, f'{sigla.lower()}_crash.log')
        if os.path.isfile(cpath):
            with open(cpath, encoding='utf-8', errors='replace') as f:
                txt = f.read()[-8000:]
            # Cada início do servidor grava "=== captura armada ===". Isso NÃO é crash.
            # Só conta um bloco como falha fatal se ele traz traceback de verdade
            # (Python, faulthandler/segfault, ou exceção de thread).
            sinais = ('Traceback', 'Fatal Python error', 'Current thread 0x', 'exceção não tratada')
            crash = [b.strip() for b in txt.split('=== captura armada')
                     if any(s in b for s in sinais)][-5:]
    except Exception:
        pass
    return {'erros': sorted(grupos.values(), key=lambda g: -g['count']),
            'crash': crash, 'anteriores': anteriores, 'dias': dias}


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


_TS_NO_NOME = re.compile(r'(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})')


def backup_ts(filename):
    """Timestamp ISO a partir do nome do backup (DB_XXXX_BACKUP_ / SYNC_XXXX_BACKUP_).

    Procura a data no nome em vez de fatiar por posição fixa. A versão anterior
    usava filename[15:25], contando com prefixo de 15 chars (DB_ + sigla de 4 +
    _BACKUP_) — verdade só para o Cofre. SIS_ tinha 16 e SYNC_ tem 17, então
    qualquer chamada com o JSON devolvia data deslocada, sem erro nenhum.
    """
    m = _TS_NO_NOME.search(filename or '')
    return f"{m.group(1)}T{m.group(2).replace('-', ':')}" if m else ''


# ── Backup: contrato de envelope e Cofre (.zip = banco + anexos) ────────────────
# Padrão da família (padronização 2026-07). O JSON portátil sai com envelope
# `{"_sgx": "<SIGLA>", "schema": <int>, "exportedAt": "<ISO>", ...}`; a leitura
# aceita também os envelopes antigos de cada sistema para os backups já gravados
# em produção continuarem restauráveis. O Cofre deixa de ser só o .db e passa a
# ser um pacote .zip com o banco (banco.db) + a pasta de anexos (uploads/…),
# fechando a lacuna de os PDFs viverem fora do banco; o restore aceita o .db
# legado (sem anexos). ponytail: zipfile/sqlite da stdlib, sem dependência.

def eh_backup(data, sigla):
    """True para o envelope novo (`_sgx`) e para os antigos de cada sistema
    (marcador booleano `_sgcd`/`_sgca`/`_sgea`, ou string `sgdp_version`)."""
    if not isinstance(data, dict):
        return False
    low = sigla.lower()
    return (data.get('_sgx') == sigla
            or data.get('_' + low) is not None
            or (low + '_version') in data)

def backup_exported_at(data):
    return data.get('exportedAt') or data.get('exported_at')

def escrever_cofre(db_path, uploads_dir, dst_zip):
    """Grava o Cofre .zip: snapshot consistente do banco (via API de backup do
    SQLite, não cópia a quente) como banco.db, mais a pasta de anexos quando
    houver (uploads_dir=None nos sistemas sem anexos)."""
    import tempfile, zipfile
    fd, tmp_db = tempfile.mkstemp(suffix='.db'); os.close(fd)
    src = sqlite3.connect(db_path); bk = sqlite3.connect(tmp_db)
    try:
        with bk:
            src.backup(bk)
    finally:
        src.close(); bk.close()
    try:
        with zipfile.ZipFile(dst_zip, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(tmp_db, 'banco.db')
            if uploads_dir and os.path.isdir(uploads_dir):
                for fn in os.listdir(uploads_dir):
                    fp = os.path.join(uploads_dir, fn)
                    if os.path.isfile(fp):
                        z.write(fp, f'uploads/{fn}')
    finally:
        try: os.remove(tmp_db)
        except OSError: pass

def abrir_cofre(raw, destino_dir):
    """Lê os bytes de um Cofre e extrai para destino_dir. Aceita o .zip novo
    (banco + anexos) e o .db legado. Devolve (caminho_do_banco, anexos), onde
    anexos é a lista de nomes extraídos (pacote .zip) ou None (.db legado, não
    mexer nos uploads). Levanta ValueError se o formato for inválido.
    Protegido contra zip-slip: dos membros uploads/ só o basename é usado."""
    import zipfile
    if raw[:4] == b'PK\x03\x04':
        zpath = os.path.join(destino_dir, 'cofre.zip')
        with open(zpath, 'wb') as f:
            f.write(raw)
        with zipfile.ZipFile(zpath) as z:
            nomes = z.namelist()
            if 'banco.db' not in nomes:
                raise ValueError('Pacote inválido: banco.db ausente')
            z.extract('banco.db', destino_dir)
            anexos = []
            for n in nomes:
                if not n.startswith('uploads/') or n.endswith('/'):
                    continue
                base = os.path.basename(n)
                if not base or base.startswith('..'):
                    continue
                with z.open(n) as src_f, open(os.path.join(destino_dir, base), 'wb') as out_f:
                    shutil.copyfileobj(src_f, out_f)
                anexos.append(base)
        return os.path.join(destino_dir, 'banco.db'), anexos
    if raw[:16] == b'SQLite format 3\x00':
        dbfile = os.path.join(destino_dir, 'banco.db')
        with open(dbfile, 'wb') as f:
            f.write(raw)
        return dbfile, None
    raise ValueError('Arquivo não é um backup de banco válido (.zip ou .db)')


def pick_folder_dialog(description):
    """Abre o FolderBrowserDialog do Windows (via PowerShell) e devolve o caminho
    escolhido, ou '' se cancelado. `description` DEVE ser um literal de código —
    é interpolado no comando PowerShell, então nunca passe entrada de usuário."""
    ps_cmd = (
        'Add-Type -AssemblyName System.Windows.Forms;'
        '$d=New-Object System.Windows.Forms.FolderBrowserDialog;'
        f'$d.Description="{description}";'
        '$d.ShowNewFolderButton=$true;'
        'if($d.ShowDialog()-eq"OK"){Write-Output $d.SelectedPath}'
    )
    r = subprocess.run(['powershell', '-Sta', '-WindowStyle', 'Hidden', '-Command', ps_cmd],
                       capture_output=True, text=True, timeout=120)
    return r.stdout.strip()
