# Suíte de testes do backend (server.py) — sobe o servidor real contra um
# banco/backups temporários e bate nos endpoints REST via http.client.
# python -m unittest discover -s tests   (ou: python tests/test_server.py)
import http.client
import io
import json
import os
import shutil
import socketserver
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import uuid
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402

PORT = 3093
_tmpdir = None
_httpd = None
_thread = None


def setUpModule():
    global _tmpdir, _httpd, _thread
    _tmpdir = tempfile.mkdtemp(prefix='sgea_test_')
    server.DB_PATH = os.path.join(_tmpdir, 'sgea.db')
    server.BACKUP_DIR = os.path.join(_tmpdir, 'backups')
    os.makedirs(server.BACKUP_DIR, exist_ok=True)
    # Motor de erros: log no dir temporário (não polui o do repositório).
    server._DATA_DIR = _tmpdir
    server._log = server.sgx_base.configurar_log('SGEA', _tmpdir, forcar=True)
    server.init_db()
    # A suíte age como um sistema já instalado, com a senha padrão trocada: sem
    # isto todo login como admin/admin123 tomaria 403, porque o servidor passou a
    # recusar qualquer rota enquanto a troca obrigatória estiver pendente (o
    # bloqueio em si tem teste próprio, em TestSenhaPadraoObrigatoria).
    with server.get_db() as conn:
        conn.execute("UPDATE usuarios SET must_change_password=0 WHERE username='admin'")
        conn.commit()

    # Serve via waitress (mesmo servidor do deploy) para validar o adaptador WSGI.
    import waitress
    app = server.sgx_base._wsgi_app(server.SGEAHandler)
    _httpd = waitress.create_server(app, host='127.0.0.1', port=PORT, threads=8)
    _thread = threading.Thread(target=_httpd.run, daemon=True)
    _thread.start()


def tearDownModule():
    try: _httpd.close()
    except Exception: pass
    shutil.rmtree(_tmpdir, ignore_errors=True)


class SGEATestCase(unittest.TestCase):

    def request(self, method, path, body=None, token=None):
        conn = http.client.HTTPConnection('127.0.0.1', PORT, timeout=5)
        hdrs = {'Content-Type': 'application/json'}
        if token:
            hdrs['Authorization'] = f'Bearer {token}'
        payload = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
        conn.request(method, path, body=payload, headers=hdrs)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        try:
            parsed = json.loads(data) if data else None
        except ValueError:
            parsed = data
        return resp.status, parsed

    def login(self, username='admin', password='admin123'):
        status, data = self.request('POST', '/api/auth/login', {'username': username, 'password': password})
        self.assertEqual(status, 200, data)
        return data['token']

    def _criar_produto(self, token, qtd_por_embalagem=1):
        cod = f'TESTE.{uuid.uuid4().hex[:8]}'
        status, prod = self.request('POST', '/api/produtos', {
            'codigo_fiorilli': cod, 'nome': 'Produto de Teste',
            'qtd_por_embalagem': qtd_por_embalagem, 'unidade_consumo': 'UN',
        }, token)
        self.assertEqual(status, 201, prod)
        return prod['id']


class TestAuth(SGEATestCase):

    def test_login_ok(self):
        status, data = self.request('POST', '/api/auth/login', {'username': 'admin', 'password': 'admin123'})
        self.assertEqual(status, 200)
        self.assertIn('token', data)
        self.assertTrue(data['user']['admin'])

    def test_login_senha_errada(self):
        status, data = self.request('POST', '/api/auth/login', {'username': 'admin', 'password': 'errada'})
        self.assertEqual(status, 401)

    def test_rota_protegida_sem_token(self):
        status, data = self.request('GET', '/api/produtos')
        self.assertEqual(status, 401)


class TestConfiguracoes(SGEATestCase):

    def test_org_info_e_last_backup_sao_publicos(self):
        status, data = self.request('GET', '/api/public/org-info')
        self.assertEqual(status, 200)
        self.assertIn('orgao', data)
        status, data = self.request('GET', '/api/public/last-backup')
        self.assertEqual(status, 200)
        self.assertIn('ts', data)

    def test_salvar_e_ler_orgao(self):
        token = self.login()
        status, _ = self.request('PUT', '/api/settings/org', {'orgao': 'Prefeitura de Teste', 'municipio': 'Teste/SP'}, token)
        self.assertEqual(status, 200)
        status, data = self.request('GET', '/api/settings', token=token)
        self.assertEqual(data['orgao'], 'Prefeitura de Teste')
        status, data = self.request('GET', '/api/public/org-info')
        self.assertEqual(data['orgao'], 'Prefeitura de Teste')

    def test_brasao_upload_e_remocao(self):
        token = self.login()
        status, data = self.request('PUT', '/api/settings/brasao', {'brasao_dataurl': 'data:image/png;base64,ABC'}, token)
        self.assertEqual(status, 200)
        status, data = self.request('GET', '/api/settings/brasao', token=token)
        self.assertEqual(data['brasao_dataurl'], 'data:image/png;base64,ABC')
        status, _ = self.request('PUT', '/api/settings/brasao', {'brasao_dataurl': ''}, token)
        self.assertEqual(status, 200)
        status, data = self.request('GET', '/api/settings/brasao', token=token)
        self.assertEqual(data['brasao_dataurl'], '')


class TestCrudCadastros(SGEATestCase):

    def test_centro_custo_crud(self):
        token = self.login()
        status, cc = self.request('POST', '/api/centros-custo', {'codigo': 'CC1', 'nome': 'Educação'}, token)
        self.assertEqual(status, 201, cc)
        status, listado = self.request('GET', '/api/centros-custo', token=token)
        self.assertEqual(status, 200)
        self.assertTrue(any(i['id'] == cc['id'] for i in listado['items']))
        status, atualizado = self.request('PUT', f'/api/centros-custo/{cc["id"]}', {'nome': 'Educação e Cultura'}, token)
        self.assertEqual(status, 200)
        self.assertEqual(atualizado['nome'], 'Educação e Cultura')

    def test_centro_custo_codigo_duplicado(self):
        token = self.login()
        self.request('POST', '/api/centros-custo', {'codigo': 'DUP1', 'nome': 'A'}, token)
        status, data = self.request('POST', '/api/centros-custo', {'codigo': 'DUP1', 'nome': 'B'}, token)
        self.assertEqual(status, 409, data)

    def test_produto_codigo_fiorilli_duplicado(self):
        token = self.login()
        self.request('POST', '/api/produtos', {'codigo_fiorilli': 'DUPFIO', 'nome': 'X'}, token)
        status, data = self.request('POST', '/api/produtos', {'codigo_fiorilli': 'DUPFIO', 'nome': 'Y'}, token)
        self.assertEqual(status, 409, data)


class TestFefoDireto(unittest.TestCase):
    """Testa _consumir_fefo diretamente contra o banco, sem passar pela camada
    HTTP — feedback mais rápido na lógica de maior risco do sistema."""

    def setUp(self):
        self.pid = str(uuid.uuid4())
        with server.get_db() as conn:
            conn.execute(
                'INSERT INTO produtos (id,codigo_fiorilli,nome,qtd_por_embalagem) VALUES (?,?,?,1)',
                (self.pid, f'FEFO.{uuid.uuid4().hex[:8]}', 'Produto FEFO')
            )

    def _add_lote(self, qtd, validade=None, custo=10.0):
        with server.get_db() as conn:
            cur = conn.execute(
                '''INSERT INTO lotes (produto_id,lote_numero,data_validade,quantidade_recebida,quantidade_atual,valor_unitario_custo)
                   VALUES (?,?,?,?,?,?)''',
                (self.pid, 'L', validade, qtd, qtd, custo)
            )
            return cur.lastrowid

    def _saldo(self):
        with server.get_db() as conn:
            row = conn.execute('SELECT estoque_fisico FROM v_estoque WHERE produto_id=?', (self.pid,)).fetchone()
            return row['estoque_fisico'] if row else 0

    def test_consome_lote_mais_proximo_de_vencer_primeiro(self):
        lote_longe = self._add_lote(10, '2027-12-31')
        lote_perto = self._add_lote(10, '2026-08-01')
        with server.get_db() as conn:
            consumos, valor_medio, valor_total = server._consumir_fefo(conn, self.pid, 5)
        self.assertEqual(consumos, [(lote_perto, 5, 10.0)])
        with server.get_db() as conn:
            self.assertEqual(conn.execute('SELECT quantidade_atual FROM lotes WHERE id=?', (lote_longe,)).fetchone()[0], 10)
            self.assertEqual(conn.execute('SELECT quantidade_atual FROM lotes WHERE id=?', (lote_perto,)).fetchone()[0], 5)

    def test_divide_consumo_entre_lotes_quando_um_nao_cobre(self):
        lote_a = self._add_lote(3, '2026-08-01', custo=10.0)
        lote_b = self._add_lote(10, '2026-09-01', custo=20.0)
        lote_sem_validade = self._add_lote(100, None, custo=5.0)
        with server.get_db() as conn:
            consumos, valor_medio, valor_total = server._consumir_fefo(conn, self.pid, 8)
        # consome lote_a inteiro (3) + parte de lote_b (5); lote sem validade intocado
        self.assertEqual(consumos, [(lote_a, 3, 10.0), (lote_b, 5, 20.0)])
        self.assertEqual(valor_total, 3 * 10.0 + 5 * 20.0)
        self.assertAlmostEqual(valor_medio, valor_total / 8)
        with server.get_db() as conn:
            self.assertEqual(conn.execute('SELECT quantidade_atual FROM lotes WHERE id=?', (lote_sem_validade,)).fetchone()[0], 100)

    def test_lotes_sem_validade_consumidos_por_ordem_de_chegada(self):
        primeiro = self._add_lote(5, None, custo=1.0)
        segundo = self._add_lote(5, None, custo=2.0)
        with server.get_db() as conn:
            consumos, _, _ = server._consumir_fefo(conn, self.pid, 5)
        self.assertEqual(consumos, [(primeiro, 5, 1.0)])
        with server.get_db() as conn:
            self.assertEqual(conn.execute('SELECT quantidade_atual FROM lotes WHERE id=?', (segundo,)).fetchone()[0], 5)

    def test_estoque_insuficiente_nao_decrementa_nada(self):
        self._add_lote(5, '2026-08-01')
        with server.get_db() as conn:
            with self.assertRaises(server.EstoqueInsuficiente):
                server._consumir_fefo(conn, self.pid, 100)
        self.assertEqual(self._saldo(), 5)  # rollback: nada foi decrementado


