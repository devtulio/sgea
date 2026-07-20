---
version: alpha
name: familia-sgcd-design-analysis
description: >
  Sistema visual institucional compartilhado pela família SGCD/SGCA/SGDP/SGEA
  (software de gestão administrativa/jurídica para prefeitura municipal).
  Base neutra e limpa — sidebar navy institucional (#1a3a6b), superfícies
  claras em cinza-neutro, tipografia system-ui sem serifa, cantos levemente
  arredondados (8px), sombras discretas. Lê como documentação de software de
  governo: sóbrio, funcional, alto contraste (auditado WCAG 2.1 AA em
  2026-07-10), sem elementos decorativos além do brasão institucional e um
  canvas de partículas sutil na tela de login. 3 temas de destaque alternativos
  (azul/verde/roxo) e modo escuro completo, ambos escolha do usuário — nunca
  hardcoded.

colors:
  brand: "#1a3a6b"
  brand-text: "var(--brand) no claro; color-mix(in srgb, var(--brand) 40%, #b7c9de) no dark — use para TEXTO na cor da marca (nunca var(--brand) direto em texto: ilegível no modo escuro)"
  brand-light: "#e8eef7"
  brand-dark: "#102855"
  accent: "#1a3a6b"
  accent-light: "#2a5298"
  success: "#15803d"
  success-light: "#dcfce7"
  warning: "#d97706"
  warning-light: "#fef3c7"
  danger: "#dc2626"
  danger-light: "#fee2e2"
  gray-50: "#f9fafb"
  gray-100: "#f3f4f6"
  gray-200: "#e5e7eb"
  gray-300: "#d1d5db"
  gray-400: "#6b7280"
  gray-500: "#6b7280"
  gray-600: "#4b5563"
  gray-700: "#374151"
  gray-800: "#1f2937"
  gray-900: "#111827"
  bg-card: "#ffffff"

colors-dark-mode:
  gray-50: "#1a1a1a"
  gray-100: "#242424"
  gray-200: "#323232"
  gray-300: "#555550"
  gray-400: "#9ca3af"
  gray-500: "#9a9691"
  gray-600: "#9a9691"
  gray-700: "#c8c3bc"
  gray-800: "#f0ece8"
  gray-900: "#f0ece8"
  bg-card: "#2a2a2a"
  body-bg: "#1a1a1a"
  body-text: "#f0ece8"

themes-alternativos:
  # Configurações → Interface — usuário escolhe, nunca é default fixo
  azul:  { brand: "#0066CC", brand-light: "#e0eeff", brand-dark: "#0052a3", accent: "#0052a3", accent-light: "#0066CC" }
  verde: { brand: "#1a7a3c", brand-light: "#dcfce7", brand-dark: "#145e2d", accent: "#145e2d", accent-light: "#1a7a3c" }
  roxo:  { brand: "#5E2750", brand-light: "#f5edf3", brand-dark: "#44193a", accent: "#44193a", accent-light: "#5E2750" }

typography:
  font-family: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
  base-size: 16px
  size-pequena: 14px   # html.font-pequena — escolha do usuário em Configurações
  size-grande: 18px    # html.font-grande
  dash-title:
    fontSize: 1.05rem
    fontWeight: 700
    letterSpacing: 0.8px
    textTransform: uppercase
  pin-title:            # título do card de login
    fontSize: 17px
    fontWeight: 700
  label:                 # rótulos de campo de formulário
    fontSize: 0.72rem
    fontWeight: 700
    letterSpacing: 0.4px
    textTransform: uppercase
  body:
    fontSize: 0.85rem

spacing:
  radius: 8px
  radius-modal: 12px
  radius-pin-card: 16px
  sidebar-width: 220px
  shadow: "0 1px 3px rgba(0,0,0,.10), 0 1px 2px rgba(0,0,0,.06)"
  shadow-md: "0 4px 6px rgba(0,0,0,.07), 0 2px 4px rgba(0,0,0,.06)"
  shadow-lg: "0 10px 25px rgba(0,0,0,.12)"
---

# Sistema visual — família SGCD/SGCA/SGDP/SGEA

Fonte dos valores acima: `_esqueleto/base.css` (mecânica compartilhada) +
override de `--brand`/`--brand-light`/`--brand-dark`/`--accent`/`--accent-light`
em cada `SISTEMA.html` (hoje **idêntico e literal nos 4 sistemas** — navy
institucional `#1a3a6b`). Ver [[project_esqueleto_familia]] para o histórico
da migração e [[feedback_paridade_visual_familia_sgcd]] para por que esses
valores precisam ser copiados literalmente, nunca recriados "parecidos".

## Componentes canônicos (nomes de classe/id — ver `base.css` para o CSS completo)

- **Sidebar** (`#sidebar`) — fundo `--accent`, 220px, brasão 80×80 no topo, nav com item ativo em `border-left: 3px solid var(--brand)`.
- **Login** (`#overlay-pin` / `#pin-card`) — fundo full-screen `#1a1f2e`, card branco 380px com canvas de partículas atrás, header `--accent`, campos maiores (44px altura) que o resto do sistema.
- **Configurações** (`.cfg-tabs` / `.cfg-panel` / `.cfg-fieldset`) — abas horizontais, aba ativa sublinhada em `--brand`.
- **Modal** (`.overlay` / `.modal`) — header colado no topo em `--accent`, borda inferior 3px `--brand`, footer sticky.
- **Botões** — `.btn-primary` (`--brand`, hover `--brand-dark`), `.btn-outline`, `.btn-ghost`, `.btn-danger`/`.btn-success`.
- **Badges/toast/busca global (Ctrl+K)** — ver `base.css` linhas 201–240.
- **Tabela de listagem** (`.list-table-wrap` > `.list-table`) — thead cinza uppercase, zebra, hover `--brand-light`; colunas numéricas com `.col-num`, ações com `.col-actions`.
- **Stat-card de dashboard** — acento por **borda esquerda 4px** colorida (nunca anel completo nem borda no topo).

## Regras de uso

1. **Nunca declarar cor de marca fora do `<style>` específico do sistema.** `base.css` só traz um neutro de bootstrap (`#4b5563`) de propósito — cor institucional é sempre override local, e o usuário pode trocar por um dos 3 temas alternativos ou modo escuro a qualquer momento pela tela de Configurações.
2. **Copiar valores literais deste arquivo**, nunca recriar de memória — é o motivo deste arquivo existir (ver [[feedback_paridade_visual_familia_sgcd]]).
3. Ao adicionar um sistema novo à família ou uma tela nova a um existente, tudo que não for específico de domínio (login, Configurações→Aparência, sidebar, modais) segue este documento; lógica de negócio (SMTP, ICP-Brasil, PNCP, CRUD específico) não é coberta aqui — ver README de cada sistema.

## Manutenção

Este arquivo é derivado de `base.css` + dos overrides de `SISTEMA.html` — **não
é fonte de verdade própria**. Sempre que `base.css` mudar um token (cor, radius,
sombra, tipografia) ou um sistema mudar sua cor institucional, atualizar este
arquivo no mesmo commit e rodar `python sync.py` para propagar a cópia aos 4
sistemas — mesma disciplina de `base.css`/`base.js`/`sgx_base.py` (ver `README.md`
deste diretório).
