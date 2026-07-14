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
  await page.check('input[name="ef-tipo"][value="compra_direta"]');
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