class TestEntradasSaidas(SGEATestCase):

    def test_entrada_compra_direta_converte_caixa_para_unidade(self):
        token = self.login()
        pid = self._criar_produto(token, qtd_por_embalagem=12)
        status, ent = self.request('POST', '/api/entradas', {
            'tipo': 'compra_direta', 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid, 'quantidade_embalagem': 5, 'valor_unitario': 13.55,
                       'lote_numero': 'L1', 'data_validade': '2026-08-01'}]
        }, token)
        self.assertEqual(status, 201, ent)
        self.assertEqual(ent['itens'][0]['quantidade_unidades'], 60)
        status, prod = self.request('GET', f'/api/produtos/{pid}', token=token)
        self.assertEqual(prod['estoque_fisico'], 60)
        self.assertAlmostEqual(prod['estoque_financeiro'], 60 * 13.55)

    def test_entrada_com_pedido(self):
        token = self.login()
        pid = self._criar_produto(token)
        status, ped = self.request('POST', '/api/pedidos', {
            'numero': f'{uuid.uuid4().hex[:6]}/2026',
            'itens': [{'produto_id': pid, 'quantidade_pedida': 10}],
        }, token)
        self.assertEqual(status, 201, ped)
        status, ent = self.request('POST', '/api/entradas', {
            'tipo': 'pedido', 'pedido_id': ped['id'], 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid, 'quantidade_unidades': 10, 'valor_unitario': 2.0}]
        }, token)
        self.assertEqual(status, 201, ent)
        self.assertEqual(ent['pedido_id'], ped['id'])

    def test_saida_fracionada_e_reversao_no_delete(self):
        token = self.login()
        pid = self._criar_produto(token, qtd_por_embalagem=12)
        self.request('POST', '/api/entradas', {
            'tipo': 'compra_direta', 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid, 'quantidade_embalagem': 1, 'valor_unitario': 10}]
        }, token)
        status, sai = self.request('POST', '/api/saidas', {
            'data': '2026-07-12', 'itens': [{'produto_id': pid, 'quantidade': 2}]
        }, token)
        self.assertEqual(status, 201, sai)
        status, prod = self.request('GET', f'/api/produtos/{pid}', token=token)
        self.assertEqual(prod['estoque_fisico'], 10)  # 12 - 2

        status, _ = self.request('DELETE', f'/api/saidas/{sai["id"]}', token=token)
        self.assertEqual(status, 200)
        status, prod = self.request('GET', f'/api/produtos/{pid}', token=token)
        self.assertEqual(prod['estoque_fisico'], 12)  # revertido

    def test_saida_estoque_insuficiente_retorna_409(self):
        token = self.login()
        pid = self._criar_produto(token)
        status, data = self.request('POST', '/api/saidas', {
            'data': '2026-07-12', 'itens': [{'produto_id': pid, 'quantidade': 5}]
        }, token)
        self.assertEqual(status, 409, data)

    def test_delete_entrada_bloqueado_apos_consumo_parcial(self):
        token = self.login()
        pid = self._criar_produto(token)
        status, ent = self.request('POST', '/api/entradas', {
            'tipo': 'compra_direta', 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid, 'quantidade_unidades': 10, 'valor_unitario': 1}]
        }, token)
        self.request('POST', '/api/saidas', {
            'data': '2026-07-12', 'itens': [{'produto_id': pid, 'quantidade': 3}]
        }, token)
        status, data = self.request('DELETE', f'/api/entradas/{ent["id"]}', token=token)
        self.assertEqual(status, 409, data)

    # ── Pedidos: itens, saldo, status agregado ──────────────────────────────
    # (métodos aqui, não numa classe TestPedidos própria, pra não sortear depois
    # de TestLixeiraEWipe — ver comentário na classe abaixo sobre ordem alfabética)

    def _criar_pedido(self, token, pid_produto, quantidade_pedida=10):
        status, ped = self.request('POST', '/api/pedidos', {
            'numero': f'{uuid.uuid4().hex[:6]}/2026',
            'itens': [{'produto_id': pid_produto, 'quantidade_pedida': quantidade_pedida}],
        }, token)
        self.assertEqual(status, 201, ped)
        return ped

    def test_criar_pedido_com_itens_e_itens_imutaveis_na_edicao(self):
        token = self.login()
        pid = self._criar_produto(token)
        ped = self._criar_pedido(token, pid, quantidade_pedida=10)
        self.assertEqual(len(ped['itens']), 1)
        self.assertEqual(ped['itens'][0]['quantidade_pedida'], 10)
        self.assertEqual(ped['itens'][0]['status'], 'aberto')

        status, ped2 = self.request('PUT', f'/api/pedidos/{ped["id"]}', {
            'itens': [{'produto_id': pid, 'quantidade_pedida': 999}],  # ignorado — só cabeçalho é editável
            'codigo_licitacao': 'LIC-123',
        }, token)
        self.assertEqual(status, 200, ped2)
        self.assertEqual(ped2['codigo_licitacao'], 'LIC-123')
        self.assertEqual(ped2['itens'][0]['quantidade_pedida'], 10)  # inalterado

    def test_entrada_dentro_do_saldo_reduz_saldo_do_item(self):
        token = self.login()
        pid = self._criar_produto(token)
        ped = self._criar_pedido(token, pid, quantidade_pedida=10)
        status, ent = self.request('POST', '/api/entradas', {
            'tipo': 'pedido', 'pedido_id': ped['id'], 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid, 'quantidade_unidades': 5, 'valor_unitario': 2.0}]
        }, token)
        self.assertEqual(status, 201, ent)
        status, ped2 = self.request('GET', f'/api/pedidos/{ped["id"]}', token=token)
        item = ped2['itens'][0]
        self.assertEqual(item['quantidade_recebida'], 5)
        self.assertEqual(item['saldo'], 5)
        self.assertEqual(item['status'], 'parcial')
        self.assertEqual(ped2['status'], 'aberto')

    def test_entrada_excedendo_saldo_retorna_409_sem_gravar_nada(self):
        token = self.login()
        pid = self._criar_produto(token)
        ped = self._criar_pedido(token, pid, quantidade_pedida=10)
        status, data = self.request('POST', '/api/entradas', {
            'tipo': 'pedido', 'pedido_id': ped['id'], 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid, 'quantidade_unidades': 12, 'valor_unitario': 2.0}]
        }, token)
        self.assertEqual(status, 409, data)
        status, ped2 = self.request('GET', f'/api/pedidos/{ped["id"]}', token=token)
        self.assertEqual(ped2['itens'][0]['saldo'], 10)  # nada foi consumido
        status, prod = self.request('GET', f'/api/produtos/{pid}', token=token)
        self.assertEqual(prod['estoque_fisico'], 0)  # nenhum lote foi criado

    def test_entrada_com_produto_fora_do_pedido_retorna_erro(self):
        token = self.login()
        pid = self._criar_produto(token)
        outro_pid = self._criar_produto(token)
        ped = self._criar_pedido(token, pid, quantidade_pedida=10)
        status, data = self.request('POST', '/api/entradas', {
            'tipo': 'pedido', 'pedido_id': ped['id'], 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': outro_pid, 'quantidade_unidades': 1, 'valor_unitario': 2.0}]
        }, token)
        self.assertEqual(status, 409, data)

    def test_anular_saldo_item_zerado_retorna_409(self):
        token = self.login()
        pid = self._criar_produto(token)
        ped = self._criar_pedido(token, pid, quantidade_pedida=10)
        self.request('POST', '/api/entradas', {
            'tipo': 'pedido', 'pedido_id': ped['id'], 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid, 'quantidade_unidades': 10, 'valor_unitario': 2.0}]
        }, token)
        item_id = ped['itens'][0]['id']
        status, data = self.request('PUT', f'/api/pedidos/{ped["id"]}/itens/{item_id}/anular', {}, token)
        self.assertEqual(status, 409, data)

    def test_anular_saldo_muda_status_do_item_e_do_pedido(self):
        token = self.login()
        pid = self._criar_produto(token)
        ped = self._criar_pedido(token, pid, quantidade_pedida=10)
        self.request('POST', '/api/entradas', {
            'tipo': 'pedido', 'pedido_id': ped['id'], 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid, 'quantidade_unidades': 5, 'valor_unitario': 2.0}]
        }, token)
        item_id = ped['itens'][0]['id']
        status, ped2 = self.request('PUT', f'/api/pedidos/{ped["id"]}/itens/{item_id}/anular', {}, token)
        self.assertEqual(status, 200, ped2)
        self.assertEqual(ped2['itens'][0]['status'], 'encerrado_parcial')
        self.assertEqual(ped2['itens'][0]['saldo'], 0)
        self.assertEqual(ped2['status'], 'encerrado_parcial')

    def test_status_pedido_atendido_quando_todos_itens_atendidos(self):
        token = self.login()
        pid = self._criar_produto(token)
        ped = self._criar_pedido(token, pid, quantidade_pedida=10)
        status, ent = self.request('POST', '/api/entradas', {
            'tipo': 'pedido', 'pedido_id': ped['id'], 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid, 'quantidade_unidades': 10, 'valor_unitario': 2.0}]
        }, token)
        self.assertEqual(status, 201, ent)
        status, ped2 = self.request('GET', f'/api/pedidos/{ped["id"]}', token=token)
        self.assertEqual(ped2['itens'][0]['status'], 'atendido')
        self.assertEqual(ped2['status'], 'atendido')

    def test_status_pedido_fica_aberto_enquanto_algum_item_esta_pendente(self):
        token = self.login()
        pid_a = self._criar_produto(token)
        pid_b = self._criar_produto(token)
        status, ped = self.request('POST', '/api/pedidos', {
            'numero': f'{uuid.uuid4().hex[:6]}/2026',
            'itens': [
                {'produto_id': pid_a, 'quantidade_pedida': 5},
                {'produto_id': pid_b, 'quantidade_pedida': 5},
            ],
        }, token)
        self.assertEqual(status, 201, ped)
        # atende só o item A por completo — item B continua aberto
        status, ent = self.request('POST', '/api/entradas', {
            'tipo': 'pedido', 'pedido_id': ped['id'], 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid_a, 'quantidade_unidades': 5, 'valor_unitario': 2.0}]
        }, token)
        self.assertEqual(status, 201, ent)
        status, ped2 = self.request('GET', f'/api/pedidos/{ped["id"]}', token=token)
        self.assertEqual(ped2['status'], 'aberto')  # item B ainda pendente

    def test_cancelar_pedido_zera_saldo_pendente_e_bloqueia_se_ja_atendido(self):
        token = self.login()
        pid = self._criar_produto(token)
        ped = self._criar_pedido(token, pid, quantidade_pedida=10)
        self.request('POST', '/api/entradas', {
            'tipo': 'pedido', 'pedido_id': ped['id'], 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid, 'quantidade_unidades': 3, 'valor_unitario': 2.0}]
        }, token)
        status, ped2 = self.request('PUT', f'/api/pedidos/{ped["id"]}/cancelar', {}, token)
        self.assertEqual(status, 200, ped2)
        self.assertEqual(ped2['status'], 'cancelado')
        self.assertEqual(ped2['itens'][0]['saldo'], 0)
        self.assertEqual(ped2['itens'][0]['quantidade_recebida'], 3)  # o que já entrou não é desfeito

        # pedido totalmente atendido não pode ser cancelado
        pid2 = self._criar_produto(token)
        ped3 = self._criar_pedido(token, pid2, quantidade_pedida=5)
        self.request('POST', '/api/entradas', {
            'tipo': 'pedido', 'pedido_id': ped3['id'], 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid2, 'quantidade_unidades': 5, 'valor_unitario': 2.0}]
        }, token)
        status, data = self.request('PUT', f'/api/pedidos/{ped3["id"]}/cancelar', {}, token)
        self.assertEqual(status, 409, data)

    # ── Dashboard e relatórios ───────────────────────────────────────────────
    # (métodos aqui pelo mesmo motivo dos testes de Pedidos acima: não sortear
    # depois de TestLixeiraEWipe)

    def test_dashboard_agrega_estoque_lotes_e_pedidos(self):
        # DB é compartilhado por toda a classe (testes anteriores já criaram
        # produtos/pedidos) — comparar contra uma baseline em vez de valor
        # absoluto, senão a ordem de execução dos outros testes quebra isto.
        token = self.login()
        hoje = time.strftime('%Y-%m-%d')
        status, base = self.request('GET', '/api/dashboard', token=token)
        self.assertEqual(status, 200, base)

        pid = self._criar_produto(token)
        self.request('POST', '/api/entradas', {
            'tipo': 'compra_direta', 'data_entrega': hoje,
            'itens': [{'produto_id': pid, 'quantidade_unidades': 10, 'valor_unitario': 3.0,
                       'data_validade': '2000-01-01'}]
        }, token)
        pid_zerado = self._criar_produto(token)
        ped = self._criar_pedido(token, pid_zerado, quantidade_pedida=5)
        self.assertEqual(ped['status'], 'aberto')

        status, dash = self.request('GET', '/api/dashboard', token=token)
        self.assertEqual(status, 200, dash)
        self.assertEqual(dash['produtos_ativos'] - base['produtos_ativos'], 2)
        self.assertEqual(dash['produtos_zerados'] - base['produtos_zerados'], 1)
        self.assertAlmostEqual(dash['estoque_valor_total'] - base['estoque_valor_total'], 30.0)
        self.assertEqual(dash['lotes_vencidos'] - base['lotes_vencidos'], 1)  # validade 2000-01-01
        self.assertEqual(dash['pedidos_abertos'] - base['pedidos_abertos'], 1)
        self.assertEqual(len(dash['movimentacao_mensal']), 6)
        self.assertEqual(dash['movimentacao_mensal'][-1]['mes'], hoje[:7])
        delta_mes = dash['movimentacao_mensal'][-1]['entradas'] - base['movimentacao_mensal'][-1]['entradas']
        self.assertAlmostEqual(delta_mes, 30.0)

    def test_relatorio_movimentacao_filtra_por_periodo_e_soma_totais(self):
        # data fora do padrão '2026-07-01'/hoje usado pelos outros testes da
        # classe, pra não ter entrada/saída de outro teste contaminando o filtro.
        token = self.login()
        data = '2031-06-15'
        pid = self._criar_produto(token)
        self.request('POST', '/api/entradas', {
            'tipo': 'compra_direta', 'data_entrega': data,
            'itens': [{'produto_id': pid, 'quantidade_unidades': 10, 'valor_unitario': 2.0}]
        }, token)
        self.request('POST', '/api/saidas', {
            'data': data, 'itens': [{'produto_id': pid, 'quantidade': 4}]
        }, token)
        status, rel = self.request('GET', f'/api/relatorio/movimentacao?de={data}&ate={data}', token=token)
        self.assertEqual(status, 200, rel)
        self.assertEqual(len(rel['entradas']), 1)
        self.assertEqual(len(rel['saidas']), 1)
        self.assertAlmostEqual(rel['totais']['entradas_valor'], 20.0)
        self.assertAlmostEqual(rel['totais']['saidas_valor'], 4 * rel['saidas'][0]['valor_unitario_medio'])

        status, vazio = self.request('GET', '/api/relatorio/movimentacao?de=2000-01-01&ate=2000-01-02', token=token)
        self.assertEqual(vazio['entradas'], [])
        self.assertEqual(vazio['saidas'], [])

    def test_relatorio_pedidos_abertos_so_lista_status_aberto(self):
        token = self.login()
        pid_aberto = self._criar_produto(token)
        ped_aberto = self._criar_pedido(token, pid_aberto, quantidade_pedida=10)
        pid_atendido = self._criar_produto(token)
        ped_atendido = self._criar_pedido(token, pid_atendido, quantidade_pedida=5)
        self.request('POST', '/api/entradas', {
            'tipo': 'pedido', 'pedido_id': ped_atendido['id'], 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid_atendido, 'quantidade_unidades': 5, 'valor_unitario': 1.0}]
        }, token)

        status, rel = self.request('GET', '/api/relatorio/pedidos-abertos', token=token)
        self.assertEqual(status, 200, rel)
        ids = [p['id'] for p in rel['items']]
        self.assertIn(ped_aberto['id'], ids)
        self.assertNotIn(ped_atendido['id'], ids)
        item = next(p for p in rel['items'] if p['id'] == ped_aberto['id'])['itens'][0]
        self.assertEqual(item['saldo'], 10)


