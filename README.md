# SGEA — Sistema de Gestão de Estoque do Almoxarifado

![Versão](https://img.shields.io/badge/versão-v0.13.1-blue) ![Tecnologia](https://img.shields.io/badge/tecnologia-Python%20%2B%20SQLite-orange) ![Licença](https://img.shields.io/badge/licença-MIT-green) ![Multiusuário](https://img.shields.io/badge/acesso-multiusuário-blueviolet)

## Descrição

O **SGEA** é uma aplicação web multiusuário para o **Almoxarifado**, destinada ao controle de estoque de itens licitados: entradas (com ou sem pedido/licitação vinculado), saídas por centro de custo/solicitante, e rastreamento de lote e validade.

O sistema nasceu para substituir uma planilha Excel usada em paralelo ao sistema oficial (Fiorilli), corrigindo três limitações dela: itens comprados por embalagem (caixa) mas retirados em unidade fracionada, ausência de controle de lote/validade, e a exigência informal de vincular toda entrada a um pedido (quando também existem compras diretas). Compartilha a arquitetura (servidor Python stdlib + SQLite + frontend single-file) com os sistemas irmãos SGCD, SGCA e SGDP.

Funciona em rede local: um único computador executa o servidor e todos os usuários acessam pelo navegador via IP ou `localhost`.

---

## Funcionalidades Principais

- **Estoque sempre em unidade de consumo** — produtos guardam um fator de conversão (unidades por embalagem); a entrada informa quantas embalagens chegaram e o sistema converte para unidades automaticamente, permitindo que a saída seja de qualquer quantidade fracionária (ex.: 2 unidades de uma caixa de 12)
- **Controle de lote e validade** — cada entrada gera um lote com data de validade opcional; o painel do produto mostra o saldo por lote e destaca lotes vencidos
- **Saída por FEFO** (*first-expire, first-out*) — ao registrar uma saída, o sistema consome primeiro o lote que vence mais cedo, dividindo automaticamente entre lotes quando um não é suficiente
- **Alertas de Validade** — tela dedicada com lotes vencidos ou a vencer numa janela de 30/60/90 dias
- **Entrada com ou sem pedido** — vínculo opcional a um Pedido (nº + código de licitação); sem pedido, a entrada é tratada como compra direta (só NF, fornecedor e produto)
- **Reversão segura** — excluir uma saída devolve exatamente as quantidades aos lotes de origem; excluir uma entrada é bloqueado se algum de seus lotes já foi parcialmente consumido
- **Cadastros de apoio** — Centros de Custo, Fornecedores (com consulta automática de CNPJ), Funcionários (solicitantes de saída) e Frota (veículos, para correlacionar saídas de combustível/peças)
- **Autenticação multiusuário** com hashing PBKDF2-HMAC-SHA256 e gestão de usuários pelo admin
- **Auditoria** — trilha de eventos de criação/edição/exclusão em todos os módulos, com tela de consulta filtrável (admin)
- **Lixeira** — Entradas e Saídas excluídas ficam disponíveis para restaurar por 30 dias
- **Alerta diário por e-mail** (SMTP configurável) resumindo lotes vencidos ou vencendo nos próximos 7 dias
- **Tela de Configurações em 7 abas** — Interface (tema, largura do conteúdo, fonte, cor de destaque), Organização (órgão/CNPJ/autoridade competente e brasão), Comunicação (SMTP), Dados (backup/restore, Zona de Perigo), Segurança (troca da própria senha), Diagnóstico (checagens de consistência) e Usuários (admin), com salvamento único e indicador de alterações não salvas — mesmo padrão visual dos sistemas irmãos
- **Login no padrão visual dos sistemas irmãos** — cartão institucional, identificação do órgão, aviso de Caps Lock e último backup exibido antes de entrar
- **Busca global (Ctrl+K)** — encontra produtos, fornecedores, funcionários, frota, centros de custo e pedidos por qualquer tela, com atalho de teclado
- **Sino de notificações** — contagem de lotes vencidos/vencendo nos próximos 7 dias, com painel de acesso rápido
- **Backup automático** (JSON + banco de dados SQLite) ao encerrar a última sessão, com rotação configurável, restauração a partir de arquivo e reset de fábrica com confirmação em 3 etapas
- **Diagnóstico e correção automática de rede** — verifica IP, porta, perfil de rede e firewall

> Fora de escopo nesta versão, planejado para depois: dashboard, relatórios de consumo por período e curva ABC — o schema já foi desenhado para suportá-los sem alterações estruturais. Importação do histórico da planilha também fica para um módulo futuro; o código Fiorilli como chave única de produto já prepara esse caminho.

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
| **SQLite** | Armazenamento persistente dos dados (`sgea.db`) |
| **ReceitaWS** | Consulta de CNPJ no cadastro de fornecedores |

---

## Desenvolvimento

O sistema em si continua zero-dependência (Python stdlib + HTML puro). Para quem for alterar o código, há um lint opcional que verifica variáveis indefinidas no JavaScript de `SGEA.html`:

```bash
npm install   # uma vez, instala apenas o ESLint (ferramenta de dev, não é usada em produção)
npm run lint
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
