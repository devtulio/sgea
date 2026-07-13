// Config mínima: só pega variáveis usadas sem existir (no-undef) e afins.
// Escopo único de propósito — pegar o padrão de bug já visto duas vezes
// nesse projeto (fSt, proc): variável referenciada que nunca foi
// declarada/destruturada naquele escopo.
import globals from 'globals';

export default [
  {
    files: ['**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: globals.browser,
    },
    rules: {
      'no-undef': 'error',
      'no-unused-vars': 'off',
    },
  },
];