class TestFornecedores(SGEATestCase):
    # "Fornecedores" sorta entre "FefoDireto" e "LixeiraEWipe" — não quebra a
    # suposição de ordem alfabética do wipe (ver comentário na classe abaixo).

    def _criar_fornecedor(self, token, razao_social='Fornecedor de Teste', cnpj=None):
        cnpj = cnpj or f'{uuid.uuid4().int % 10**14:014d}'
        status, forn = self.request('POST', '/api/fornecedores', {
            'razao_social': razao_social, 'cnpj': cnpj, 'cnpj_digits': cnpj,
        }, token)
        self.assertEqual(status, 200, forn)
        return forn

    def test_criar_e_buscar_fornecedor(self):
        token = self.login()
        forn = self._criar_fornecedor(token, razao_social='Acme Ltda')
        status, buscado = self.request('GET', f'/api/fornecedores/{forn["id"]}', token=token)
        self.assertEqual(status, 200, buscado)
        self.assertEqual(buscado['razao_social'], 'Acme Ltda')
        self.assertIn(forn['id'], [f['id'] for f in self.request('GET', '/api/fornecedores', token=token)[1]['items']])

    def test_atualizar_fornecedor_e_conflito_de_concorrencia(self):
        token = self.login()
        forn = self._criar_fornecedor(token)
        status, editado = self.request('PUT', f'/api/fornecedores/{forn["id"]}', {
            'nome_fantasia': 'Acme', '_baseUpdatedAt': forn['updatedAt'],
        }, token)
        self.assertEqual(status, 200, editado)
        self.assertEqual(editado['nome_fantasia'], 'Acme')
        self.assertEqual(editado['razao_social'], forn['razao_social'])  # merge preserva o resto

        # _baseUpdatedAt desatualizado (o registro já mudou) -> 409
        status, conflito = self.request('PUT', f'/api/fornecedores/{forn["id"]}', {
            'obs': 'tentativa antiga', '_baseUpdatedAt': forn['updatedAt'],
        }, token)
        self.assertEqual(status, 409, conflito)

    def test_soft_delete_e_restaurar_fornecedor(self):
        token = self.login()
        forn = self._criar_fornecedor(token)
        status, _ = self.request('DELETE', f'/api/fornecedores/{forn["id"]}', token=token)
        self.assertEqual(status, 200)

        status, ativos = self.request('GET', '/api/fornecedores', token=token)
        self.assertNotIn(forn['id'], [f['id'] for f in ativos['items']])
        status, lixeira = self.request('GET', '/api/fornecedores?trash=1', token=token)
        self.assertIn(forn['id'], [f['id'] for f in lixeira['items']])

        status, _ = self.request('PUT', f'/api/fornecedores/{forn["id"]}/restore', token=token)
        self.assertEqual(status, 200)
        status, ativos2 = self.request('GET', '/api/fornecedores', token=token)
        self.assertIn(forn['id'], [f['id'] for f in ativos2['items']])

    def test_import_upsert_por_cnpj_preserva_certidoes_e_sancoes_e_ignora_invalido(self):
        token = self.login()
        cnpj = f'{uuid.uuid4().int % 10**14:014d}'
        forn = self._criar_fornecedor(token, razao_social='Fornecedor Original', cnpj=cnpj)
        # adiciona certidão/sanção locais antes de importar por cima
        self.request('PUT', f'/api/fornecedores/{forn["id"]}', {
            'certidoes': [{'tipoId': 'fgts', 'emissao': '2026-01-01', 'validade': '2027-01-01'}],
            'sancoes': [{'tipo': 'advertencia', 'dataAplicacao': '2026-01-01'}],
        }, token)

        status, imp = self.request('POST', '/api/fornecedores/import', {
            'fornecedores': [
                {'cnpj': cnpj, 'razao_social': 'Fornecedor Atualizado'},  # atualiza por CNPJ
                {'cnpj': f'{uuid.uuid4().int % 10**14:014d}', 'razao_social': 'Fornecedor Novo'},  # novo
                {'cnpj': '123', 'razao_social': 'CNPJ Invalido'},  # ignorado (não tem 14 dígitos)
            ]
        }, token)
        self.assertEqual(status, 200, imp)
        self.assertEqual(imp['novos'], 1)
        self.assertEqual(imp['atualizados'], 1)
        self.assertEqual(imp['ignorados'], 1)

        status, atualizado = self.request('GET', f'/api/fornecedores/{forn["id"]}', token=token)
        self.assertEqual(atualizado['razao_social'], 'Fornecedor Atualizado')
        self.assertEqual(len(atualizado['certidoes']), 1)  # preservada
        self.assertEqual(len(atualizado['sancoes']), 1)    # preservada

    def test_import_exige_admin(self):
        # Cria e depois remove o usuário não-admin — não pode sobrar no banco
        # compartilhado da suíte, senão quebra a contagem exata em TestLixeiraEWipe.
        token = self.login()
        username = f'user{uuid.uuid4().hex[:6]}'
        status, data = self.request('POST', '/api/usuarios', {
            'username': username, 'nome': 'Não Admin', 'password': 'abc12345', 'admin': False,
        }, token)
        self.assertEqual(status, 201, data)
        try:
            _, non_admin = self.request('POST', '/api/auth/login', {'username': username, 'password': 'abc12345'})
            status, resp = self.request('POST', '/api/fornecedores/import', {'fornecedores': []}, non_admin['token'])
            self.assertEqual(status, 403, resp)
        finally:
            self.request('DELETE', f'/api/usuarios/{data["id"]}', token=token)

    def test_fk_pedido_entrada_resolve_apos_migracao(self):
        token = self.login()
        forn = self._criar_fornecedor(token, razao_social='Fornecedor Vinculado')
        pid = self._criar_produto(token)
        status, ent = self.request('POST', '/api/entradas', {
            'tipo': 'compra_direta', 'data_entrega': '2026-07-01', 'fornecedor_id': forn['id'],
            'itens': [{'produto_id': pid, 'quantidade_unidades': 5, 'valor_unitario': 2.0}]
        }, token)
        self.assertEqual(status, 201, ent)
        status, buscada = self.request('GET', f'/api/entradas/{ent["id"]}', token=token)
        self.assertEqual(buscada['fornecedor_nome'], 'Fornecedor Vinculado')


