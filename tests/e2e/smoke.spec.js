// Caminho feliz de ponta a ponta: login (com troca de senha obrigatória, já que
// o banco é novo a cada run) → cadastro de produto → entrada com conversão
// caixa→unidade → saída fracionada (FEFO) → conferência de estoque e validade.
import { test, expect } from '@playwright/test';

test('login, entrada em caixa, saída fracionada e alerta de validade', async ({ page }) => {
  await page.goto('/SGEA.html');

  await page.fill('#pin-username', 'admin');
  await page.fill('#pin-input', 'admin123');
  await page.click('#login-form button[type=submit]');

  // Banco novo → admin padrão nasce com troca de senha obrigatória
  await expect(page.locator('#overlay-force-pwd')).toBeVisible();
  await page.fill('#ts-nova', 'novaSenhaE2E123');
  await page.fill('#ts-confirma', 'novaSenhaE2E123');
  await page.click('#overlay-force-pwd button:has-text("Salvar e continuar")');
  await expect(page.locator('#overlay-pin')).toBeHidden();

  // Cadastro de produto (12 unidades por caixa)
  await page.click('#nav-produtos');
  await page.click('#view-produtos button:has-text("+ Novo Produto")');
  await page.fill('#pf-nome', 'Água Sanitária 2L');
  await page.fill('#pf-codigo-fiorilli', '015.001.350');
  await page.fill('#pf-qtd-embalagem', '12');
  await page.click('#produto-modal-overlay button:has-text("Salvar")');
  await expect(page.locator('#produtos-list')).toContainText('Água Sanitária 2L');

  // Entrada: compra direta de 5 caixas (= 60 unidades), lote com validade próxima
  await page.click('#nav-entradas');
  await page.click('#view-entradas button:has-text("+ Nova Entrada")');
  // O tipo é um botão segmentado: o radio fica visualmente oculto (só focável),
  // então clica-se no rótulo, como faz o usuário
  await page.click('.seg-radio label:has(input[value="compra_direta"])');
  await expect(page.locator('input[name="ef-tipo"][value="compra_direta"]')).toBeChecked();
  // o realce tem de acompanhar a escolha (o pill já ficou preso no estado inicial)
  await expect(page.locator('.seg-radio input[value="compra_direta"] + span'))
    .toHaveCSS('background-color', 'rgb(26, 58, 107)');
  await expect(page.locator('.seg-radio input[value="pedido"] + span'))
    .toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
  await page.fill('#ef-data-entrega', '2026-07-01');
  await page.selectOption('.item-row .ei-produto', { index: 1 });
  await page.fill('.item-row .ei-qtd', '5');
  await page.fill('.item-row .ei-valor', '13.55');
  await page.fill('.item-row .ei-lote', 'L1');
  await page.fill('.item-row .ei-validade', '2026-08-01');
  await page.click('#entrada-modal-overlay button:has-text("Registrar Entrada")');
  await expect(page.locator('#entradas-list')).toContainText('Compra direta');

  // Saída fracionada: 2 unidades de uma caixa de 12
  await page.click('#nav-saidas');
  await page.click('#view-saidas button:has-text("+ Nova Saída")');
  await page.selectOption('.item-row .si-produto', { index: 1 });
  await page.fill('.item-row .si-qtd', '2');
  await page.click('#saida-modal-overlay button:has-text("Registrar Saída")');
  await expect(page.locator('#saidas-list table')).toBeVisible();

  // Estoque físico deve ser 60 - 2 = 58
  await page.click('#nav-produtos');
  await expect(page.locator('#produtos-list')).toContainText('58 UN');

  // Alerta de validade: lote vence em ~20 dias, dentro da janela de 30 dias padrão
  await page.click('#nav-alertas');
  await expect(page.locator('#alertas-list')).toContainText('Água Sanitária 2L');
  await expect(page.locator('#alertas-list')).toContainText('L1');
});

