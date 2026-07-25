# Changelog — SGEA
## Sistema de Gestão de Estoque do Almoxarifado
> Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/)
> Versionamento semântico: [SemVer](https://semver.org/lang/pt-BR/)

---

## [0.33.2] — 2026-07-25

### Documentação
- Badges de **DOI (Zenodo)** e **CI** adicionados ao README, em paridade com os demais sistemas (o SGEA agora é público).

---

## [0.33.1] — 2026-07-25

### Documentação
- **Repositório arquivado no Zenodo (DOI).** O SGEA passa a ter um identificador permanente de citação (concept-DOI), como os demais sistemas da família.

---

## [0.33.0] — 2026-07-25

### Alterado
- **A tela de Fornecedores virou tabela** (mesmo padrão de Funcionários/Centros de Custo), no lugar da lista de cards: colunas Razão Social, CNPJ e Situação, com **ordenação ao clicar no cabeçalho** e **seleção em massa** (excluir vários para a Lixeira). O detalhe completo do fornecedor — dados, certidões, sanções, consulta de CNPJ e CEIS/CNEP, edição — passou para uma **janela (modal)**, aberta ao clicar na linha ou em Editar.
- **Padronização visual:** as tabelas de **Auditoria** e **Reconciliação** passam a usar o mesmo estilo canônico das demais telas (cadastros, Estoque), ficando consistentes no espaçamento, cabeçalho e zebra das linhas. Sem mudança de comportamento.

### Corrigido
- **Modo escuro:** os selos de situação do fornecedor (ativa/inativa/outra) ganharam cores próprias para o tema escuro, em vez das cores claras que destoavam do fundo escuro.

---

## [0.32.0] — 2026-07-25

### Adicionado
- **As tabelas de Estoque, Entradas e Saídas agora ordenam ao clicar no cabeçalho**, igual à tela de Centros de Custo (clica para ordenar, clica de novo para inverter, com seta indicando a coluna). A coluna Estoque ordena por número.
- **Cada item da reconciliação tem um botão "Editar" que abre o cadastro do produto.** Nas linhas que divergem (ou em qualquer item já existente no SGEA), dá para abrir o cadastro direto dali, corrigir (unidade, embalagem, etc.) e, ao salvar, o extrato é reprocessado — o item se reclassifica na hora.
- **A reconciliação agora permite cadastrar no SGEA os itens que só existem no Fiorilli.** Quando o extrato traz produtos que ainda não estão no SGEA (balde "Só Fiorilli"), o administrador vê o botão **Cadastrar itens do Fiorilli**: abre uma lista para revisar e marcar quais criar, com a opção de já lançar o **saldo inicial** (uma entrada de abertura, sem validade, reversível pela tela de Entradas). Assim dá para partir de um SGEA vazio, importar a Posição do Estoque e sair com os produtos e o estoque cadastrados; nas próximas importações, os mesmos itens passam a apenas reconciliar. A quantidade vem arredondada para inteiro (o estoque do SGEA é inteiro) e a unidade é a do Fiorilli, sem conversão.
- **O cadastro de frota ganhou os dados oficiais do veículo (do Fiorilli).** Novos campos: RENAVAM, chassi, cor, KM atual, categoria da CNH, espécie (TCE), potência/cilindrada, lotação, situação e observação — aparecem na edição do veículo e na Ficha do Veículo, e alimentam a busca (por RENAVAM/chassi também).

### Alterado
- **A importação de frota passa a aceitar o arquivo `.xlsx` direto**, além do `.csv`. Basta selecionar a planilha CONTROLE DE FROTA em Excel — o sistema lê a aba **DADOS** automaticamente, sem precisar exportar para CSV antes (leitura feita no servidor, sem depender de programa externo).
- **A importação da planilha CONTROLE DE FROTA foi atualizada para a versão aprimorada.** Passa a importar os campos de identificação acima e a casar o **centro de custo pelo código** (formato "N - NOME") — antes casava pelo nome inteiro e criava centros duplicados quando a grafia variava. A reimportação continua sem apagar o que já está preenchido (célula em branco não zera).

### Corrigido
- **As telas de Auditoria e Reconciliação agora respeitam a largura "Expandida".** Elas continuavam estreitas (centralizadas) mesmo com o layout expandido selecionado, porque tinham um limite de largura interno que não era liberado no modo expandido.
- **O relatório de pendências de peças reconhece "PENDENTE - …"** (além de vazio e "FALTA INFORMAÇÃO") como peça a definir; "NÃO APLICÁVEL"/"NÃO UTILIZA" seguem contando como resolvidas.

---

## [0.31.0] — 2026-07-25

### Adicionado
- **O campo Responsável do Centro de Custo agora sugere nomes do cadastro de Funcionários.** Ao editar, o campo mostra uma lista com os funcionários cadastrados (é só começar a digitar); ainda é possível digitar um nome livre, então os responsáveis vindos da importação do Fiorilli continuam intactos.
- **Ações em massa nos cadastros (Frota, Centros de Custo e Funcionários).** Cada tela ganhou uma coluna de seleção com "selecionar todos" (respeita a busca ativa) e uma barra de ações: **Excluir** vários de uma vez (com resumo do que foi excluído e do que ficou bloqueado, e por quê), **Ativar/Inativar** em massa, **Exportar CSV** os selecionados e — só na Frota — **Reatribuir centro de custo** de vários veículos de uma vez.

### Corrigido
- **A data do e-mail de resumo diário volta ao formato brasileiro.** Estava saindo como `2026-07-25` (ISO) no assunto e no corpo; passa a `25/07/2026`.
- **Ao tentar excluir um cadastro que não pode ser removido, o aviso agora diz o porquê.** Vale para **Frota, Centros de Custo e Funcionários**: antes aparecia só "registro em uso"; agora o aviso lista a que registros o item está vinculado e quantos (ex.: "vinculado a 3 saída(s) de estoque, 2 veículo(s) da frota"). O aviso também fica mais tempo na tela para dar tempo de ler.

---

## [0.30.0] — 2026-07-25

### Alterado
- **O servidor interno foi trocado por um mais robusto (waitress).** Em uso simultâneo, o servidor anterior às vezes parava sozinho ("servidor parou"); o novo aguenta várias requisições ao mesmo tempo sem cair. O jeito de usar não muda — continua abrindo pelo mesmo atalho.

### Adicionado
- **Motor de captura e tratamento de erros.** O sistema passa a registrar falhas num arquivo de log rotativo (sem estourar o disco), separa "erro de quem usa" de "erro do programa", captura também erros do navegador e traz a tela **Erros recentes** no Diagnóstico (só para administradores). Se o programa travar de vez, o motivo fica gravado num arquivo `*_crash.log`.

### Corrigido
- **A aba de Auditoria volta a acompanhar o modo Compacto/Expandido da interface.** Antes ela ignorava a largura escolhida.

### Documentação
- Padronização do **README** e do **LICENSE** entre os sistemas da família (não altera o sistema): subseção "Menu de inicialização" unificada e igual ao código, referência aos sistemas irmãos na Descrição, seção "Documentos Gerados pelo Sistema" (antes ausente) e topics do repositório preenchidos no GitHub, e LICENSE normalizado para o template MIT canônico (LF) — o GitHub voltou a classificar o repositório como MIT.

---

## [0.29.0] — 2026-07-24

### Adicionado
- **Cadastro de fornecedores compartilhado entre os sistemas.** Agora dá para **exportar** o cadastro de fornecedores e **sincronizá-lo** com os outros sistemas da família por CNPJ: soma os novos, atualiza os que mudaram e, quando o mesmo fornecedor foi editado dos dois lados desde a última sincronização, abre uma tela para você escolher qual versão manter. Não apaga nada.

### Segurança
- **A senha de fábrica não pode mais ser definida como nova senha.** Ao trocar a senha, `admin123` (a padrão publicada no manual) é recusada — antes era possível "trocar" para ela e assim contornar a exigência de sair da senha padrão.

---

## [0.28.0] — 2026-07-24

### Alterado
- **Formato de backup do banco unificado com os demais sistemas da família** (pacote **.zip**), com leitura compatível. Backups no formato antigo (.db) continuam podendo ser restaurados.

---

## [0.27.4] — 2026-07-24

### Corrigido
- **Instalações anteriores à troca de senha obrigatória seguiam aceitando a senha de fábrica.** A exigência de trocar a senha só era gravada no momento em que o usuário administrador é criado; nos bancos que já existiam, a coluna nasceu desligada pelo padrão da migração. Ou seja: a proteção valia para instalação nova e deixava de fora justamente as que já estavam em uso, que continuavam abertas com a senha publicada no manual. O servidor passa a conferir a cada início se alguma conta ainda está na senha padrão e a exigir a troca — o que cobre também quem voltar a ela ou for cadastrado com ela.

---

## [0.27.3] — 2026-07-24

### Corrigido
- **Leitura de valores em dinheiro unificada** com o restante da família: `1.234` passa a valer mil duzentos e trinta e quatro (era interpretado como um vírgula dois) e valores negativos deixam de perder o sinal.

---

## [0.27.2] — 2026-07-24

### Adicionado
- **Alterações nos Dados da Organização e no brasão passam a ficar registradas na Trilha de Auditoria**, com autor, data e quais campos mudaram. Esses dados saem em todo documento gerado — nome do órgão, município, autoridade, brasão —, e qualquer usuário pode editá-los (segue assim, é a forma de trabalho do setor); o que faltava era o rastro de quem mudou. Reenviar a tela sem alterar nada não gera evento.

---

## [0.27.1] — 2026-07-24

### Corrigido
- **Qualquer usuário podia trocar a chave de API do Portal da Transparência.** A chave estava na lista de campos salvos junto com os Dados de Organização — tela aberta a todos por decisão de projeto —, então um usuário comum sobrescrevia a credencial do órgão e a consulta automática de sanções (CEIS/CNEP) parava de funcionar. A chave passou a ser gravada e exibida apenas para o administrador; o restante dos Dados de Organização continua aberto como antes.

---

## [0.27.0] — 2026-07-24

### Corrigido
- **A troca da senha padrão passou a valer no servidor.** A tela de "troque a senha no primeiro acesso" era só do navegador: quem conversasse diretamente com o sistema entrava com a senha padrão — que está no manual e no README — e usava tudo, inclusive as telas de administrador, enquanto ninguém tivesse trocado. Agora, com a troca pendente, o servidor só aceita as chamadas necessárias para exibir e concluir a própria troca; qualquer outra é recusada.
- **A chave de API do Portal da Transparência e a conta de e-mail do órgão apareciam para qualquer usuário.** A tela de Configurações é aberta a todos (usa os dados de organização), e junto vinham a chave do Portal, o endereço da conta de e-mail e a pasta de backup. Passaram a ir só para o administrador. A senha do e-mail nunca esteve nessa lista.

---

## [0.26.7] — 2026-07-24

### Corrigido
- **A senha do e-mail do sistema saía dentro do arquivo de backup.** O backup em JSON exportava todas as configurações, e entre elas está a senha do SMTP (guardada em texto puro) e a chave do Portal da Transparência. Como esse é o arquivo que se envia a outra máquina para sincronizar, essas credenciais circulavam junto. Elas passaram a ficar de fora. **Restaurar não as perde:** o que o arquivo não traz é preservado como já está no sistema.

---

## [0.26.6] — 2026-07-24

### Corrigido
- **Cadastrar ou importar um fornecedor ressuscitava quem estava na Lixeira.** Se o identificador de um fornecedor excluído aparecesse de novo, o registro voltava ao cadastro sem aviso.

### Alterado
- **Manual:** a seção de Configurações agora explica a diferença entre o backup em JSON (dados de trabalho, é o que se envia a outra máquina) e o backup do banco (.db), que é a cópia integral para recuperação completa.

---

## [0.26.5] — 2026-07-24

### Corrigido
- **Reimportar a planilha de frota apagava peças já cadastradas.** A planilha CONTROLE DE FROTA é atualizada aos poucos e reimportada inteira; uma coluna que o setor ainda não tinha preenchido chegava como célula vazia e **sobrescrevia com branco** o filtro, óleo ou correia que já estava no sistema. Agora célula em branco preserva o que existe — valores preenchidos continuam atualizando normalmente. Para limpar um campo de propósito, edite o veículo na tela de Frota.
- **Centro de custo do veículo não é mais perdido** quando a planilha reimportada não traz a coluna de centro de custo.

---

## [0.26.4] — 2026-07-23

### Alterado
- **Fonte única para o que os quatro sistemas repetiam.** O aviso de rodapé (`toast`) e a caixa de confirmação (`customConfirm`) existiam em cópia local em cada sistema, quase idênticas: uma correção feita em um não chegava aos outros. Passaram a vir do esqueleto compartilhado — o som continua sendo de cada sistema, através de um gancho (`_toastSom`). 
- **Margem de impressão dos documentos com fonte única.** O bloco `@page` (A4, 20 mm, "Folha N" no rodapé) estava copiado em cinco lugares nos quatro sistemas; agora é uma constante só, no esqueleto. Era exatamente o trecho que a versão anterior teve de corrigir em cinco lugares de uma vez.
- **O esqueleto compartilhado passou a ter histórico.** Os arquivos comuns (`base.css`, `base.js`, `sgx_base.py`) tinham fonte única, mas fora de qualquer repositório: um erro neles se espalhava para os quatro sistemas sem registro do que mudou nem como voltar atrás. Agora são versionados.
- **O CI acusa cópia do esqueleto editada por fora.** Alterar `base.js` dentro deste repositório funciona, passa no lint e é apagado sem aviso na próxima distribuição. O CI passou a conferir as cópias contra o manifesto `_esqueleto.sha256` e quebra o build quando divergem. Verificado nos dois sentidos: acusa edição real e ignora diferença de quebra de linha (o repositório guarda LF, o runner Windows faz checkout com CRLF).

---

## [0.26.3] — 2026-07-22

### Corrigido
- **Envio de e-mail podia prender uma thread do servidor para sempre.** O helper compartilhado `send_email_raw` abria a conexão SMTP sem `timeout`, e o padrão do Python é esperar indefinidamente; como o servidor é multithread, cada envio a um SMTP que aceita a conexão e não responde deixava uma thread presa — inclusive no resumo diário automático, que se repete todo dia. Agora o timeout é de 30 s e a falha vira mensagem de erro. Verificado contra um SMTP que nunca responde: falha em 30 s, em vez de travar.
- **Tecla Esc deixava a página sem rolagem.** O tratamento genérico de Esc (compartilhado) era registrado antes dos tratamentos de cada tela e apenas escondia a janela; o tratamento da tela, ao rodar depois, via a janela "já fechada" e pulava a rotina de fechamento — que é quem devolve a rolagem da página. Fechar um modal com Esc travava a rolagem até recarregar. O tratamento genérico passou a ser registrado por último, e ainda devolve a rolagem por segurança.
- **Margem de impressão dos documentos.** A margem agora é declarada no `@page` (vale para **todas** as páginas) e padronizada em **20 mm** nos quatro lados, em todos os modelos de documento e relatório. Antes, o recuo era zerado na impressão em vários modelos e o rodapé saía a ~4 mm da borda — dentro da faixa que muitas impressoras não imprimem, com risco de cortar o código de autenticidade. Medido em PDF gerado: 20,1 mm.

---

## [0.26.2] — 2026-07-22

### Corrigido
- **Falhas silenciosas na comunicação com o servidor.** Vários pontos checavam `r.ok` sem antes verificar se a chamada devolveu resposta — e a camada de API devolve `null` quando a sessão expira (401) ou a rede falha. O resultado era um `TypeError` engolido: o botão simplesmente não fazia nada, sem mensagem alguma. Todos os pontos passaram a usar a guarda que o próprio código já adotava em outros lugares.
- **Sessão deslizante.** A sessão (60s) era renovada **apenas** pelo `/api/auth/ping`, um `setInterval` que o navegador estrangula em aba de segundo plano — quem ficasse redigindo com a aba atrás perdia a sessão e a ação seguinte falhava com 401. Agora **qualquer requisição autenticada renova** a sessão. O backup automático não muda: navegador fechado não faz requisições, então a sessão ociosa continua expirando em 60s.

---

## [0.26.1] — 2026-07-22

### Adicionado
- Coluna **Centro de Custo** na lista de Frota, mostrando o nome do centro vinculado (a lista guardava só o id) — com `—` quando o veículo não tem centro. A coluna é ordenável como as demais, e a **busca da tela passa a encontrar pelo nome do centro** (ex.: digitar "educa" filtra os veículos da Educação).

---

## [0.26.0] — 2026-07-22

### Adicionado
- **Importar CSV** na tela de Centros de Custo (admin): lê o cadastro exportado do Fiorilli, usando **CODCCUSTO** como código e **DESCR** como nome. A conciliação é em duas etapas — casa primeiro pelo **código** e, não achando, pelo **nome**, **adotando** o centro já cadastrado e gravando nele o código. Isso preserva os vínculos existentes (veículos, saídas) dos centros que haviam sido criados sem código pela importação da frota, em vez de duplicá-los.
- **Responsável** e **e-mail** no cadastro de Centro de Custo (colunas novas, migração automática), preenchidos pelo import a partir de `RESPONSA` e `EMAIL`.

### Notas
- Nomes repetidos com códigos diferentes (é assim no Fiorilli — ex.: dois centros "TRANSPORTE") são importados **fielmente**, e o resultado da importação avisa quais são, para você renomear ou desativar o que não usar. A alternativa (fundir pelo nome) descartaria um dos códigos.
- A importação é **idempotente**: reimportar o mesmo arquivo atualiza e não duplica.

---

## [0.25.1] — 2026-07-22

### Corrigido
- **Ficha do Veículo**: a tabela de dados usava rótulos com fundo cinza (`<th>`), que destoava do padrão dos relatórios e desalinhava rótulo e valor (padding diferente de `<th>`/`<td>`). Agora os rótulos são células normais em negrito, com o mesmo alinhamento e o zebrado padrão dos demais relatórios.

---

## [0.25.0] — 2026-07-22

### Adicionado
- **Ficha do Veículo** (imprimível) — botão **Ficha** por linha na tela de Frota gera um documento A4 com o cadastro do veículo e todo o catálogo de peças (filtros, óleos, bateria e pneus) organizado em seções, para o almoxarifado visualizar e imprimir/salvar em PDF.
- **Relatórios de Frota** na página de Relatórios: **Inventário da Frota** (relação completa), **Frota por Centro de Custo** (agrupado, com totais), **Frota por Combustível** (distribuição, útil para planejar compras) e **Pendências de Peças** (veículos com peça ainda vazia ou "FALTA INFORMAÇÃO", para dirigir o preenchimento).

---

## [0.24.0] — 2026-07-22

### Adicionado
- **Ficha de manutenção do veículo** no cadastro de Frota: além dos dados cadastrais, cada veículo passa a guardar o **Ano (fabricação/modelo)** e um **catálogo de peças** — 11 tipos de filtro (ar cabine/motor/primário/secundário, combustível, sedimentador, lubrificante, desumidificador, hidráulico, transmissão, ureia), óleo de motor e transmissão, bateria e pneus (dianteiro/traseiro) — com as referências cruzadas entre marcas. O formulário é organizado em seções (Cadastro / Filtros / Óleos, bateria e pneus).
- **Importar CSV** na tela de Frota (admin): lê a planilha *CONTROLE DE FROTA* exportada em CSV, deduplica por número de frota, vincula o Centro de Custo pelo nome (criando os que faltarem, opcional) e faz upsert (reimportar atualiza, não duplica). Detecta o delimitador (`;`/`,`) e o encoding (UTF-8/latin-1).

### Técnico
- Tabela `frota` ganhou 17 colunas TEXT (`ano` + catálogo de peças), adicionadas por migração automática (`ALTER TABLE`) nos bancos existentes.
- CRUD genérico ganhou suporte a campos `textarea` e a separadores de seção.

---

## [0.23.6] — 2026-07-22

### Corrigido
- Campos de busca das listas (Estoque, Reconciliação, Auditoria e cadastros de apoio) apareciam "quadradões" (sem borda arredondada/padding) porque estavam fora do contexto `.filters`. Agora usam um estilo único compartilhado (`.search-inp` no `base.css`), idêntico ao campo de Fornecedores.
- Relatórios: os dois campos de data do card "Movimentação por Período" transbordavam a borda do card em telas estreitas (faltava `min-width:0` no flex). Corrigido.

---

## [0.23.5] — 2026-07-22

### Modificado
- **Busca com ✕ para limpar** padronizada em todas as listas (Estoque, Reconciliação e Auditoria): os campos ganharam o mesmo botão ✕ já usado em Fornecedores e nos cadastros de apoio — aparece ao digitar, limpa a busca ao clicar. Antes usavam o estilo antigo (lupa, sem limpar). Helper compartilhado no `base.js`.

---

## [0.23.4] — 2026-07-22

### Adicionado
- **Natureza do Cargo** e **Forma de Provimento**, no cadastro de Funcionário, viraram **listas de seleção** (dropdown) com as opções reais da folha do Fiorilli (Efetivo, Comissão, Temporário, Emprego Público, Função de Confiança, Conselheiro; Concurso Público, Eleição/Indicação, Livre Provimento, Tempo Determinado) — antes eram texto livre, sujeito a erro de digitação. Um valor importado que não esteja na lista é **preservado** ao editar.
- **Ordenação por coluna** nas listas de cadastros de apoio (Funcionários, Centros de Custo, Frota): clicar no título da coluna ordena; clicar de novo inverte. Indicador ▲/▼ e `aria-sort` (operável por teclado).

## [0.23.3] — 2026-07-22

### Alterado
- **Aba Dados em paridade visual com a família**: a seção de backup deixou de ser fragmentada (cards "Pasta de Backup" e "Backup Automático" separados + fileira solta de botões) e virou uma seção **"Backup de Dados"** coesa, com o backup manual em duas colunas (Sistema JSON / Banco de dados .db) e o backup automático aninhado, no mesmo padrão do SGCD/SGCA/SGDP.

### Adicionado
- Botão **Exportar backup (JSON)** no cartão "Sistema (JSON)" da aba Dados (usa o endpoint `/api/backup` já existente) — antes o SGEA só restaurava JSON, não exportava.

### Corrigido
- Inputs da aba Dados (pasta de backup, backups mantidos) agora aparecem arredondados: a classe `.input` que esses campos usavam **nunca havia sido definida** no CSS — definida no `base.css` compartilhado (também corrige os inputs equivalentes de SGCD/SGCA).

## [0.23.2] — 2026-07-21

### Corrigido
- **Acessibilidade (WCAG 1.4.3)**: o contraste do botão "Dispensar" da faixa de aviso de servidor desatualizado subiu de ~3,5:1 para 8,1:1, com `aria-label` e alvo de toque maior.

### Interno
- Três funções que estavam copiadas idênticas nos 4 sistemas (`checarVersaoServidor` no `base.js`; `backup_ts` e `pick_folder_dialog` no `sgx_base.py`) foram consolidadas no esqueleto compartilhado (fonte única via `sync.py`), sem mudança de comportamento. O `Iniciar SGEA.bat` passou a encerrar um servidor preso na porta antes de subir o novo.

## [0.23.1] — 2026-07-20

### Adicionado
- **Aviso de servidor desatualizado.** O `/health` do servidor passou a informar a versão em execução, e o app compara com a versão do `SGEA.html` carregado ao entrar. Se o servidor Python em execução for mais antigo que a página (processo iniciado antes de uma atualização, situação em que rotas novas dão "Rota não encontrada" até reiniciar), uma faixa de alerta no topo orienta a reiniciar pelo `Iniciar SGEA.bat`. `SERVER_VERSION` no `server.py` deve acompanhar o `SGEA_VERSION` a cada release.

## [0.23.0] — 2026-07-20

### Adicionado
- **Importação de funcionários pela folha do Fiorilli (CSV).** Novo botão **Importar CSV** na tela de Funcionários (admin) que lê o CSV da folha de pagamento exportado do Fiorilli e cadastra todos os servidores de uma vez. O importador detecta o encoding (UTF-8 ou latin-1), ignora as colunas de salário, **deduplica por matrícula** (descartando as linhas repetidas de 13º/rescisão) e faz **upsert** — reimportar atualiza quem já existe pela matrícula, sem duplicar. Uma prévia mostra quantos funcionários únicos, quantos repetidos foram descartados e quantas linhas sem nome foram ignoradas antes de confirmar.
- **Novos campos no cadastro de Funcionário**: Natureza do Cargo, Forma de Provimento, Data de Admissão e Ato de Admissão (preenchidos automaticamente pela importação e editáveis no cadastro). A matrícula passou a aparecer também na listagem.

## [0.22.1] — 2026-07-20

### Corrigido
- **Relatório de Backup e Integridade voltou a funcionar para administradores.** A contagem de cadastros de apoio ainda consultava `fornecedores WHERE ativo=1`, mas a tabela `fornecedores` foi reescrita para o schema rico e passou a usar `deleted_at` (não tem mais coluna `ativo`) — a consulta quebrava com erro 500. O frontend, por sua vez, mostrava "acesso restrito a administradores" para **qualquer** falha, mascarando o erro real. Agora o fornecedores é contado por `deleted_at IS NULL` e a mensagem de erro reflete o motivo real devolvido pelo servidor.

## [0.22.0] — 2026-07-20

### Adicionado
- **"Meu E-mail" (SMTP por usuário)** na aba **Segurança** das Configurações, em paridade com SGCD/SGCA/SGDP: cada usuário pode cadastrar sua própria conta de envio (host, porta, STARTTLS/SSL, ignorar certificado, usuário, senha e nome do remetente), com os botões **"Salvar minha config"**, **"Copiar do sistema"** (traz host/porta/segurança da config do sistema, sem a senha) e **"Testar"**. Deixado em branco, herda o SMTP do sistema. A senha é gravada **apenas no servidor** (colunas `smtp_*` na tabela `usuarios`; endpoint `GET /api/usuarios/{id}/smtp` devolve tudo menos a senha) e nunca retorna ao navegador.

## [0.21.2] — 2026-07-20

### Alterado
- **Configurações em paridade visual com a família**: a aba **Comunicação** deixou de usar grade de 2 colunas — os campos do SMTP agora ficam empilhados em largura total, com o aviso âmbar "(apenas para servidores internos / autoassinados)" ao lado de "Ignorar verificação de certificado SSL", como no SGCD/SGCA/SGDP. A **Zona de Perigo** (aba Dados) passou de um bloco com fundo rosa para o mesmo cartão de borda vermelha (`fieldset`/`legend`) dos irmãos. Removidos overrides locais de `.cfg-tab` no modo escuro que divergiam do `base.css` compartilhado.

## [0.21.1] — 2026-07-20

### Alterado
- **Lote 4 da auditoria de design**: botão "🖨 Imprimir / Salvar PDF" dos documentos gerados agora **centralizado no topo** (era fixo no canto direito), como nos irmãos. Token `--violet` e regras novas no `base.css`/`DESIGN.md` compartilhados.

## [0.21.0] — 2026-07-20

### Alterado
- **Legibilidade do modo escuro**: novo token `--brand-text` — textos na cor da marca (números, links, metadados de cards) agora clareiam automaticamente no tema escuro (antes: navy sobre fundo escuro, quase ilegível). Aplicado via troca global `color: var(--brand)` → `var(--brand-text)`.
- **Componentes canônicos novos no `base.css`** (auditoria de design 2026-07-20): tabela de listagem (`.list-table`, com cabeçalho, zebra e hover) e variantes de badge (`badge-ok/warn/danger/neutral`). `DESIGN.md` atualizado (token, tabela e regra do acento esquerdo nos stat-cards).
- **Tabelas de listagem ganharam o estilo canônico** — Estoque, Alertas de Validade, Pedidos e demais listas usavam `.list-table` sem CSS (tabela crua do navegador, colunas coladas); agora têm cabeçalho, zebra, espaçamento e hover. Os badges de urgência dos Alertas (vencido/vencendo), que existiam no código mas renderizavam como texto puro, passaram a aparecer.
- **Login em paridade com os irmãos**: placeholders nos campos, rótulo "Senha de acesso" e ícone no botão "Entrar no sistema".
- Cosmético: linha do órgão na sidebar oculta até ser configurado (antes "—"); troca de senha com placeholders e botão "Salvar nova senha" (era "Alterar Senha").

## [0.20.0] — 2026-07-19

### Adicionado
- **Barra de ações de Fornecedores em paridade total com o SGCA** — a tela ganhou **Exportar CSV**, **Exportar Excel** (planilha .xlsx), **Relatório** de fornecedores imprimível e **Importar CSV** (cadastro em lote a partir de planilha; basta a coluna `cnpj`, com consulta automática opcional à Receita para preencher os demais campos). A busca ganhou botão de limpar (✕), **ordenação** (mais recente / mais antigo / A→Z / Z→A) e **contagem de resultados**.
- **Motor de exportação .xlsx** (writer OOXML mínimo, sem dependências) adicionado ao `base.js` compartilhado da família.

### Alterado
- **Brasão da barra lateral em 80×80** (antes 56×56), alinhando ao SGCD/SGCA/SGDP.
- Botão de sanções renomeado para **"Relatório de Sanções"** (ícone e rótulo idênticos ao SGCA).
- Campo de busca e seletor de ordenação passam a usar a classe `.filters` do padrão, casando fundo/borda/foco com o SGCA no tema escuro.

### Removido
- **"Importar backup" (JSON do SGCA/SGDP)** saiu da tela de Fornecedores, para deixar a barra idêntica ao padrão. A importação em lote agora é via **Importar CSV**. (O endpoint `POST /api/fornecedores/import` do servidor foi mantido.)

## [0.19.0] — 2026-07-19

### Adicionado
- **Filtros na tela de Fornecedores** — botões **Todos / Ativos / Inativos / Pendências** (paridade com SGCA/SGCD). Ativos/Inativos pela situação cadastral (ReceitaWS); **Pendências** lista fornecedores com CNPJ duplicado/inválido ou com certidão vencida.

### Alterado
- **Nome do órgão no topo da barra lateral** — a sidebar passa a exibir o órgão (ex.: "Prefeitura Municipal de Orindiúva") abaixo do subtítulo, alinhando o cabeçalho ao SGCD/SGCA.

## [0.18.0] — 2026-07-19

### Adicionado
- **Cadastro rico de Fornecedores**, saindo do motor CRUD genérico para uma tela dedicada: consulta automática de CNPJ (ReceitaWS, com BrasilAPI como alternativa), preenchendo razão social, situação cadastral, porte, natureza jurídica, endereço, CNAE e quadro societário (QSA); consulta de sanções federais **CEIS/CNEP** via Portal da Transparência (exige chave de API gratuita, configurável em Configurações → Organização); **certidões** e **sanções manuais** (Art. 156, Lei 14.133/2021) com dois relatórios imprimíveis — por fornecedor e global — que são os únicos documentos do SGEA com **código QR de autenticidade** no rodapé; **importação** de fornecedores a partir de um backup do SGCA ou SGDP (upsert por CNPJ, preservando certidões/sanções já cadastradas); e **exclusão reversível** — fornecedor excluído passa a aparecer na Lixeira, junto com Entradas e Saídas, restaurável por 30 dias.

## [0.17.0] — 2026-07-19

### Adicionado
- **Dashboard** — nova tela inicial (aberta automaticamente após o login, no lugar de Estoque), com 6 indicadores: valor total em estoque, produtos ativos, produtos com estoque zerado, lotes vencendo e vencidos (30 dias) e pedidos em aberto — os três últimos levam direto para a tela correspondente. Abaixo, um gráfico de barras (entradas × saídas em valor, últimos 6 meses).
- **Tela de Relatórios**, com 5 documentos imprimíveis: **Posição de Estoque Valorizado** (quantidade e valor por produto, com próxima validade), **Movimentação por Período** (entradas e saídas detalhadas num intervalo de datas escolhido), **Lotes a Vencer/Vencidos** (mesma janela de 90 dias da tela de Alertas), **Pedidos em Aberto** (itens ainda pendentes de cada pedido) e **Curva ABC** (classificação dos produtos por participação no valor total do estoque, com corte em 80%/95%). Todos seguem o mesmo padrão visual já usado pelo Backup e Integridade e pela Trilha de Auditoria (cabeçalho com brasão, Times New Roman, numeração de página, sem QR — relatórios gerenciais, não documentos formais).

## [0.16.0] — 2026-07-19

### Adicionado
- **Auditoria registra geração de relatórios.** Ao gerar a Trilha de Auditoria ou o relatório de Backup e Integridade, um evento `DOCUMENTO_GERADO` ("Relatório gerado", badge navy) passa a ser gravado na auditoria — fechando a lacuna de rastreabilidade que existia frente aos sistemas irmãos.
- **Numeração de páginas nos relatórios impressos.** Os dois relatórios ganham "Folha N" no rodapé de cada página impressa (`@page counter`), útil para relatórios de várias páginas.

### Alterado
- **CSS dos relatórios impressos consolidado** numa const única (`_RELATORIO_CSS`), antes duplicada quase idêntica nos dois geradores. Sem mudança visual (a margem do título foi unificada em 10pt).

## [0.15.2] — 2026-07-18

### Alterado
- **Rodapé nos relatórios impressos** (Trilha de Auditoria e Backup e Integridade): "Documento gerado pelo SGEA · data · por usuário", alinhado ao padrão dos sistemas irmãos. Sem QR — os relatórios do SGEA são gerenciais, não documentos formais.

## [0.15.1] — 2026-07-18

### Alterado
- **Helpers de exportação consolidados no esqueleto compartilhado** (`base.js`): `_salvarArquivoComo` (diálogo "Salvar como") e `toCSV` (montagem de CSV) deixam de ser duplicados no HTML e passam a vir do `base.js` comum aos 4 sistemas. Sem mudança de comportamento — as exportações do SGEA já usavam o diálogo.

## [0.15.0] — 2026-07-18

### Adicionado
- **Diálogo "Salvar como" ao exportar arquivos** — as exportações geradas no navegador (CSV da Trilha de Auditoria, CSV de pendências da Reconciliação e o backup de segurança baixado antes do reset de fábrica) passam a abrir o explorador nativo do Windows para escolher a pasta de destino (File System Access API `showSaveFilePicker`), em vez de salvar direto na pasta de Downloads. Em contexto sem suporte (ex.: acesso pela rede por IP, sem `localhost`), cai automaticamente no download tradicional, sem quebrar. Alinha o SGEA ao comportamento dos sistemas irmãos.

## [0.14.0] — 2026-07-18

### Adicionado
- **Reconciliação com o Fiorilli** — nova tela (menu **Reconciliação**) que importa o relatório de **Posição do Estoque** do Fiorilli (exportado como **CSV (Dados)**) e compara, item a item, com o estoque do SGEA. É **somente leitura**: o Fiorilli continua sendo o razão oficial, o SGEA nunca escreve nele.
  - **Casamento por `codigo_fiorilli`** (CADPRO), com cinco situações: **Confere**, **Diverge qtd**, **Só Fiorilli** (item que o SGEA não cadastrou), **Só SGEA** (saldo que o Fiorilli omitiu) e **Unidade incompatível** (cadastro a padronizar).
  - **Conversão de unidade automática** — as quantidades do Fiorilli são convertidas para a **unidade de consumo** do SGEA usando a `qtd_por_embalagem` do produto (ex.: `0,68 CX` vira `17 UN`). O almoxarife lê tudo na unidade de prateleira.
  - **Guarda de data de corte** — avisa quando o extrato não é do dia (a posição do SGEA muda a cada movimento), recomendando reconciliar com um extrato de hoje.
  - **Valor como conferência secundária** e sinalização de estoque/valor negativo do Fiorilli; **Exportar pendências** em CSV.
  - O import fica registrado na **Trilha de Auditoria** (`RECONCILIACAO_IMPORTADA`).

## [0.13.7] — 2026-07-18

### Corrigido (acessibilidade — WCAG 2.1 AA)
- **Elementos interativos agora acessíveis por teclado** (WCAG 2.1.1): itens da busca global (Ctrl+K), item de notificação e a linha de produto que expande os lotes ganharam `role="button"` + `tabindex="0"` (o estilo compartilhado já dispara a ação em Enter/Espaço). Antes só respondiam ao mouse. Fecha a paridade com SGCD/SGCA/SGDP.
- **`alt` na prévia do brasão** (WCAG 1.1.1) — a imagem de pré-visualização do brasão nas Configurações passou a ter texto alternativo.

## [0.13.6] — 2026-07-18

### Corrigido
- **Parsing de valores (`_float`) mais robusto** — aceita moeda no formato brasileiro com separador de milhar (`1.234,56` deixou de virar nulo) e número puro; entradas inválidas continuam retornando nulo sem quebrar. Mesma correção aplicada em SGCD e SGCA.

## [0.13.5] — 2026-07-18

### Corrigido
- **Bolinha de cor em "Cor de destaque" não aparecia** — a classe `.cor-swatch` não tinha dimensões definidas (span de 0×0). Adicionada a regra CSS (`14×14`, círculo, `flex-shrink:0`), igualando o padrão de bolinha dos sistemas irmãos.

## [0.13.4] — 2026-07-17

### Corrigido
- **Painel de notificações (sino) agora abre à direita da barra lateral**, em vez de sobrepor o rodapé da sidebar. O SGEA era o único que não reposicionava o painel dinamicamente (usava a posição padrão `left:16px` do estilo compartilhado); agora usa `left = largura da sidebar + 12px`, no mesmo padrão de SGCD/SGCA/SGDP.

## [0.13.3] — 2026-07-17

### Removido
- **Skeleton de carregamento removido** — eram apenas 3 divs placeholder que nem tinham CSS de skeleton (renderizavam vazios); padronização com os sistemas irmãos. A lista de produtos já é populada pelo JS ao carregar.

## [0.13.2] — 2026-07-17

### Alterado
- **Modo escuro alinhado ao padrão neutro canônico da família.** O tema escuro do SGEA usava tons próprios ligeiramente diferentes (fundo `#17181c`, cards `#232323`); agora usa exatamente a paleta neutra do estilo compartilhado (`base.css`): fundo `#1a1a1a`, cards `#2a2a2a`, texto `#f0ece8`, faixa de tabela `#323232`. Fica idêntico ao dark de SGCD/SGCA/SGDP. Nenhuma mudança no modo claro.

## [0.13.1] — 2026-07-17

### Corrigido
- **Tabela da tela de Auditoria agora tem o mesmo visual dos sistemas irmãos** — na v0.13.0 os rótulos/badges/filtros/CSV/relatório foram igualados, mas a tabela em si ainda usava o estilo genérico "cru" (sem cabeçalho em faixa, sem bordas de linha, sem card). Agora tem cabeçalho em faixa (maiúsculo), linhas com separador e o conjunto dentro de um card com sombra e cantos arredondados, no padrão do SGDP/SGCD (com a paleta escura do próprio SGEA no modo noturno). O título passou a ser "Trilha de Auditoria" e a filtragem ao vivo ganhou um pequeno atraso (debounce) para não recarregar a cada tecla.

## [0.13.0] — 2026-07-17

### Alterado
- **Tela de Auditoria em paridade com os sistemas irmãos** — as ações agora aparecem com **rótulos legíveis** (ex.: "Entrada registrada" em vez de `ENTRADA_REGISTRADA`) e **badges coloridos por família de ação** (verde = criação/restauração, azul = edição, vermelho = exclusão/reset, âmbar = anulação/restauração de backup), a filtragem por busca/tipo/data passou a ser **ao vivo** (sem botão "Filtrar"), e a lista ficou num **layout centralizado**, tudo igual ao SGCD/SGCA.

### Adicionado
- **Exportar CSV** e **Relatório imprimível** na tela de Auditoria — o CSV baixa todos os eventos que batem com os filtros atuais (com cabeçalho e rótulos legíveis); o Relatório abre um documento com cabeçalho do órgão/brasão e a trilha completa, pronto para imprimir ou salvar em PDF (reusa a infraestrutura de documento imprimível já existente no SGEA).

## [0.12.0] — 2026-07-17

### Adicionado
- **Pedidos com múltiplos itens** — cada pedido agora agrupa vários produtos, cada um com sua quantidade pedida (nova tabela `pedido_itens`, uma linha por produto, única por pedido+produto). Nova aba de Pedidos com listagem, modal de criação/edição com linhas de itens dinâmicas, cancelamento do pedido inteiro e anulação do saldo de um item específico. Endpoints: `GET/POST /api/pedidos`, `GET/PUT/DELETE /api/pedidos/<id>`, `POST /api/pedidos/<id>/cancelar`, `POST /api/pedidos/<id>/itens/<id>/anular`.
- **Status derivado das entradas, sem contador armazenado** — a quantidade recebida de cada item é sempre calculada a partir da soma real das entradas vinculadas ao pedido (`entrada_itens`), nunca guardada numa coluna, pra não correr o risco de um contador desalinhar da realidade. Daí saem o saldo em aberto e o status por item (`aberto`/`parcial`/`atendido`/`encerrado_parcial`) e o status agregado do pedido — sendo `cancelado` o único valor definido manualmente, tudo o mais é recalculado dos itens a cada leitura.

## [0.11.7] — 2026-07-14

### Alterado
- **Fundo animado da tela de login ganhou interação de mouse**, igualando ao SGCD/SGCA/SGDP — `_loginCanvasStart`/`_loginCanvasStop` (as 2 últimas funções do motor de partículas ainda locais, mantidas deliberadamente simples na v0.11.6) foram removidas em favor da versão do esqueleto compartilhado, que já tinha esse comportamento. Contagem padrão de partículas também passa a ser 60 (padrão da família), não mais 50.

## [0.11.6] — 2026-07-14

### Removido
- **6 das 8 funções do motor de partículas da tela de login (`_lcLoadConfig`/`_lcSaveConfig`/`_lcToggleConfig`/`_lcParam`/`_lcResetConfig`/`_lcSpeedVal`) reimplementadas localmente**, byte-idênticas às do esqueleto compartilhado (só a chave de `localStorage` estava hardcoded em vez de usar `_lcConfigKey()` — mesmo valor na prática). `_loginCanvasStart`/`_loginCanvasStop` continuam locais (sem interação de mouse, contagem de partículas padrão 50 em vez de 60 — escolhas deliberadas do SGEA)

## [0.11.5] — 2026-07-14

### Removido
- **`create_session`/`delete_session`/`renew_session`/`active_sessions` reimplementadas localmente**, mecanicamente idênticas ao esqueleto compartilhado (`_esqueleto/sgx_base.py`) — agora delegam pro `sgx_base`, mantendo a mesma assinatura local. `get_session()` permanece local (SELECT de colunas explícito por segurança, colunas divergem por sistema). Import `secrets` removido (ficou sem uso após a mudança)

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
