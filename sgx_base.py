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


def backup_ts(filename):
    """Timestamp ISO a partir do nome do backup no formato
    DB_XXXX_BACKUP_YYYY-MM-DD_HH-MM-SS.db. O prefixo tem sempre 15 chars nos 4
    sistemas (DB_ + código de 4 letras + _BACKUP_), então os offsets são fixos."""
    d = filename[15:25]; t = filename[26:34].replace('-', ':')
    return f'{d}T{t}'


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
