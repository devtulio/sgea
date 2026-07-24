// Testes E2E do fluxo real no navegador (login, cadastro, entrada, saída).
// Complementa tests/test_server.py (unittest, só backend) — aqui é HTML+JS+backend
// juntos, exatamente como um usuário usaria. Roda contra um banco/backups
// isolados (SGEA_DATA_DIR), nunca o sgea.db real.
import { defineConfig } from '@playwright/test';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const dataDir = mkdtempSync(join(tmpdir(), 'sgea-e2e-'));
const port = 3052;

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,  // 60s: runners Windows do CI ocasionalmente lentos (goto+fill consumiam os 30s)
  // Assertions que dependem de um round-trip ao servidor Python ocasionalmente
  // passam de 5s (default) sob carga nos runners Windows do GitHub. 10s dá folga
  // sem mascarar travamento real (o timeout do teste inteiro continua limitado acima).
  expect: { timeout: 10_000 },
  // Só no CI: o runner Windows do GitHub é ~5x mais lento que a máquina local e
  // ocasionalmente estoura o timeout num teste pesado, sem nada de errado no
  // código (6 quedas em ~80 execuções, sempre verdes ao repetir o MESMO commit).
  // Repetir não esconde problema: o Playwright reporta o que só passou na
  // repetição como "flaky", e teste que falha nas 3 tentativas continua
  // quebrando o build. Local segue com 0 — aqui a falha tem de doer na hora.
  retries: process.env.CI ? 2 : 0,
  fullyParallel: false, // um único servidor/banco compartilhado entre os specs
  workers: 1,
  use: {
    baseURL: `http://localhost:${port}`,
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'python server.py',
    url: `http://localhost:${port}/health`,
    reuseExistingServer: false,
    timeout: 15_000,
    env: { SGEA_DATA_DIR: dataDir, SGEA_PORT: String(port) },
  },
});
