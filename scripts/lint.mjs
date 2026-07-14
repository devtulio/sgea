// Extrai os <script> do SGEA.html e roda ESLint (no-undef) sobre o resultado.
// Não faz parte do runtime do sistema — é só uma checagem de desenvolvimento.
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ESLint } from 'eslint';

const htmlPath = join(import.meta.dirname, '..', 'SGEA.html');
const html = readFileSync(htmlPath, 'utf-8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);

if (!scripts.length) {
  console.error('Nenhum <script> encontrado em SGEA.html');
  process.exit(1);
}

const baseJsPath = join(import.meta.dirname, '..', 'base.js');
scripts.unshift(readFileSync(baseJsPath, 'utf-8'));

const tmpDir = mkdtempSync(join(tmpdir(), 'sgea-lint-'));
const tmpFile = join(tmpDir, 'sgea.js');
writeFileSync(tmpFile, scripts.join('\n;\n'));

const eslint = new ESLint({
  cwd: tmpDir,
  overrideConfigFile: join(import.meta.dirname, '..', 'eslint.config.js'),
});
const results = await eslint.lintFiles([tmpFile]);
const formatter = await eslint.loadFormatter('stylish');
const output = formatter.format(results.map(r => ({ ...r, filePath: 'SGEA.html (script extraído)' })));

const errorCount = results.reduce((n, r) => n + r.errorCount, 0);
if (output.trim()) console.log(output);
console.log(errorCount === 0 ? '✔ Nenhum erro encontrado.' : `✖ ${errorCount} erro(s) encontrado(s).`);
process.exit(errorCount === 0 ? 0 : 1);