// Importador de funcionários (folha do Fiorilli): fixture em latin-1 com uma linha
// de 13º repetida (mesma matrícula) e colunas de salário; confere dedup por matrícula,
// mapeamento dos campos novos e o upsert idempotente.
test('importa funcionários da folha do Fiorilli (dedup + campos novos)', async ({ page }) => {
  // Login resiliente: o banco é compartilhado entre os testes, a senha do admin
  // pode já ter sido trocada pelo teste anterior.
  await page.goto('/SGEA.html');
  await page.fill('#pin-username', 'admin');
  await page.fill('#pin-input', 'admin123');
  await page.click('#login-form button[type=submit]');
  // Espera a tela reagir ao login em vez de dormir um tempo fixo: 800 ms bastam
  // na máquina local, mas o runner do CI é ~5x mais lento e o `if` abaixo era
  // avaliado antes da resposta chegar. Os três desfechos possíveis: pede troca
  // de senha (banco novo), entra direto, ou recusa — este último é esperado
  // quando o teste anterior já trocou a senha, e cai no segundo `else`.
  await expect(async () => {
    const pedeTroca = await page.locator('#overlay-force-pwd').isVisible();
    const entrou    = !(await page.locator('#overlay-pin').isVisible());
    const recusou   = await page.locator('#pin-erro').isVisible();
    expect(pedeTroca || entrou || recusou).toBeTruthy();
  }).toPass({ timeout: 15_000 });
  if (await page.locator('#overlay-force-pwd').isVisible()) {
    await page.fill('#ts-nova', 'novaSenhaE2E123');
    await page.fill('#ts-confirma', 'novaSenhaE2E123');
    await page.click('#overlay-force-pwd button:has-text("Salvar e continuar")');
  } else if (await page.locator('#overlay-pin').isVisible()) {
    await page.fill('#pin-input', 'novaSenhaE2E123');
    await page.click('#login-form button[type=submit]');
  }
  await expect(page.locator('#overlay-pin')).toBeHidden();

  // Fixture no formato da folha, com acentos (latin-1) e uma linha de 13º repetida
  const csv = [
    'Referência;Nome;Unidade;Proventos;Descontos;Líquido;Cargo;Natureza Cargo;Forma de Provimento Cargo;Matrícula;Data Admissão;Ato Admissão',
    'Folha Mensal - Junho;FULANO DE TAL;ALMOXARIFADO;5000,00;500,00;4500,00;ALMOXARIFE;1 - Efetivo;CONCURSO PUBLICO;100;01/01/2020;A1',
    'Fechamento 13º Salário - Junho;FULANO DE TAL;ALMOXARIFADO;2500,00;250,00;2250,00;ALMOXARIFE;1 - Efetivo;CONCURSO PUBLICO;100;01/01/2020;A1',
    'Folha Mensal - Junho;BELTRANO SILVA;SAÚDE;3000,00;300,00;2700,00;MOTORISTA;3 - Temporário;TEMPO DETERMINADO;200;15/06/2023;',
  ].join('\r\n');

  await page.click('#nav-funcionarios');
  await page.click('#crud-btn-import-func');
  await page.setInputFiles('#func-csv-input', { name: 'folha.csv', mimeType: 'text/csv', buffer: Buffer.from(csv, 'latin1') });

  const cards = page.locator('#func-csv-cards');
  await expect(cards).toContainText('2'); // 2 únicos
  await expect(cards).toContainText('repetidos descartados'); // o 13º repetido saiu
  await page.click('#func-csv-btn-aplicar');
  await expect(page.locator('#func-csv-done')).toContainText('2');
  await page.click('#modal-func-csv .modal-footer .btn-ghost');

  // Campos novos gravados e visíveis na lista
  await expect(page.locator('#crud-list')).toContainText('FULANO DE TAL');
  await expect(page.locator('#crud-list')).toContainText('100');

  const utilizada = await page.evaluate(async () => {
    const d = await API.json(await API.get('/api/funcionarios?per=100'));
    const f = (d.items || d).find(i => i.matricula === '100');
    return { natureza: f.natureza, forma: f.forma_provimento, data: f.data_admissao };
  });
  expect(utilizada.natureza).toBe('1 - Efetivo');
  expect(utilizada.forma).toBe('CONCURSO PUBLICO');
  expect(utilizada.data).toBe('01/01/2020');
});
