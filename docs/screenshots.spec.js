// Capturas do README. Não é teste: monta um cenário de demonstração e fotografa.
// Roda fora do CI, por configuração própria:
//
//     npx playwright test -c docs/screenshots.config.js
//
// Todo dado aqui é fictício, por decisão: as imagens vão para um repositório
// público e nada que saia daqui pode ser de um produto, fornecedor ou servidor
// real. O órgão é "Município de Exemplo/SP"; não há brasão (upload em
// Configurações, nunca embutido).
import { test, expect } from '@playwright/test';

const SHOTS = 'docs/screenshots';

const ORG = {
  orgao: 'Prefeitura Municipal de Exemplo',
  municipio: 'Município de Exemplo',
  uf: 'SP',
  nome: 'Marcos Vinícius Prado',
  cargo: 'Almoxarife',
  matricula: '1592',
};

const emDias = n => {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

// qtd_por_embalagem > 1 mostra o fracionamento (compra em caixa, consumo em unidade)
const PRODUTOS = [
  { codigo_fiorilli: '015.001.350', nome: 'Água sanitária 2L',                unidade_licitada: 'CX', qtd_por_embalagem: 12, unidade_consumo: 'UN' },
  { codigo_fiorilli: '015.002.118', nome: 'Papel higiênico rolo 300m',        unidade_licitada: 'FD', qtd_por_embalagem: 8,  unidade_consumo: 'RL' },
  { codigo_fiorilli: '021.004.077', nome: 'Luva de procedimento tam. M',      unidade_licitada: 'CX', qtd_por_embalagem: 100, unidade_consumo: 'UN' },
  { codigo_fiorilli: '033.007.412', nome: 'Álcool gel 70% — frasco 500ml',    unidade_licitada: 'CX', qtd_por_embalagem: 24, unidade_consumo: 'UN' },
  { codigo_fiorilli: '008.003.201', nome: 'Papel sulfite A4 75g',             unidade_licitada: 'CX', qtd_por_embalagem: 10, unidade_consumo: 'RESMA' },
  { codigo_fiorilli: '044.001.905', nome: 'Máscara cirúrgica tripla camada',  unidade_licitada: 'CX', qtd_por_embalagem: 50, unidade_consumo: 'UN' },
];

// Validades escalonadas: uma vencida, duas dentro da janela de alerta de 30 dias
// e o resto folgado — é o que faz a tela de Alertas e o FEFO terem o que mostrar.
const LOTES = [
  { i: 0, lote: 'L2026-114', validade: emDias(-4),  entrega: emDias(-96), nfe: '18452', forn: 0, qtd: 5,  valor: 13.55 },
  { i: 1, lote: 'L2026-097', validade: emDias(11),  entrega: emDias(-74), nfe: '18987', forn: 1, qtd: 12, valor: 78.90 },
  { i: 2, lote: 'L2026-205', validade: emDias(26),  entrega: emDias(-58), nfe: '02143', forn: 1, qtd: 8,  valor: 42.00 },
  { i: 3, lote: 'L2026-233', validade: emDias(95),  entrega: emDias(-40), nfe: '19233', forn: 0, qtd: 20, valor: 96.40 },
  { i: 4, lote: 'L2026-241', validade: emDias(280), entrega: emDias(-21), nfe: '02310', forn: 1, qtd: 30, valor: 187.50 },
  { i: 5, lote: 'L2026-256', validade: emDias(160), entrega: emDias(-7),  nfe: '19488', forn: 0, qtd: 15, valor: 29.90 },
];

// CNPJ com dígito verificador válido, de empresas inventadas.
const FORNECEDORES = [
  { id: '12908073000165', cnpj: '12.908.073/0001-65', cnpj_digits: '12908073000165', razao_social: 'DISTRIBUIDORA EXEMPLO DE MATERIAIS LTDA' },
  { id: '19131243000197', cnpj: '19.131.243/0001-97', cnpj_digits: '19131243000197', razao_social: 'COMERCIAL MODELO SUPRIMENTOS EIRELI' },
];

test('capturas do README', async ({ page }) => {
  page.on('dialog', d => d.accept());

  await page.goto('/SGEA.html');
  await page.fill('#pin-username', 'admin');
  await page.fill('#pin-input', 'admin123');
  await page.click('#login-form button[type=submit]');
  await expect(page.locator('#overlay-force-pwd')).toBeVisible();
  await page.fill('#ts-nova', 'demoSGEA2026');
  await page.fill('#ts-confirma', 'demoSGEA2026');
  await page.click('#overlay-force-pwd button:has-text("Salvar e continuar")');
  await expect(page.locator('#overlay-pin')).toBeHidden();

  // a troca de senha derruba a sessao aqui (o token antigo passa a dar 401):
  // entra de novo com a senha nova antes de semear pela API
  await page.reload();
  if (await page.locator('#pin-username').isVisible().catch(() => false)) {
    await page.fill('#pin-username', 'admin');
    await page.fill('#pin-input', 'demoSGEA2026');
    await page.click('#login-form button[type=submit]');
    await expect(page.locator('#overlay-pin')).toBeHidden();
  }

  await page.evaluate(async org => {
    const lista = await API.json(await API.get('/api/usuarios'));
    const arr = Array.isArray(lista) ? lista : lista.items;
    const eu = arr.find(u => u.username === 'admin');
    await API.put(`/api/usuarios/${eu.id}`, { nome: org.nome, cargo: org.cargo, matricula: org.matricula });
    localStorage.setItem('sgea-user', JSON.stringify(org));
  }, ORG);

  await page.evaluate(async ({ produtos, lotes, fornecedores }) => {
    for (const f of fornecedores) await API.post('/api/fornecedores', { ...f, addedAt: Date.now() });
    const ids = [];
    for (const p of produtos) {
      const r = await API.post('/api/produtos', { ...p, ativo: true });
      const d = await API.json(r);
      ids.push(d.id || d.produto?.id);
    }
    for (const l of lotes) {
      await API.post('/api/entradas', {
        tipo: 'compra_direta',
        data_entrega: l.entrega,
        fornecedor_id: fornecedores[l.forn].id,
        nfe_numero: l.nfe,
        itens: [{ produto_id: ids[l.i], quantidade_embalagem: l.qtd,
                  valor_unitario: l.valor, lote_numero: l.lote, data_validade: l.validade }],
      });
    }
  }, { produtos: PRODUTOS, lotes: LOTES, fornecedores: FORNECEDORES });

  await page.reload();
  await expect(page.locator('#overlay-pin')).toBeHidden();

  // ── 1. Estoque, com lote e validade ───────────────────────────────────────
  await page.click('#nav-produtos');
  await expect(page.locator('#produtos-list')).toContainText('Água sanitária 2L');
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${SHOTS}/estoque.png` });

  // ── 2. Entradas ───────────────────────────────────────────────────────────
  await page.click('#nav-entradas');
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${SHOTS}/entradas.png` });

  // ── 3. Alertas de validade ────────────────────────────────────────────────
  await page.click('#nav-alertas');
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${SHOTS}/alertas.png` });
});
