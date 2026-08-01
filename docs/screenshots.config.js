// Configuração separada da suíte E2E: as capturas do README não são teste, não
// devem rodar no CI e não podem sujar a árvore a cada `npx playwright test`.
// Roda com:  npx playwright test -c docs/screenshots.config.js
//
// O banco é um diretório temporário novo a cada execução (SGEA_DATA_DIR), como
// nos testes: a captura NUNCA enxerga o sgea.db real. Isso é o que garante que
// nenhum dado de processo, fornecedor ou servidor vá parar num repositório
// público — e é por construção, não por cuidado na hora de tirar a foto.
import { defineConfig } from '@playwright/test';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const dataDir = mkdtempSync(join(tmpdir(), 'sgea-shots-'));
const port = 3359;   // porta propria: nao conflita com a suite E2E (3050)

export default defineConfig({
  testDir: '.',
  timeout: 120_000,
  expect: { timeout: 10_000 },
  workers: 1,
  use: {
    baseURL: `http://localhost:${port}`,
    // 1600x1000 em 1x: nitido o bastante para o README e ~4x mais leve que 2x —
    // as imagens vivem no repositorio e sao reescritas a cada nova captura.
    viewport: { width: 1600, height: 1000 },
    timezoneId: 'America/Sao_Paulo',
    locale: 'pt-BR',
  },
  webServer: {
    command: 'python server.py',
    cwd: join(import.meta.dirname, '..'),   // testDir e docs/; o servidor roda na raiz
    url: `http://localhost:${port}/health`,
    reuseExistingServer: false,
    timeout: 30_000,
    env: { SGEA_DATA_DIR: dataDir, SGEA_PORT: String(port) },
  },
});
