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
  timeout: 30_000,
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