class TestLixeiraEWipe(SGEATestCase):
    # ponytail: test_wipe_* apaga o banco compartilhado da suíte — depende de
    # unittest descobrir as classes em ordem alfabética ("L" já é a última classe
    # hoje). Se uma nova classe de teste for adicionada depois de "L" no alfabeto,
    # mova o teste de wipe para o final do arquivo ou isole-o em módulo próprio.

    def test_entrada_excluida_zera_lote_e_restaurar_devolve(self):
        token = self.login()
        pid = self._criar_produto(token)
        status, ent = self.request('POST', '/api/entradas', {
            'tipo': 'compra_direta', 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid, 'quantidade_unidades': 10, 'valor_unitario': 1}]
        }, token)
        self.assertEqual(status, 201, ent)

        self.request('DELETE', f'/api/entradas/{ent["id"]}', token=token)
        status, prod = self.request('GET', f'/api/produtos/{pid}', token=token)
        self.assertEqual(prod['estoque_fisico'], 0)  # exclusão zera o efeito no estoque, não só some da lista

        status, trash = self.request('GET', '/api/entradas?trash=1', token=token)
        self.assertTrue(any(e['id'] == ent['id'] for e in trash['items']))

        status, restored = self.request('PUT', f'/api/entradas/{ent["id"]}/restore', token=token)
        self.assertEqual(status, 200, restored)
        status, prod = self.request('GET', f'/api/produtos/{pid}', token=token)
        self.assertEqual(prod['estoque_fisico'], 10)

    def test_saida_excluida_e_restaurada_reconsome_fefo(self):
        token = self.login()
        pid = self._criar_produto(token)
        self.request('POST', '/api/entradas', {
            'tipo': 'compra_direta', 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid, 'quantidade_unidades': 10, 'valor_unitario': 2}]
        }, token)
        status, sai = self.request('POST', '/api/saidas', {
            'data': '2026-07-12', 'itens': [{'produto_id': pid, 'quantidade': 4}]
        }, token)
        self.assertEqual(status, 201, sai)

        self.request('DELETE', f'/api/saidas/{sai["id"]}', token=token)
        status, prod = self.request('GET', f'/api/produtos/{pid}', token=token)
        self.assertEqual(prod['estoque_fisico'], 10)  # revertido

        status, restored = self.request('PUT', f'/api/saidas/{sai["id"]}/restore', token=token)
        self.assertEqual(status, 200, restored)
        status, prod = self.request('GET', f'/api/produtos/{pid}', token=token)
        self.assertEqual(prod['estoque_fisico'], 6)  # 10 - 4 de novo

    def test_wipe_mantem_usuarios_e_settings_limpa_o_resto(self):
        token = self.login()
        self._criar_produto(token)
        self.request('PUT', '/api/settings/org', {'orgao': 'Prefeitura de Teste Wipe'}, token)

        status, _ = self.request('DELETE', '/api/wipe', token=token)
        self.assertEqual(status, 200)

        status, produtos = self.request('GET', '/api/produtos', token=token)
        self.assertEqual(produtos['items'], [])
        status, usuarios = self.request('GET', '/api/usuarios', token=token)
        self.assertEqual(len(usuarios), 1)
        status, settings = self.request('GET', '/api/settings', token=token)
        self.assertEqual(settings['orgao'], 'Prefeitura de Teste Wipe')


