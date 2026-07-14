# Changelog — SGEA
## Sistema de Gestão de Estoque do Almoxarifado
> Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/)
> Versionamento semântico: [SemVer](https://semver.org/lang/pt-BR/)

---

## [0.11.4] — 2026-07-14

### Corrigido
- **Cabeçalho de título + ações de cada tela (`.dash-top`) sem nenhum estilo** — a classe não estava definida no esqueleto compartilhado (`_esqueleto/base.css`, só a classe morta `.view-top` existia lá) nem localmente no SGEA (removida por engano numa correção anterior de outra sessão). Corrigido definindo `.dash-top` em `base.css`, aplicando-se automaticamente aqui — flex, espaçamento e título em maiúsculas voltam a aparecer corretamente

## [0.11.3] — 2026-07-14

### Removido
- **Handler local de Tab-trap dentro do modal aberto, duplicado do listener genérico do esqueleto compartilhado (`base.js`)** — ficava dentro da IIFE de foco automático dos modais (que continua local, pois gerencia o retorno de foco). SGEA não tinha handler local de Enter/Espaço (já dependia do genérico). Mesmo padrão já adotado pelo SGDP ao migrar para o esqueleto

## [0.11.2] — 2026-07-14

### Corrigido
- **`customConfirm()` travava para sempre ao fechar por Esc ou clique fora do overlay** — os dois atalhos de fechamento globais do esqueleto compartilhado (`base.js`) só escondiam `#confirm-overlay` sem resolver a Promise nem remover os listeners dos botões OK/Cancelar, deixando qualquer `await customConfirm(...)` pendurado e vazando listeners a cada abertura. Corrigido para clicar no botão Cancelar (que sempre resolve corretamente e limpa os listeners) em vez de só esconder o overlay. Corrigido na fonte compartilhada (`_esqueleto/base.js`) e propagado aos 4 sistemas via `sync.py`

## [0.11.1] — 2026-07-13

### Corrigido
- **Fieldsets da aba Configurações limitados a uma largura fixa (420/560/640px)** deixavam uma faixa vazia grande à direita do painel em telas maiores — removida a restrição de largura em todas as abas (Interface, Organização, Comunicação, Dados, Segurança), os grupos agora ocupam toda a largura do painel, como nos sistemas irmãos
- **Aba Segurança sem o agrupamento em fieldset** que as demais abas têm — campos de troca de senha agora dentro de um fieldset "Alterar Minha Senha", igual ao padrão do SGCA
- **Opção "Normal" do Tamanho da Fonte sem descrição**, diferente das demais opções ("Pequena — mais itens visíveis", "Grande — melhor legibilidade") — agora "Normal — padrão do sistema"

## [0.11.0] — 2026-07-13

### Adicionado
- **Relatório de Backup e Integridade** — novo botão na aba Dados de Configurações gera um documento imprimível com status do backup automático, tamanhos em disco, contagens gerais do sistema (produtos, entradas, saídas, lotes, usuários, cadastros de apoio) e os eventos recentes de backup/restauração/reset, no mesmo padrão dos sistemas irmãos
- **Auditoria de restauração e reset de fábrica** — restaurar um backup (JSON ou .db) e o reset de fábrica agora registram um evento na trilha de auditoria, o que antes não acontecia

## [0.10.0] — 2026-07-13

### Adicionado
- **Campos CPF, E-mail, Cargo e Matrícula no cadastro de usuários** — modal de "Novo Usuário"/"Editar Usuário" reescrito no padrão dos sistemas irmãos (largura 560px, ordem dos campos, opção "Ativo" escondida ao criar usuário novo), com máscara de CPF e as novas colunas exibidas na listagem de usuários

## [0.9.0] — 2026-07-13

### Alterado
- **Cor institucional (padrão) trocada de verde para azul-marinho** (`#1a3a6b`) — passa a usar exatamente a mesma cor institucional do SGCD/SGCA/SGDP em toda a interface (barra lateral, botões, login, manual). As opções alternativas "Azul", "Verde" e "Roxo" já eram idênticas às dos sistemas irmãos e não mudaram

## [0.8.0] — 2026-07-13

### Adicionado
- **Som ao clicar em botões** — mesmo efeito sonoro (Web Audio API, sem arquivos externos) dos sistemas irmãos: um clique curto em qualquer botão, um acorde ascendente em ações de sucesso e um som descendente em erros

### Alterado
- **Opções de "Cor de Destaque" nas Configurações agora seguem exatamente o padrão visual do SGCD** — cada opção de rádio (Institucional, Azul, Verde, Roxo) usa a cor correspondente na própria marcação de seleção, igual aos sistemas irmãos

## [0.7.0] — 2026-07-13

### Adicionado
- **Painel de configuração da animação de fundo na tela de login** — botão de engrenagem abre um painel com controles de número de partículas, distância de conexão e velocidade, com persistência em localStorage e botão "Restaurar padrões" (mesmo padrão do SGCD/SGCA/SGDP; mantida a versão mais simples do SGEA, sem interação com o mouse)

## [0.6.0] — 2026-07-13

### Alterado — Padronização do esqueleto de navegação (padrão SGCD)
- **Cabeçalho de tela renomeado de `.view-top` para `.dash-top`** — alinhando à nomenclatura já usada no SGCD/SGCA/SGDP
- **Navegação entre telas consolidada em um único helper `_showView(viewId, navId)`** — elimina a repetição do trio "esconder todas as views → ativar a view alvo → marcar item de menu" que existia em cada uma das 8 funções de navegação
- **Skeleton de carregamento na tela de Estoque** — placeholder animado exibido só na primeira carga (padrão idêntico ao Dashboard do SGCD/SGDP), substituído automaticamente assim que os dados chegam

## [0.5.1] — 2026-07-13

### Adicionado
- **Data de hoje na sidebar** — abaixo da busca global, mostra o dia da semana e a data por extenso (ex.: "segunda-feira, 13 de julho de 2026"), no mesmo padrão do SGCA

### Corrigido
- **Campos de Interface na aba Configurações aplicavam a mudança direto no navegador ao trocar a opção**, sem esperar o clique em Salvar (tema claro/escuro, largura do conteúdo, tamanho da fonte, cor de destaque) — divergia do padrão dos irmãos, onde essas mudanças só entram em vigor ao salvar. Agora os quatro campos só aplicam e persistem quando o botão Salvar é clicado, com o indicador de alterações não salvas pulsando enquanto isso

## [0.5.0] — 2026-07-13

### Adicionado
- **Busca global (Ctrl+K)** — botão na sidebar e atalho de teclado abrem um modal que busca em produtos, centros de custo, fornecedores, funcionários, frota e pedidos ao mesmo tempo (reaproveitando os endpoints REST já existentes, com busca `?q=` no servidor); clicar num resultado navega direto para a tela e abre o item para edição
- **Sino de notificações** — botão na barra do usuário (sidebar) mostra a contagem de lotes vencidos/vencendo nos próximos 7 dias (mesma janela do alerta diário por e-mail) e um painel com a lista; clicar num item leva à tela de Alertas de Validade

### Corrigido
- **Alinhamento fino do sistema de design com os sistemas irmãos** — título de tela agora maiúsculo (como nos irmãos), cor "Verde" da opção de destaque corrigida para o tom exato usado nos outros sistemas, borda do cabeçalho de modal, tamanho de fonte de badges, espaçamento das abas de Configurações e estilo da tabela de listagem ajustados para bater exatamente com o padrão visual da família — fecha os últimos resíduos de divergência apontados por comparação lado a lado com o SGCA

## [0.4.1] — 2026-07-12

### Corrigido
- **Paridade visual da tela de Configurações com os sistemas irmãos** — a versão 0.4.0 tinha as 7 abas mas com estrutura, nomes e ordem diferentes do padrão SGCD/SGCA/SGDP. Agora: cabeçalho fixo com "← Voltar" e um único botão "Salvar" global (com indicador visual pulsante quando há alterações não salvas), abas renomeadas e reordenadas (Interface, Organização, Comunicação, Dados, Segurança, Diagnóstico, Usuários), cada configuração agrupada em `<fieldset>` com legenda colorida e texto de ajuda, e cor de destaque com amostra circular de cor ao lado de cada opção (Institucional, Azul, Verde, Roxo — "Laranja" foi trocado por "Verde" para bater com o conjunto de opções dos irmãos)
- Botões de salvar isolados por aba (Geral, Comunicação, Backup) foram substituídos por um único `saveSettings()` que salva tudo de uma vez, como nos irmãos

## [0.4.0] — 2026-07-12

### Adicionado
- **Auditoria** — trilha de eventos (criar/editar/excluir) em todos os módulos de cadastro, produtos, entradas, saídas e usuários, com tela própria (admin) com filtros por texto, tipo e período. `user_id`/`user_nome` sempre vêm da sessão autenticada, nunca do corpo da requisição
- **Lixeira** — Entradas e Saídas excluídas ficam disponíveis para restaurar por 30 dias (purga automática depois disso); tela própria listando os dois tipos
- **SMTP** — aba Comunicação (admin) com configuração completa (host, porta, TLS/SSL, autenticação, remetente, destinatário) e botão "Testar conexão"; alerta diário automático por e-mail resumindo lotes vencidos ou vencendo nos próximos 7 dias, com controle de envio único por dia
- **Aba Dados** (evolução da aba Backup): pasta de backup customizável via diálogo nativo do Windows, restauração a partir de backup JSON ou banco `.db`, alternância de backup automático, e **Zona de Perigo** (reset de fábrica com fluxo de 3 confirmações — diálogo, frase "APAGAR TUDO" e contagem regressiva — mantendo usuários e configurações)
- **Aba Diagnóstico** — checagens de consistência client-side (saldo de lote maior que o recebido, itens de saída cuja soma não bate com os lotes consumidos, produtos sem centro de custo, código Fiorilli duplicado)
- **Aba Organização ampliada** — CNPJ do órgão e autoridade competente (nome + cargo)
- **Cor de destaque** — Institucional (verde, padrão), Azul, Roxo e Laranja, na aba Aparência

### Corrigido
- **Excluir uma entrada não zerava o saldo dos lotes que ela gerou** — o registro sumia da lista, mas o estoque continuava contando essas unidades normalmente. Agora a exclusão zera `quantidade_atual` dos lotes (seguro, pois o delete já é bloqueado se algum lote foi parcialmente consumido) e a restauração devolve o saldo original

## [0.3.0] — 2026-07-12

### Adicionado
- **Tela de login no mesmo padrão visual dos sistemas irmãos**: cartão institucional com cabeçalho colorido, card de identificação do órgão, fundo animado (rede de partículas), alternância de mostrar/ocultar senha, aviso de Caps Lock ativo, animação de "shake" e mensagem de erro real do servidor ao errar a senha, último acesso/backup no rodapé e usuário lembrado entre sessões
- **Visualização compacta/expandida** na aba Aparência — controla a largura máxima do conteúdo das telas
- **Tamanho de fonte** (Normal/Pequena/Grande) na aba Aparência, aplicado ao sistema inteiro
- **Upload de brasão do município** na aba Geral, exibido na barra lateral e sincronizado entre navegadores via `GET/PUT /api/settings/brasao`
- Endpoints públicos `GET /api/public/org-info` e `GET /api/public/last-backup`, usados pela tela de login (não exigem autenticação)

### Corrigido
- **Erro 401 de senha incorreta no login era mascarado como "servidor indisponível"** — o wrapper genérico de chamadas à API tratava qualquer 401 como sessão expirada e disparava logout automático, inclusive na própria tentativa de login; agora a rota de login é tratada à parte e mostra a mensagem real do servidor
- **Modal de troca de senha obrigatória ficava atrás da tela de login** (z-index maior do overlay de login bloqueava o clique no botão "Salvar e continuar") — a tela de login agora é escondida assim que o login é aceito, antes de decidir se mostra a troca de senha

## [0.2.0] — 2026-07-12

### Adicionado
- **Tela de Configurações**, no mesmo padrão em abas dos sistemas irmãos (SGCD/SGCA/SGDP): Geral (nome do órgão e município), Aparência (tema claro/escuro, persistido por navegador), Segurança (troca da própria senha a qualquer momento, sem depender do fluxo forçado do primeiro login), Backup e Usuários — essas duas últimas restritas a administradores
- **Endpoints `GET /api/settings` e `PUT /api/settings/org`** para dados gerais do órgão
- Menu lateral simplificado: "Usuários" e "Backup" deixaram de ser itens de navegação separados e passaram a ser abas dentro de Configurações, unificando a administração do sistema num único lugar

## [0.1.0] — 2026-07-12

### Adicionado
- **Primeira versão do sistema**, construído para substituir a planilha de controle de estoque do almoxarifado, mantendo a arquitetura (servidor Python stdlib + SQLite + frontend single-file) dos sistemas irmãos SGCD/SGCA/SGDP
- **Cadastro de Produtos** com código Fiorilli único (compatibilidade com o sistema oficial), centro de custo, fator de conversão embalagem→unidade e unidade de consumo
- **Controle de estoque por lote**, com data de validade opcional — saldo do produto é sempre a soma dos lotes com saldo, nunca um contador em cache
- **Entrada** com dois fluxos: vinculada a um Pedido (nº + código de licitação) ou compra direta (só NF, fornecedor e produto); cada item de entrada gera um lote novo
- **Saída sempre em unidade de consumo**, resolvendo a limitação da planilha de só permitir baixa por caixa/embalagem — corrige uma solicitação real do almoxarifado (retirada de poucas unidades de uma caixa fechada)
- **Consumo por FEFO** (*first-expire, first-out*) na saída — consome o lote que vence mais cedo primeiro, dividindo entre lotes quando necessário; lotes sem validade são consumidos por último, em ordem de chegada
- **Reversão de saída** — excluir uma saída devolve exatamente as quantidades consumidas aos lotes de origem
- **Exclusão de entrada bloqueada** (409) se algum de seus lotes já foi parcialmente consumido por uma saída
- **Alertas de Validade** — tela com lotes vencidos ou a vencer numa janela configurável de 30/60/90 dias
- **Cadastros de apoio**: Centros de Custo, Fornecedores (com consulta automática de CNPJ via ReceitaWS), Funcionários (solicitantes) e Frota (veículos, com vínculo opcional na saída para correlacionar combustível/peças)
- **Autenticação multiusuário** com hashing PBKDF2-HMAC-SHA256, troca de senha obrigatória no primeiro acesso e gestão de usuários pelo admin
- **Backup automático** (JSON + banco SQLite) ao encerrar a última sessão, com rotação configurável, mais backup manual e download pela tela de Backup
- **Diagnóstico e correção automática de rede** — verifica IP, porta, perfil de rede e firewall
- **Suíte de testes**: `unittest` do backend com cobertura dedicada da lógica de FEFO (consumo dividido entre lotes, ordenação por validade, estoque insuficiente com rollback, custo médio ponderado) e um teste E2E (Playwright) do fluxo completo pelo navegador

> Fora de escopo nesta versão, planejado para depois: dashboard, relatórios de consumo por período, curva ABC e importação do histórico da planilha existente.
