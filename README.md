# SGEA — Sistema de Gestão de Estoque do Almoxarifado

![Versão](https://img.shields.io/badge/versão-v0.35.0-blue) ![Tecnologia](https://img.shields.io/badge/tecnologia-Python%20%2B%20SQLite-orange) ![Licença](https://img.shields.io/badge/licença-MIT-green) ![Multiusuário](https://img.shields.io/badge/acesso-multiusuário-blueviolet) [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21570250.svg)](https://doi.org/10.5281/zenodo.21570250) [![CI](https://github.com/devtulio/sgea/actions/workflows/ci.yml/badge.svg)](https://github.com/devtulio/sgea/actions/workflows/ci.yml)

## Descrição

O **SGEA** é uma aplicação web multiusuário para o **Almoxarifado**, destinada ao controle de estoque de itens licitados: entradas (com ou sem pedido/licitação vinculado), saídas por centro de custo/solicitante, e rastreamento de lote e validade.

O sistema nasceu para substituir uma planilha Excel usada em paralelo ao sistema oficial (Fiorilli), corrigindo três limitações dela: itens comprados por embalagem (caixa) mas retirados em unidade fracionada, ausência de controle de lote/validade, e a exigência informal de vincular toda entrada a um pedido (quando também existem compras diretas). Compartilha a arquitetura (servidor Python + SQLite + frontend single-file, sem nada a instalar) com os sistemas irmãos SGCD, SGCA e SGDP.

Funciona em rede local: um único computador executa o servidor e todos os usuários acessam pelo navegador via IP ou `localhost`.

---

## Funcionalidades Principais

- **Dashboard** — tela inicial após o login, com indicadores de valor em estoque, produtos ativos/zerados, lotes vencendo/vencidos e pedidos em aberto, e um gráfico de entradas × saídas dos últimos 6 meses
- **Relatórios** — Posição de Estoque Valorizado, Movimentação por Período, Lotes a Vencer/Vencidos, Pedidos em Aberto, Curva ABC e relatórios da Frota (Inventário, por Centro de Custo, por Combustível e Pendências de Peças), todos imprimíveis no mesmo padrão visual dos demais documentos do sistema
- **Estoque sempre em unidade de consumo** — produtos guardam um fator de conversão (unidades por embalagem); a entrada informa quantas embalagens chegaram e o sistema converte para unidades automaticamente, permitindo que a saída seja de qualquer quantidade fracionária (ex.: 2 unidades de uma caixa de 12)
- **Controle de lote e validade** — cada entrada gera um lote com data de validade opcional; o painel do produto mostra o saldo por lote e destaca lotes vencidos
- **Saída por FEFO** (*first-expire, first-out*) — ao registrar uma saída, o sistema consome primeiro o lote que vence mais cedo, dividindo automaticamente entre lotes quando um não é suficiente
- **Alertas de Validade** — tela dedicada com lotes vencidos ou a vencer numa janela de 30/60/90 dias
- **Entrada com ou sem pedido** — vínculo opcional a um Pedido (nº + código de licitação); sem pedido, a entrada é tratada como compra direta (só NF, fornecedor e produto)
- **Reversão segura** — excluir uma saída devolve exatamente as quantidades aos lotes de origem; excluir uma entrada é bloqueado se algum de seus lotes já foi parcialmente consumido
- **Fornecedores** — cadastro rico: consulta automática de CNPJ (ReceitaWS/BrasilAPI) com endereço, CNAE e quadro societário; consulta de sanções federais (CEIS/CNEP); certidões e sanções manuais (Art. 156, Lei 14.133/2021) com relatórios imprimíveis (com QR de autenticidade); exportação e sincronização do cadastro com os sistemas irmãos (SGCD/SGCA) casando por CNPJ, com tela de revisão quando o mesmo fornecedor mudou dos dois lados; exclusão reversível pela Lixeira
- **Tela de Fornecedores em tabela** — colunas ordenáveis pelo cabeçalho, seleção em massa para envio à Lixeira e o cadastro completo (Dados, Certidões, Sanções) numa janela de detalhe
- **Cadastros de apoio** — Centros de Custo (com código, responsável e e-mail), Funcionários (solicitantes de saída; com cargo, unidade, matrícula, natureza/forma de provimento e data/ato de admissão) e Frota (veículos, para correlacionar saídas de combustível/peças)
- **Ações em massa nos cadastros** — Frota, Centros de Custo e Funcionários têm coluna de seleção com "selecionar todos" (respeitando a busca ativa) e barra de ações com Excluir em lote (com resumo do que foi bloqueado e por quê), Ativar, Inativar, Exportar CSV e, só na Frota, Reatribuir centro de custo
- **Ficha de manutenção da Frota** — além do cadastro do veículo (nº, placa, ano, marca/modelo, combustível, centro de custo), cada veículo guarda um catálogo de peças: 11 tipos de filtro, óleos de motor/transmissão, bateria e pneus, com as referências cruzadas entre marcas; o botão **Ficha** gera um documento A4 imprimível com o cadastro e todo o catálogo por seção
- **Importação do pedido de compra do Fiorilli** — lê o CSV do pedido e cria número, data, previsão de entrega, licitação, fornecedor e itens (com valor unitário e marca), criando fornecedor por CNPJ e produto por `codigo_fiorilli` quando faltarem; converte a quantidade da unidade licitada para a de consumo pela embalagem do produto, soma itens repetidos e avisa quando o pedido já tem entrega registrada no Fiorilli. Idempotente pelo nº do pedido
- **Ações em massa no Estoque e em Pedidos** — seleção por linha com "selecionar todos" respeitando a busca; no Estoque: excluir (com resumo do que ficou bloqueado e por quê), ativar, inativar, exportar CSV e reatribuir centro de custo; em Pedidos: cancelar em lote (anulando o saldo pendente) e exportar CSV
- **Importação das requisições de entrada e saída do Fiorilli** — lê a *REQUISIÇÃO DE ENTRADA* ou de *SAÍDA* (CSV) e lança o movimento inteiro: a entrada cria itens e lotes com validade (criando produto por `codigo_fiorilli`, fornecedor por CNPJ e centro de custo por código quando faltarem); a saída baixa o estoque honrando o lote que o Fiorilli indicou e é **toda-ou-nada** — faltando produto cadastrado ou saldo, nada é gravado e o sistema devolve a lista do que impediu. Idempotente pelo nº da requisição em ambos os casos
- **Importação de funcionários pela folha do Fiorilli** — botão que lê o CSV da folha de pagamento e cadastra todos os servidores de uma vez, detectando o encoding, ignorando salários, deduplicando por matrícula e fazendo upsert (reimportar atualiza, não duplica)
- **Importação de centros de custo por CSV** — lê o cadastro do Fiorilli (CODCCUSTO/DESCR); concilia por código e, não achando, pelo nome, adotando o centro já existente para preservar os vínculos em vez de duplicar
- **Importação da Frota por planilha** — botão que lê a planilha *CONTROLE DE FROTA* em **.csv ou .xlsx** (lendo a aba *DADOS* automaticamente), deduplica por número, vincula o centro de custo **pelo código** (formato "N - NOME"), caindo para o nome quando não encontra (criando os que faltarem), e faz upsert
- **Autenticação multiusuário** com hashing PBKDF2-HMAC-SHA256 e gestão de usuários pelo admin
- **Reconciliação com o Fiorilli** — importa o relatório de Posição do Estoque do Fiorilli (CSV Dados) e compara item a item por `codigo_fiorilli`, classificando em confere / diverge / só-Fiorilli / só-SGEA / unidade incompatível; converte as quantidades do Fiorilli para a unidade de consumo do SGEA. **Não escreve no Fiorilli** (ele continua o razão oficial), mas oferece dois atalhos para corrigir o lado do SGEA sem sair da tela: **Cadastrar itens do Fiorilli** (com saldo inicial opcional) e o botão **Editar** por linha, que reprocessa o extrato ao salvar. Exporta as pendências em CSV
- **Auditoria** — trilha de eventos de criação/edição/exclusão em todos os módulos, com tela de consulta filtrável (admin)
- **Lixeira** — Entradas, Saídas e Fornecedores excluídos ficam disponíveis para restaurar por 30 dias
- **Alerta diário por e-mail** (SMTP configurável) resumindo lotes vencidos ou vencendo nos próximos 7 dias
- **Tela de Configurações em 7 abas** — Interface (tema, largura do conteúdo, fonte, cor de destaque), Organização (órgão/CNPJ/autoridade competente e brasão), Comunicação (SMTP), Dados (backup/restore, Zona de Perigo), Segurança (troca da própria senha e config pessoal de e-mail/SMTP), Diagnóstico (checagens de consistência, com o painel de erros recentes do sistema) e Usuários (admin), com salvamento único e indicador de alterações não salvas — mesmo padrão visual dos sistemas irmãos
- **Login no padrão visual dos sistemas irmãos** — cartão institucional, identificação do órgão, aviso de Caps Lock e último backup exibido antes de entrar
- **Busca global (Ctrl+K)** — encontra produtos, fornecedores, funcionários, frota, centros de custo e pedidos por qualquer tela, com atalho de teclado
- **Sino de notificações** — contagem de lotes vencidos/vencendo nos próximos 7 dias, com painel de acesso rápido
- **Backup automático** (JSON + pacote `.zip` do banco — o `.db` legado ainda restaura) ao encerrar a última sessão, com rotação configurável, restauração a partir de arquivo e reset de fábrica com confirmação em 3 etapas
- **Motor de captura e tratamento de erros** — erros do servidor e do navegador do usuário são registrados em log rotativo e agrupados na tela **Erros recentes** (Configurações → Diagnóstico, somente admin); travamentos graves ficam em `SGEA_crash.log`
- **Diagnóstico e correção automática de rede** — verifica IP, porta, perfil de rede e firewall

> Fora de escopo nesta versão, planejado para depois: importação do histórico da planilha — o código Fiorilli como chave única de produto já prepara esse caminho.

---

## Requisitos

- **Python 3.7+** (apenas biblioteca padrão — zero dependências externas)
- **Google Chrome** ou **Microsoft Edge** (recomendado)
- Windows 10/11

> **Servidor sem Python instalado (ex.: Windows Server bloqueado por política de TI):**
> o `Iniciar SGEA.bat` detecta automaticamente a ausência do Python e extrai uma versão portátil (embarcável, sem instalador) incluída no próprio projeto (`python-3.12.9-embed-amd64.zip`) para `C:\Python312-embed\` — não exige instalação nem privilégio de administrador.

---

## Instalação e uso

1. Copie a pasta `SGEA/` para o computador que atuará como servidor
2. Clique duas vezes em **`Iniciar SGEA.bat`**
3. Faça login com as credenciais iniciais abaixo — a troca de senha é obrigatória no primeiro acesso

> ⚠️ **Importante:** abrir o `SGEA.html` diretamente pelo navegador (sem o servidor) impede o funcionamento do sistema. Use sempre o `Iniciar SGEA.bat`.

### Login inicial

| Campo   | Valor       |
|---------|-------------|
| Usuário | `admin`     |
| Senha   | `admin123`  |

### Menu de inicialização

O `Iniciar SGEA.bat` abre um menu no terminal:

| Opção | Descrição |
|-------|-----------|
| **[1] Diagnóstico** | Verifica e corrige automaticamente rede, porta e firewall (pede elevação de Administrador quando necessário) |
| **[2] Iniciar Servidor** | Sobe o servidor e mantém rodando continuamente — atende uso individual e em rede. Só encerra com **Ctrl+C** no terminal ou fechando a janela |

### Acesso em rede local

O sistema foi projetado para uso multiusuário em rede local (LAN): **uma única máquina executa o servidor** (e guarda o banco de dados) e as demais acessam pelo navegador, sem instalar nada.

**Na máquina servidora (uma vez só):**

1. Execute **`Liberar Porta SGEA.bat`** como Administrador (botão direito → *Executar como administrador*) — cria a regra no Firewall do Windows liberando a porta 3003 para conexões de entrada
2. Inicie o sistema pelo `Iniciar SGEA.bat` e deixe a máquina ligada — ao iniciar, o console mostra o endereço de rede pronto para distribuir (`Rede: http://<IP>:3003/SGEA.html`)

**Nas outras máquinas:** basta abrir o navegador (Chrome ou Edge) no endereço do servidor:

```
http://192.168.x.x:3003/SGEA.html
```

Cada usuário faz login com sua própria conta — o servidor atende acessos simultâneos e todos enxergam os mesmos dados.

Se a conexão não funcionar, execute **`Diagnostico SGEA.bat`** (ou a opção **[1]** do `Iniciar SGEA.bat`) na máquina servidora: ele descobre o IP e verifica/corrige automaticamente firewall e perfil de rede.

> ⚠️ **Uso restrito à rede interna.** A comunicação é HTTP simples (sem criptografia de transporte) — adequado para uma LAN interna confiável, mas **nunca exponha a porta do sistema à internet**. Para acesso remoto, use a VPN institucional.

---

## Estrutura de arquivos

```
SGEA/
├── SGEA.html                # Frontend — aplicação web
├── server.py                # Servidor Python (API REST + SQLite) — porta 3003
├── sgx_base.py              # Esqueleto compartilhado da família (backend) — cópia distribuída
├── base.css                 # Esqueleto compartilhado da família (estilos) — cópia distribuída
├── base.js                  # Esqueleto compartilhado da família (JS) — cópia distribuída
├── _esqueleto.sha256        # Manifesto de integridade das cópias do esqueleto (conferido no CI)
├── waitress/                # Servidor WSGI vendorizado (puro-Python, nada a instalar)
├── scripts/                 # Utilitários de desenvolvimento (lint, verificação do esqueleto)
├── tests/                   # Suíte de testes automatizados do backend
│   ├── test_server.py
│   └── e2e/                 # Testes E2E (Playwright) — navegador real de ponta a ponta
├── Iniciar SGEA.bat         # Inicializa o servidor
├── python-3.12.9-embed-amd64.zip  # Python portátil (fallback se não houver Python instalado)
├── Criar Atalho SGEA.bat    # Cria atalho na área de trabalho com ícone
├── Criar Atalho SGEA.ps1    # Script PowerShell de criação do atalho
├── Diagnostico SGEA.bat     # Roda o diagnóstico de rede (clique duplo)
├── Liberar Porta SGEA.bat   # Cria regra de firewall para a porta (Admin)
├── diagnostico.py           # Script de diagnóstico de rede e firewall
├── sgea.ico                 # Ícone do sistema
├── sgea.db                  # Banco de dados SQLite (criado automaticamente)
├── backups/                 # Backups automáticos (criado automaticamente)
├── browser-profile/         # Perfil do Chrome/Edge (criado automaticamente)
├── requirements.txt         # Sem dependências externas — arquivo documental
├── README.md
├── CHANGELOG.md
└── MANUAL.html
```

---

## Documentos Gerados pelo Sistema

| Documento | Descrição |
|-----------|-----------|
| **Ficha do Veículo** | Ficha de manutenção imprimível de um veículo da frota |
| **Relatório de Estoque** | Posição de estoque por item |
| **Relatório de Movimentação** | Entradas e saídas por período |
| **Curva ABC** | Classificação ABC dos itens por consumo |
| **Relatório de Lotes / Validade** | Lotes e vencimentos (FEFO) |
| **Relatório de Pedidos em Aberto** | Pedidos pendentes de entrega |
| **Relatórios de Frota** | Inventário, combustível, por centro de custo e pendências |
| **Relatório de Fornecedores** | Cadastro de fornecedores |
| **Relatório de Sanções** | Sanções registradas no cadastro do fornecedor (Art. 156 da Lei 14.133/2021) |
| **Relatório de Auditoria** | Trilha de eventos do sistema |
| **Relatório de Integridade** | Estado do banco, backups e contagens |

Todos os documentos abrem em janela separada com botão "🖨 Imprimir / Salvar PDF".

---

## Segurança

- Senhas armazenadas com **PBKDF2-HMAC-SHA256** e salt aleatório por usuário
- Sessões server-side invalidadas automaticamente por inatividade
- Acesso à API exige token de sessão em todas as rotas (exceto login e verificação)
- Verificação de integridade do banco de dados (SQLite `PRAGMA integrity_check`) na inicialização
- Recomenda-se uso em rede interna (LAN) apenas

---

## Tecnologias

| Tecnologia | Uso |
|-----------|-----|
| **HTML5 + CSS3** | Interface da aplicação, layout responsivo |
| **JavaScript puro (ES6+)** | Toda a lógica de negócio, sem frameworks externos |
| **Python 3 (stdlib)** | Servidor local: REST API, SQLite, auth, proxy CNPJ |
| **waitress (vendorizado, puro-Python)** | Servidor WSGI que atende as requisições — vem junto na pasta `waitress/`, não precisa instalar nada |
| **SQLite** | Armazenamento persistente dos dados (`sgea.db`) |
| **ReceitaWS** | Consulta de CNPJ no cadastro de fornecedores |

---

## Desenvolvimento

O sistema em si continua sem nada a instalar: Python stdlib + HTML puro, mais o **waitress** vendorizado em `waitress/` — não é biblioteca padrão, mas viaja junto do repositório, então não há passo de instalação de dependências. Para quem for alterar o código, há um lint opcional que verifica variáveis indefinidas no JavaScript de `SGEA.html`:

```bash
npm install   # uma vez, instala apenas o ESLint (ferramenta de dev, não é usada em produção)
npm run lint
```

Parte do código é compartilhada com os outros sistemas da família (SGCD, SGCA e SGDP): `base.css`, `base.js` e `sgx_base.py` são cópias distribuídas a partir de uma fonte única, que fica fora deste repositório. Editar essas cópias aqui funciona e passa no lint — mas a alteração é silenciosamente sobrescrita na próxima distribuição. Por isso o CI confere as cópias contra o manifesto `_esqueleto.sha256` e quebra o build se elas divergirem:

```bash
python scripts/verificar_esqueleto.py
```

Há também uma suíte de testes automatizados do backend (`server.py`), usando só `unittest` da stdlib — sobe o servidor real contra um banco temporário e testa os endpoints REST, com atenção especial à lógica de consumo por lote (FEFO):

```bash
python -m unittest discover -s tests -v
```

Há também uma suíte de testes E2E (`tests/e2e/`), usando Playwright — sobe o servidor real e dirige um Chromium de verdade pelo fluxo completo (login com troca de senha obrigatória, cadastro de produto, entrada com conversão caixa→unidade, saída fracionada e alerta de validade):

```bash
npm install
npx playwright install chromium   # uma vez, baixa o navegador de teste
npm run test:e2e
```

Roda contra um banco/backups temporários (nunca o `sgea.db` real), criados e descartados automaticamente a cada execução.

---

## Versionamento

Consulte o [CHANGELOG.md](CHANGELOG.md) para o histórico completo de versões e alterações.

---

## Contribuição

Contribuições são bem-vindas! Veja o [CONTRIBUTING.md](CONTRIBUTING.md) para orientações sobre como reportar bugs, sugerir funcionalidades e enviar Pull Requests.

---

## Licença

Distribuído sob a licença **MIT**. Veja [LICENSE](LICENSE) para o texto completo.

> **Aviso:** Os dados ficam armazenados no arquivo `sgea.db` na pasta do sistema. Faça backups regulares pela tela **Backup** e mantenha cópia do `sgea.db` em local seguro.