class TestAuditoria(SGEATestCase):

    def test_gravar_e_filtrar_auditoria(self):
        token = self.login()
        status, _ = self.request('POST', '/api/audit', {'type': 'PRODUTO_CRIADO', 'detail': 'Produto XYZ criado'}, token)
        self.assertEqual(status, 200)
        status, data = self.request('GET', '/api/audit?tipo=PRODUTO_CRIADO', token=token)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data['total'], 1)
        self.assertEqual(data['items'][0]['type'], 'PRODUTO_CRIADO')
        self.assertEqual(data['items'][0]['user_nome'], 'Administrador')  # vem da sessão, não do body

    def test_audit_ignora_user_do_body(self):
        token = self.login()
        self.request('POST', '/api/audit', {'type': 'TESTE', 'detail': 'x', 'user_nome': 'Forjado'}, token)
        status, data = self.request('GET', '/api/audit?tipo=TESTE', token=token)
        self.assertEqual(data['items'][0]['user_nome'], 'Administrador')


class ReconciliacaoUnitTest(unittest.TestCase):
    """Funções puras da reconciliação com o Fiorilli (sem servidor/DB)."""

    CSV = (
        'CADPRO;DISC1;UNID1;QUAN1;QUAN2;QUAN3;VATO3\r\n'
        '002;GRUPO;;;;;\r\n'                                    # grupo: ignorado
        '002.001;SUBGRUPO;;;;;\r\n'                             # subgrupo: ignorado
        '002.001.036;Leite integral;UN;700;20;680;1360,00\r\n' # confere direto (UN=UN)
        '001.004.012;Papel A4;CX;1;0;0,68;170,00\r\n'          # 0,68 CX ×25 = 17 UN
        '003.002.008;Detergente 5L;UN;40;0;40;200,00\r\n'      # diverge (40 vs 34)
        '014.011.004;Cabo vassoura;UN;55;0;55,0000009;-21,24\r\n'  # confere + valor negativo
        '007.003.021;Luva nitrilica;UN;120;0;120;600,00\r\n'   # só Fiorilli
        '012.008.045;Fita zebrada;RL;8;0;8;80,00\r\n'          # unidade incompativel (RL vs UN)
    )
    PRODUTOS = [
        {'codigo_fiorilli': '002.001.036', 'nome': 'Leite', 'unidade_consumo': 'UN', 'unidade_licitada': 'UN', 'qtd_por_embalagem': 1, 'estoque_fisico': 680, 'estoque_financeiro': 1360.0},
        {'codigo_fiorilli': '001.004.012', 'nome': 'Papel A4', 'unidade_consumo': 'UN', 'unidade_licitada': 'CX', 'qtd_por_embalagem': 25, 'estoque_fisico': 17, 'estoque_financeiro': 170.0},
        {'codigo_fiorilli': '003.002.008', 'nome': 'Detergente', 'unidade_consumo': 'UN', 'unidade_licitada': 'UN', 'qtd_por_embalagem': 1, 'estoque_fisico': 34, 'estoque_financeiro': 170.0},
        {'codigo_fiorilli': '014.011.004', 'nome': 'Cabo', 'unidade_consumo': 'UN', 'unidade_licitada': 'UN', 'qtd_por_embalagem': 1, 'estoque_fisico': 55, 'estoque_financeiro': 0.0},
        {'codigo_fiorilli': '012.008.045', 'nome': 'Fita', 'unidade_consumo': 'UN', 'unidade_licitada': 'UND', 'qtd_por_embalagem': 200, 'estoque_fisico': 200, 'estoque_financeiro': 80.0},
        {'codigo_fiorilli': '009.005.100', 'nome': 'Cafe avulso', 'unidade_consumo': 'UN', 'unidade_licitada': 'UN', 'qtd_por_embalagem': 1, 'estoque_fisico': 12, 'estoque_financeiro': 60.0},  # só SGEA
        {'codigo_fiorilli': '099.099.099', 'nome': 'Zerado inativo', 'unidade_consumo': 'UN', 'unidade_licitada': 'UN', 'qtd_por_embalagem': 1, 'estoque_fisico': 0, 'estoque_financeiro': 0.0},  # zero implícito
    ]

    def test_parser_filtra_e_arredonda(self):
        itens = server._parse_fiorilli_posicao(self.CSV)
        self.assertNotIn('002', itens)          # grupo descartado
        self.assertNotIn('002.001', itens)      # subgrupo descartado
        self.assertEqual(itens['001.004.012']['estoque'], 0.68)
        self.assertEqual(itens['014.011.004']['estoque'], 55.0)   # 55,0000009 -> 55.0
        self.assertTrue(itens['014.011.004']['valor_negativo'])

    def test_parser_cabecalho_invalido(self):
        with self.assertRaises(ValueError):
            server._parse_fiorilli_posicao('A;B;C\r\n1;2;3\r\n')

    def test_classificacao_baldes(self):
        fiorilli = server._parse_fiorilli_posicao(self.CSV)
        res = server._classificar_reconciliacao(fiorilli, self.PRODUTOS, '2026-07-15')
        balde = {i['codigo']: i for i in res['itens']}
        self.assertEqual(balde['002.001.036']['balde'], 'confere')
        self.assertEqual(balde['001.004.012']['balde'], 'confere')       # conversão ×25
        self.assertEqual(balde['001.004.012']['fiorilli_qtd'], 17.0)     # mostrado em UN
        self.assertEqual(balde['003.002.008']['balde'], 'diverge')
        self.assertEqual(balde['003.002.008']['delta'], -6.0)
        self.assertEqual(balde['014.011.004']['balde'], 'confere')
        self.assertIn('valor_divergente', balde['014.011.004']['flags'])
        self.assertIn('fiorilli_valor_negativo', balde['014.011.004']['flags'])
        self.assertEqual(balde['007.003.021']['balde'], 'so_fiorilli')
        self.assertEqual(balde['009.005.100']['balde'], 'so_sgea')
        self.assertEqual(balde['012.008.045']['balde'], 'unidade')       # RL não casa
        self.assertEqual(balde['099.099.099']['balde'], 'confere')       # zero implícito
        self.assertEqual(res['resumo']['confere'], 4)
        self.assertEqual(res['resumo']['total'], 8)


class TestAcoesEmMassa(SGEATestCase):
    def test_bulk_delete_parcial_reporta_bloqueados_com_motivo(self):
        token = self.login()
        # 2 centros livres + 1 em uso por um veículo
        ids = []
        for nome in ('CC-A', 'CC-B', 'CC-USADO'):
            status, cc = self.request('POST', '/api/centros-custo', {'nome': nome}, token)
            self.assertEqual(status, 201, cc); ids.append(cc['id'])
        status, veic = self.request('POST', '/api/frota',
                                    {'numero': 'V1', 'centro_custo_id': ids[2]}, token)
        self.assertEqual(status, 201, veic)
        status, d = self.request('POST', '/api/centros-custo/bulk-delete', {'ids': ids}, token)
        self.assertEqual(status, 200, d)
        self.assertEqual(len(d['excluidos']), 2)
        self.assertEqual(len(d['bloqueados']), 1)
        self.assertEqual(d['bloqueados'][0]['id'], ids[2])
        self.assertIn('veículo', d['bloqueados'][0]['motivo'])

    def test_bulk_update_ativo(self):
        token = self.login()
        ids = []
        for m in ('M1', 'M2'):
            status, f = self.request('POST', '/api/funcionarios', {'nome': f'F{m}', 'matricula': m}, token)
            self.assertEqual(status, 201, f); ids.append(f['id'])
        status, d = self.request('POST', '/api/funcionarios/bulk-update',
                                 {'ids': ids, 'patch': {'ativo': 0}}, token)
        self.assertEqual(status, 200, d)
        self.assertEqual(d['atualizados'], 2)
        status, lst = self.request('GET', '/api/funcionarios', token=token)
        for f in lst['items']:
            if f['id'] in ids:
                self.assertEqual(f['ativo'], 0)

    def test_bulk_update_ignora_coluna_desconhecida(self):
        token = self.login()
        status, f = self.request('POST', '/api/funcionarios', {'nome': 'X', 'matricula': 'Z'}, token)
        self.assertEqual(status, 201, f)
        # 'nao_existe' deve ser ignorada; sem colunas válidas => 0 atualizados
        status, d = self.request('POST', '/api/funcionarios/bulk-update',
                                 {'ids': [f['id']], 'patch': {'nao_existe': 1}}, token)
        self.assertEqual(status, 200, d)
        self.assertEqual(d['atualizados'], 0)


class TestExclusaoBloqueadaExplicaMotivo(SGEATestCase):
    def test_excluir_veiculo_vinculado_a_saida_explica_o_motivo(self):
        token = self.login()
        pid = self._criar_produto(token, qtd_por_embalagem=12)
        self.request('POST', '/api/entradas', {
            'tipo': 'compra_direta', 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid, 'quantidade_embalagem': 1, 'valor_unitario': 10}]
        }, token)
        status, veic = self.request('POST', '/api/frota', {'numero': 'V-TEST'}, token)
        self.assertEqual(status, 201, veic)
        status, sai = self.request('POST', '/api/saidas', {
            'data': '2026-07-12', 'frota_id': veic['id'],
            'itens': [{'produto_id': pid, 'quantidade': 1}]
        }, token)
        self.assertEqual(status, 201, sai)
        status, data = self.request('DELETE', f'/api/frota/{veic["id"]}', token=token)
        self.assertEqual(status, 409, data)
        self.assertIn('saída', data['error'])

    def test_excluir_centro_custo_vinculado_a_veiculo_explica_o_motivo(self):
        token = self.login()
        status, cc = self.request('POST', '/api/centros-custo', {'nome': 'CC-TEST'}, token)
        self.assertEqual(status, 201, cc)
        status, veic = self.request('POST', '/api/frota',
                                    {'numero': 'V-CC', 'centro_custo_id': cc['id']}, token)
        self.assertEqual(status, 201, veic)
        status, data = self.request('DELETE', f'/api/centros-custo/{cc["id"]}', token=token)
        self.assertEqual(status, 409, data)
        self.assertIn('veículo', data['error'])

    def test_excluir_funcionario_vinculado_a_saida_explica_o_motivo(self):
        token = self.login()
        pid = self._criar_produto(token, qtd_por_embalagem=12)
        self.request('POST', '/api/entradas', {
            'tipo': 'compra_direta', 'data_entrega': '2026-07-01',
            'itens': [{'produto_id': pid, 'quantidade_embalagem': 1, 'valor_unitario': 10}]
        }, token)
        status, func = self.request('POST', '/api/funcionarios',
                                    {'nome': 'F-TEST', 'matricula': 'M1'}, token)
        self.assertEqual(status, 201, func)
        status, sai = self.request('POST', '/api/saidas', {
            'data': '2026-07-12', 'solicitante_id': func['id'],
            'itens': [{'produto_id': pid, 'quantidade': 1}]
        }, token)
        self.assertEqual(status, 201, sai)
        status, data = self.request('DELETE', f'/api/funcionarios/{func["id"]}', token=token)
        self.assertEqual(status, 409, data)
        self.assertIn('saída', data['error'])


class TestImportFrotaAprimorada(SGEATestCase):
    """Planilha CONTROLE DE FROTA aprimorada: colunas de identificação (Fiorilli)
    e centro de custo no formato 'N - NOME' (casado por código)."""

    def _veiculo(self, numero):
        with server.get_db() as conn:
            return dict(conn.execute('SELECT * FROM frota WHERE numero=?', (numero,)).fetchone())

    def test_importa_campos_de_identificacao(self):
        token = self.login()
        csv = ('FROTA;PLACA;RENAVAM;CHASSI;COR;KM ATUAL FIORILLI;CATEGORIA CNH;'
               'ESPECIE TCE;POTENCIA/CILINDRADA;LOTACAO FIORILLI;SITUACAO FIORILLI;OBSERVACAO DE QUALIDADE\n'
               '1;GJL6D26;01284762677;9BRB33BE4N2088582;PRETA;141818;B;PASSAGEIRO AUTOMOVEL;'
               '**/177CV/1987;5;ATIVO;revisado')
        status, resp = self.request('POST', '/api/frota/import', {'csv': csv, 'criar_centros': True}, token=token)
        self.assertEqual(status, 200, resp)
        v = self._veiculo('1')
        self.assertEqual(v['renavam'], '01284762677')
        self.assertEqual(v['chassi'], '9BRB33BE4N2088582')
        self.assertEqual(v['cor'], 'PRETA')
        self.assertEqual(v['situacao'], 'ATIVO')
        self.assertEqual(v['observacao'], 'revisado')

    def test_centro_casa_por_codigo_sem_duplicar(self):
        token = self.login()
        # centro já cadastrado com código 3 e nome curto (como vem do import de centros)
        status, cc = self.request('POST', '/api/centros-custo',
                                   {'codigo': '3', 'nome': 'GABINETE DO PREFEITO'}, token)
        self.assertEqual(status, 201, cc)
        antes = len(self.request('GET', '/api/centros-custo', token=token)[1]['items'])
        # planilha traz "3 - GABINETE DO PREFEITO E DEPENDENCIA" (nome diferente)
        csv = 'FROTA;PLACA;CENTRO DE CUSTO\n7;ABC1D23;3 - GABINETE DO PREFEITO E DEPENDENCIA'
        status, resp = self.request('POST', '/api/frota/import', {'csv': csv, 'criar_centros': True}, token=token)
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp['centros_criados'], 0, 'nao deve duplicar: casou pelo codigo')
        depois = len(self.request('GET', '/api/centros-custo', token=token)[1]['items'])
        self.assertEqual(antes, depois)
        self.assertEqual(self._veiculo('7')['centro_custo_id'], cc['id'])

    def test_centro_sem_prefixo_cria_com_codigo(self):
        token = self.login()
        csv = 'FROTA;PLACA;CENTRO DE CUSTO\n8;XYZ9K88;10 - TRANSPORTE RODOVIARIO'
        status, resp = self.request('POST', '/api/frota/import', {'csv': csv, 'criar_centros': True}, token=token)
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp['centros_criados'], 1)
        with server.get_db() as conn:
            cc = dict(conn.execute("SELECT codigo, nome FROM centros_custo WHERE nome='TRANSPORTE RODOVIARIO'").fetchone())
        self.assertEqual(cc['codigo'], '10')  # código extraído do prefixo


class TestImportFrotaNaoApagaDado(SGEATestCase):
    """Regressão do eixo perda de dado (auditoria 2026-07-24).

    A planilha CONTROLE DE FROTA é atualizada aos poucos e reimportada inteira.
    Célula vazia chegava aqui como '' e o UPDATE gravava por cima, apagando a
    peça que já estava cadastrada.
    """

    CABECALHO = ('FROTA;PLACA;MARCA;MODELO;COMBUSTIVEL;'
                 'FILTRO AR CABINE;FILTRO AR MOTOR;OLEO DE MOTOR')

    def _importar(self, token, linha):
        status, resp = self.request('POST', '/api/frota/import',
                                    {'csv': f'{self.CABECALHO}\n{linha}', 'criar_centros': False},
                                    token=token)
        self.assertEqual(status, 200, resp)
        return resp

    def _veiculo(self, numero):
        with server.get_db() as conn:
            return dict(conn.execute('SELECT * FROM frota WHERE numero=?', (numero,)).fetchone())

    def test_celula_em_branco_nao_apaga_valor_cadastrado(self):
        token = self.login()
        self._importar(token, '901;AAA1A11;VW;Gol;Gasolina;WEGA WP9014;TECFIL ARL9010;LUBRAX 15W40')
        self._importar(token, '901;AAA1A11;VW;Gol;Gasolina;;;')          # setor ainda não preencheu
        v = self._veiculo('901')
        self.assertEqual(v['filtro_ar_cabine'], 'WEGA WP9014')
        self.assertEqual(v['filtro_ar_motor'], 'TECFIL ARL9010')
        self.assertEqual(v['oleo_motor'], 'LUBRAX 15W40')

    def test_valor_novo_continua_sobrescrevendo(self):
        # A guarda acima não pode congelar o importador: valor preenchido atualiza.
        token = self.login()
        self._importar(token, '902;BBB2B22;VW;Gol;Gasolina;WEGA WP9014;TECFIL ARL9010;LUBRAX 15W40')
        self._importar(token, '902;BBB2B22;VW;Gol;Flex;WEGA WP9099;;LUBRAX 20W50')
        v = self._veiculo('902')
        self.assertEqual(v['combustivel'], 'Flex')
        self.assertEqual(v['filtro_ar_cabine'], 'WEGA WP9099')
        self.assertEqual(v['filtro_ar_motor'], 'TECFIL ARL9010')   # em branco no CSV: mantém
        self.assertEqual(v['oleo_motor'], 'LUBRAX 20W50')


class TestBackupNaoVazaCredencial(SGEATestCase):
    """Regressão do eixo perda de dado (auditoria 2026-07-24).

    O backup JSON exportava `sys_settings` inteiro, e ali mora a senha do SMTP
    do sistema (texto puro) e a chave do Portal da Transparência. O arquivo sai
    do servidor — o manual orienta enviá-lo a outra máquina —, então essas
    credenciais circulavam junto. Restaurar não as perde: o que o arquivo não
    traz é preservado como já está no banco.
    """

    SEGREDO = 'SENHA-SMTP-DO-SISTEMA-XYZ'

    def _gravar_segredo(self):
        with server.get_db() as conn:
            conn.execute("INSERT OR REPLACE INTO sys_settings (key,value) VALUES ('smtp_pass',?)",
                         (self.SEGREDO,))
            conn.commit()

    def _ler_segredo(self):
        with server.get_db() as conn:
            row = conn.execute("SELECT value FROM sys_settings WHERE key='smtp_pass'").fetchone()
        return row['value'] if row else None

    def test_backup_nao_contem_a_senha_do_smtp(self):
        token = self.login()
        self._gravar_segredo()
        status, backup = self.request('GET', '/api/backup', token=token)
        self.assertEqual(status, 200)
        self.assertNotIn(self.SEGREDO, json.dumps(backup, ensure_ascii=False),
                         'senha do SMTP do sistema vazou no arquivo de backup')

    def test_restaurar_preserva_a_senha_do_smtp(self):
        token = self.login()
        self._gravar_segredo()
        _, backup = self.request('GET', '/api/backup', token=token)
        self.assertEqual(self.request('POST', '/api/backup/restore', backup, token=token)[0], 200)
        self.assertEqual(self._ler_segredo(), self.SEGREDO,
                         'restaurar backup apagou a senha do SMTP do sistema')


class TestSenhaPadraoObrigatoria(SGEATestCase):
    """Regressão do eixo permissão/sigilo (auditoria 2026-07-24).

    A troca de senha obrigatória existia só no navegador: quem falasse direto
    com a API entrava com a senha padrão (que está no README e no manual) e
    usava o sistema inteiro, rotas de administrador inclusive.
    """

    def _usuario_pendente(self):
        adm = self.login()
        self.request('POST', '/api/usuarios',
                     {'username': 'pendente', 'nome': 'Pendente',
                       'password': 'senha123', 'senha': 'senha123', 'admin': True}, token=adm)
        with server.get_db() as conn:
            uid = conn.execute("SELECT id FROM usuarios WHERE username='pendente'").fetchone()['id']
            conn.execute('UPDATE usuarios SET must_change_password=1 WHERE id=?', (uid,))
            conn.commit()
        st, log = self.request('POST', '/api/auth/login', {'username': 'pendente', 'password': 'senha123'})
        self.assertEqual(st, 200, log)
        return log['token'], uid

    def test_api_recusa_enquanto_a_senha_nao_for_trocada(self):
        tok, _ = self._usuario_pendente()
        for rota in ('/api/produtos', '/api/usuarios', '/api/backup'):
            st, _ = self.request('GET', rota, token=tok)
            self.assertEqual(st, 403, f'{rota} respondeu {st} com a senha padrão pendente')

    def test_libera_o_que_a_tela_de_troca_precisa(self):
        tok, uid = self._usuario_pendente()
        self.assertEqual(self.request('GET', '/api/auth/me', token=tok)[0], 200)
        st, _ = self.request('PUT', f'/api/usuarios/{uid}', {'password': 'TrocadaAgora#2026'}, token=tok)
        self.assertEqual(st, 200, 'não deu para trocar a própria senha')
        st, log = self.request('POST', '/api/auth/login',
                               {'username': 'pendente', 'password': 'TrocadaAgora#2026'})
        self.assertEqual(st, 200)
        self.assertEqual(self.request('GET', '/api/produtos', token=log['token'])[0], 200,
                         'sistema continuou bloqueado depois de trocar a senha')


class TestChavePortalSoAdmin(SGEATestCase):
    """Regressão do eixo permissão/sigilo (auditoria 2026-07-24).

    `portal_transparencia_key` é credencial de API, mas estava na lista de
    campos graváveis por /api/settings/org — rota aberta a qualquer usuário
    autenticado (Dados de Organização, por decisão de projeto). Um usuário
    comum sobrescrevia a chave do órgão.
    """

    def _chave(self):
        with server.get_db() as conn:
            row = conn.execute("SELECT value FROM sys_settings WHERE key='portal_transparencia_key'").fetchone()
        return row['value'] if row else None

    def _comum(self):
        # O banco é compartilhado pela suíte inteira: o usuário criado aqui é
        # removido no fim, senão sobra para o teste de wipe, que confere quantos
        # usuários existem.
        adm = self.login()
        self.request('POST', '/api/usuarios',
                     {'username': 'semadmin', 'nome': 'Sem Admin', 'password': 'senha123',
                      'senha': 'senha123', 'admin': False}, token=adm)
        self.addCleanup(self._remover_semadmin)
        st, log = self.request('POST', '/api/auth/login', {'username': 'semadmin', 'password': 'senha123'})
        self.assertEqual(st, 200, log)
        return adm, log['token']

    def _remover_semadmin(self):
        with server.get_db() as conn:
            conn.execute("DELETE FROM usuarios WHERE username='semadmin'")
            conn.commit()

    def test_admin_grava_a_chave(self):
        adm, _ = self._comum()
        st, _ = self.request('PUT', '/api/settings', {'portal_transparencia_key': 'CHAVE-DO-ORGAO'}, token=adm)
        self.assertEqual(st, 200)
        self.assertEqual(self._chave(), 'CHAVE-DO-ORGAO')

    def test_usuario_comum_nao_sobrescreve_a_chave(self):
        adm, tok = self._comum()
        self.request('PUT', '/api/settings', {'portal_transparencia_key': 'CHAVE-DO-ORGAO'}, token=adm)
        # pela rota aberta de Dados de Organização (que ele pode usar para o resto)
        st, _ = self.request('PUT', '/api/settings/org',
                             {'orgao': 'Prefeitura de Teste',
                              'portal_transparencia_key': 'CHAVE-DO-INVASOR'}, token=tok)
        self.assertEqual(st, 200)
        self.assertEqual(self._chave(), 'CHAVE-DO-ORGAO', 'usuário comum sobrescreveu a credencial')
        # e o campo que ele PODE gravar continua funcionando
        st, cfg = self.request('GET', '/api/settings', token=tok)
        self.assertEqual(cfg.get('orgao'), 'Prefeitura de Teste')
        self.assertNotIn('portal_transparencia_key', cfg)


class TestAuditoriaDeConfiguracao(SGEATestCase):
    """Achado 9 do eixo permissão/sigilo (auditoria 2026-07-24).

    Dados de Organização e brasão seguem abertos a qualquer usuário autenticado
    — decisão de projeto —, mas saem em todo documento gerado. Sem registro na
    trilha, uma alteração no nome do órgão ou no brasão aparecia em documento
    oficial sem rastro de quem fez.
    """
    def _ids_config(self):
        with server.get_db() as conn:
            return {r['id'] for r in conn.execute(
                "SELECT id FROM audit_global WHERE type='CONFIG_ALTERADA'")}

    def _novos_desde(self, ids_antes):
        # Compara por conjunto de ids, não por contagem: o banco é compartilhado
        # pela suíte e outros testes também mexem em configuração.
        with server.get_db() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM audit_global WHERE type='CONFIG_ALTERADA'")
                if r['id'] not in ids_antes]

    def test_alterar_dados_da_organizacao_gera_evento(self):
        token = self.login()
        antes = self._ids_config()
        st, _ = self.request('PUT', '/api/settings/org',
                             {'orgao': f'Prefeitura {uuid.uuid4().hex[:8]}'}, token=token)
        self.assertEqual(st, 200)
        novos = self._novos_desde(antes)
        self.assertEqual(len(novos), 1, 'alteração não entrou na trilha')
        self.assertIn('orgao', novos[0]['detail'])
        self.assertEqual(novos[0]['label'], 'Dados da organização alterados')

    def test_reenviar_os_mesmos_valores_nao_polui_a_trilha(self):
        # A tela reenvia todos os campos a cada "Salvar"; sem alteração real não
        # deve virar evento.
        token = self.login()
        fixo = f'Prefeitura {uuid.uuid4().hex[:8]}'
        self.request('PUT', '/api/settings/org', {'orgao': fixo}, token=token)
        antes = self._ids_config()
        self.request('PUT', '/api/settings/org', {'orgao': fixo}, token=token)
        self.assertEqual(self._novos_desde(antes), [], 'reenvio sem alteração gerou evento')

    def test_alterar_brasao_gera_evento(self):
        token = self.login()
        antes = self._ids_config()
        st, _ = self.request('PUT', '/api/settings/brasao',
                             {'brasao_dataurl': 'data:image/png;base64,' + uuid.uuid4().hex}, token=token)
        self.assertEqual(st, 200)
        novos = self._novos_desde(antes)
        self.assertEqual(len(novos), 1)
        self.assertEqual(novos[0]['label'], 'Brasão alterado')


class TestSenhaPadraoMarcadaNoBoot(SGEATestCase):
    """Regressão do eixo permissão/sigilo (auditoria 2026-07-24).

    Quem instalou antes da coluna must_change_password existir recebeu 0 pelo
    DEFAULT do ALTER TABLE: ficou com a senha do manual e sem o bloqueio do
    servidor, porque a marca de troca só é gravada na criação do admin. O boot
    precisa remarcar quem continua na senha padrão.
    """

    def _limpa(self):
        with server.get_db() as conn:
            conn.execute("DELETE FROM usuarios WHERE username='antigo'")
            conn.execute("UPDATE usuarios SET must_change_password=0 WHERE username='admin'")
            conn.commit()

    def _cria_e_reinicia(self, senha):
        self.addCleanup(self._limpa)
        with server.get_db() as conn:
            conn.execute(
                'INSERT INTO usuarios (username,nome,senha_hash,admin,ativo,must_change_password)'
                ' VALUES (?,?,?,0,1,0)',
                ('antigo', 'Instalacao antiga', server._hash_password(senha)))
            conn.commit()
        server.init_db()   # o que acontece a cada início do servidor
        with server.get_db() as conn:
            return conn.execute(
                "SELECT must_change_password FROM usuarios WHERE username='antigo'"
            ).fetchone()['must_change_password']

    def test_boot_marca_quem_ficou_na_senha_padrao(self):
        self.assertEqual(self._cria_e_reinicia('admin123'), 1,
                         'conta com a senha padrão seguiu sem exigir troca')

    def test_boot_nao_mexe_em_quem_ja_trocou(self):
        self.assertEqual(self._cria_e_reinicia('OutraSenha#2026'), 0,
                         'exigiu troca de quem já tinha saído da senha padrão')


class TestRecusaSenhaPadrao(SGEATestCase):
    """Não deixa definir a senha de fábrica como NOVA senha (ver sgx_base.eh_senha_padrao)."""

    def test_recusa_admin123_como_nova_senha(self):
        tok = self.login()
        with server.get_db() as conn:
            uid = conn.execute("SELECT id FROM usuarios WHERE username='admin'").fetchone()['id']
        st, r = self.request('PUT', f'/api/usuarios/{uid}', {'password': 'admin123'}, token=tok)
        self.assertEqual(st, 400, r)
        self.assertIn('padrão', (r or {}).get('error', ''))


class TestSyncFornecedor(SGEATestCase):
    """Cadastro de fornecedor compartilhado (2026-07): export + sync peer por CNPJ,
    last-write-wins com revisão manual (marca d'água syncedAt). Espelho de SGCD/SGCA.
    SGEA já usa o schema JSON `data` do fornecedor (paridade), sem migração."""

    def _set_data(self, cnpj_like, **kv):
        with server.get_db() as conn:
            row = conn.execute("SELECT id,data FROM fornecedores WHERE cnpj LIKE ?", (cnpj_like,)).fetchone()
            d = json.loads(row['data']); d.update(kv)
            conn.execute("UPDATE fornecedores SET data=? WHERE id=?", (json.dumps(d), row['id'])); conn.commit()

    def test_export_envelope(self):
        tok = self.login()
        self.request('POST', '/api/fornecedores', {'cnpj': '90.201.001/0001-00', 'razao_social': 'ExpS', 'updatedAt': 1000}, tok)
        st, d = self.request('GET', '/api/fornecedores/export', token=tok)
        self.assertEqual(st, 200)
        self.assertEqual((d['_sgx'], d['tipo']), ('SGEA', 'fornecedores'))

    def test_preview_apply_e_preserva_ativo(self):
        tok = self.login()
        self.request('POST', '/api/fornecedores', {'cnpj': '90.202.001/0001-00', 'razao_social': 'Base', 'ativo': 1, 'updatedAt': 1000}, tok)
        self._set_data('90.202.001%', syncedAt=1000)
        arq = {'tipo': 'fornecedores', 'fornecedores': [
            {'cnpj': '90.202.002/0001-00', 'razao_social': 'Novo', 'updatedAt': 2000},
            {'cnpj': '90.202.001/0001-00', 'razao_social': 'Base Ltda', 'updatedAt': 5000}]}
        st, prev = self.request('POST', '/api/fornecedores/sync/preview', arq, token=tok)
        self.assertEqual((prev['inserir'], prev['atualizar'], len(prev['conflitos'])), (1, 1, 0))
        st, ap = self.request('POST', '/api/fornecedores/sync/apply', arq, token=tok)
        self.assertEqual((ap['novos'], ap['atualizados']), (1, 1))
        st, lst = self.request('GET', '/api/fornecedores?per=2000', token=tok)
        base = next(f for f in lst['items'] if (f.get('cnpj') or '').startswith('90.202.001'))
        self.assertEqual(base['razao_social'], 'Base Ltda')
        self.assertEqual(base.get('ativo'), 1)   # campo local do SGEA preservado no merge

    def test_conflito_resolve_arquivo(self):
        tok = self.login()
        self.request('POST', '/api/fornecedores', {'cnpj': '90.203.001/0001-00', 'razao_social': 'Local', 'updatedAt': 5000}, tok)
        self._set_data('90.203.001%', syncedAt=1000)
        arq = {'tipo': 'fornecedores', 'fornecedores': [{'cnpj': '90.203.001/0001-00', 'razao_social': 'Remoto', 'updatedAt': 3000}]}
        st, prev = self.request('POST', '/api/fornecedores/sync/preview', arq, token=tok)
        self.assertEqual(len(prev['conflitos']), 1)
        st, ap = self.request('POST', '/api/fornecedores/sync/apply',
                              {**arq, 'resolver': {'90203001000100': 'arquivo'}}, token=tok)
        self.assertEqual(ap['conflitos_aplicados'], 1)
        st, lst = self.request('GET', '/api/fornecedores?per=2000', token=tok)
        alvo = next(f for f in lst['items'] if (f.get('cnpj') or '').startswith('90.203.001'))
        self.assertEqual(alvo['razao_social'], 'Remoto')

    def test_arquivo_invalido(self):
        tok = self.login()
        self.assertEqual(self.request('POST', '/api/fornecedores/sync/preview', {'foo': 1}, token=tok)[0], 400)


class TestMotorErros(SGEATestCase):
    """Motor de captura e tratamento de erros (portado do piloto SGCD)."""

    def _raw(self, method, path, data, token=None):
        conn = http.client.HTTPConnection('127.0.0.1', PORT, timeout=10)
        hdrs = {'Content-Type': 'application/json'}
        if token: hdrs['Authorization'] = f'Bearer {token}'
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse(); body = resp.read(); conn.close()
        try: return resp.status, json.loads(body) if body else None
        except ValueError: return resp.status, body

    def test_param_invalido_400(self):
        tok = self.login()
        self.assertEqual(self.request('GET', '/api/fornecedores?per=abc', token=tok)[0], 400)

    def test_log_client_sem_auth_204(self):
        st, _ = self._raw('POST', '/api/log/client',
                          json.dumps({'msg': 'boom teste', 'view': 'view-x'}).encode())
        self.assertEqual(st, 204)

    def test_log_client_chega_no_log_e_diagnostico(self):
        tok = self.login()
        marca = f'erro-teste-{uuid.uuid4().hex[:8]}'
        self._raw('POST', '/api/log/client', json.dumps({'msg': marca, 'view': 'view-y'}).encode())
        caminho = server.sgx_base.caminho_log_erros(server._DATA_DIR, 'SGEA')
        with open(caminho, encoding='utf-8', errors='replace') as f:
            self.assertIn(marca, f.read())
        st, d = self.request('GET', '/api/diagnostico/erros', token=tok)
        self.assertEqual(st, 200)
        self.assertTrue(any('cliente-js' in g.get('tipo', '') for g in d['erros']))

    def test_diagnostico_so_admin(self):
        admin = self.login()
        self.request('POST', '/api/usuarios', {'username': 'u_diag_ea', 'nome': 'U', 'password': 'senha123'}, token=admin)
        comum = self.request('POST', '/api/auth/login', {'username': 'u_diag_ea', 'password': 'senha123'})[1]['token']
        self.assertEqual(self.request('GET', '/api/diagnostico/erros', token=comum)[0], 403)


class TestBackupCofre(SGEATestCase):
    """Padronização do backup (2026-07): envelope único e Cofre .zip via sgx_base.
    SGEA não tem anexos, então o Cofre é um .zip só com banco.db. O restore aceita
    o .db legado (retrocompat com backups já gravados)."""

    def _raw(self, method, path, data, token):
        conn = http.client.HTTPConnection('127.0.0.1', PORT, timeout=15)
        hdrs = {'Content-Length': str(len(data))}
        if token: hdrs['Authorization'] = f'Bearer {token}'
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse(); body = resp.read(); conn.close()
        try: return resp.status, json.loads(body)
        except ValueError: return resp.status, body

    def test_export_tem_envelope_novo(self):
        token = self.login()
        st, j = self.request('GET', '/api/backup', token=token)
        self.assertEqual(st, 200)
        self.assertEqual(j.get('_sgx'), 'SGEA')
        self.assertNotIn('usuarios', j)   # admin único: contas não viajam no JSON

    def test_cofre_e_zip_com_banco(self):
        token = self.login()
        st, raw = self.request('GET', '/api/backup/db', token=token)
        self.assertEqual(st, 200)
        self.assertEqual(raw[:4], b'PK\x03\x04')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertEqual(z.namelist(), ['banco.db'])   # SGEA não embute uploads

    def test_restaura_cofre_zip(self):
        token = self.login()
        cod = f'COFRE.{uuid.uuid4().hex[:8]}'
        self.request('POST', '/api/produtos', {'codigo_fiorilli': cod, 'nome': 'Produto do Cofre'}, token=token)
        _, raw = self.request('GET', '/api/backup/db', token=token)
        st, d = self._raw('POST', '/api/backups/db/restore', raw, token)
        self.assertEqual(st, 200, d)
        st, listado = self.request('GET', '/api/produtos', token=token)
        self.assertTrue(any(p.get('codigo_fiorilli') == cod for p in listado['items']))

    def test_restore_aceita_db_legado(self):
        token = self.login()
        legado = os.path.join(server.BACKUP_DIR, 'legado.db')
        s = sqlite3.connect(server.DB_PATH); k = sqlite3.connect(legado)
        try:
            with k: s.backup(k)
        finally:
            s.close(); k.close()
        with open(legado, 'rb') as f: db_bytes = f.read()
        os.remove(legado)
        st, d = self._raw('POST', '/api/backups/db/restore', db_bytes, token)
        self.assertEqual(st, 200, d)

    def test_arquivos_invalidos_recusados(self):
        token = self.login()
        self.assertEqual(self.request('POST', '/api/backup/restore', {'foo': 1}, token=token)[0], 400)
        self.assertEqual(self._raw('POST', '/api/backups/db/restore', b'lixo', token)[0], 400)


if __name__ == '__main__':
    unittest.main()
