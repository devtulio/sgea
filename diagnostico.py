# SGEA — Diagnóstico e Correção Automática de Rede
import socket, subprocess, sys, os, ctypes, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PORT = 3003
RULE_NAME = 'SGEA Servidor'
SEP = '  ' + '─' * 54

FIXES_APLICADOS  = []
PROBLEMAS_MANUAIS = []


def _cor(ok):
    return {True: '\033[92m✅', False: '\033[91m❌', None: '\033[93m⚠️ '}.get(ok, '')


def _reset(): return '\033[0m'


def titulo(txt):
    print(f'\n  \033[1m{txt}\033[0m')
    print(SEP)


def linha(label, status, detalhe='', fix=''):
    print(f'  {_cor(status)}  {label}{_reset()}')
    if detalhe:
        print(f'       {detalhe}')
    if fix:
        print(f'       \033[93m→ {fix}\033[0m')


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ps(cmd, timeout=15):
    """Executa um comando PowerShell e retorna stdout (string, vazio em erro)."""
    try:
        r = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', cmd],
            capture_output=True, text=True, timeout=timeout, encoding='utf-8', errors='replace'
        )
        return (r.stdout or '').strip()
    except Exception:
        return ''


# ── 1. Informações da máquina ─────────────────────────────────────────────────
def info_maquina():
    titulo('1. Informações da máquina')
    hostname = socket.gethostname()
    linha('Nome do computador', True, hostname)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip_local = s.getsockname()[0]
        s.close()
    except Exception:
        try:
            ip_local = socket.gethostbyname(hostname)
        except Exception:
            ip_local = 'não detectado'

    linha('IP local (rede)', True, ip_local)
    if ip_local not in ('não detectado', '127.0.0.1'):
        print(f'       \033[96mEndereço para outros computadores: http://{ip_local}:{PORT}/SGEA.html\033[0m')

    # DHCP vs. fixo — se for DHCP, o IP pode mudar e quebrar atalhos em outras máquinas
    dhcp = ps(f"(Get-NetIPAddress -IPAddress '{ip_local}' -ErrorAction SilentlyContinue).PrefixOrigin")
    mac = ps(f"(Get-NetAdapter | Where-Object {{ (Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress -eq '{ip_local}' }}).MacAddress")
    if dhcp.strip().lower() == 'dhcp':
        linha('Endereço IP', None, f'Obtido via DHCP — pode mudar e quebrar atalhos salvos em outras máquinas.',
              f'Peça ao TI uma reserva de IP fixo para o MAC {mac or "(não detectado)"}  ·  IP atual: {ip_local}')
        PROBLEMAS_MANUAIS.append(f'IP via DHCP (pode mudar) — peça reserva fixa para o TI. MAC: {mac or "?"}, IP atual: {ip_local}')
    elif dhcp:
        linha('Endereço IP', True, 'Configurado como fixo (não muda sozinho)')

    return ip_local


# ── 2. Porta 3003 ─────────────────────────────────────────────────────────────
def checar_porta():
    titulo(f'2. Porta {PORT}')
    em_uso = False
    try:
        test = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test.settimeout(1)
        em_uso = (test.connect_ex(('127.0.0.1', PORT)) == 0)
        test.close()
    except Exception:
        pass

    if em_uso:
        linha(f'Porta {PORT} em uso (servidor provavelmente ativo)', True)
    else:
        linha(f'Porta {PORT} livre — servidor não está rodando', None,
              'Inicie o servidor pelo Iniciar SGEA.bat para testar o acesso pela rede.')

    try:
        import urllib.request
        urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health', timeout=2)
        linha('Responde em localhost', True)
    except Exception as e:
        linha('Responde em localhost', False if em_uso else None,
              str(e) if em_uso else 'servidor não está ativo')

    return em_uso


# ── 3. Perfil de rede (Domínio / Privada / Pública) ───────────────────────────
def checar_perfil_rede():
    titulo('3. Perfil de rede')
    saida = ps("Get-NetConnectionProfile | Select-Object -ExpandProperty NetworkCategory")
    categorias = [c.strip() for c in saida.splitlines() if c.strip()]
    if not categorias:
        linha('Perfil de rede', None, 'Não foi possível detectar (sem adaptador ativo?)')
        return None

    publica = [c for c in categorias if c.lower() == 'public']
    if publica:
        linha('Perfil de rede', False, f'Detectado como "Pública" — o Windows bloqueia conexões de entrada por padrão nesse perfil.',
              'Isso impede outras máquinas de acessar o SGEA mesmo com a regra de firewall liberada.')
        if is_admin():
            resp = input('       Corrigir agora, marcando esta rede como "Privada"? '
                          '[s/N] (faça isso só se esta for uma rede confiável do seu local de trabalho): ').strip().lower()
            if resp == 's':
                ps("Get-NetConnectionProfile | Set-NetConnectionProfile -NetworkCategory Private")
                nova = ps("Get-NetConnectionProfile | Select-Object -ExpandProperty NetworkCategory")
                if 'private' in nova.lower():
                    linha('Perfil de rede corrigido', True, 'Definido como "Privada"')
                    FIXES_APLICADOS.append('Perfil de rede alterado de "Pública" para "Privada"')
                else:
                    PROBLEMAS_MANUAIS.append('Falha ao alterar perfil de rede para Privada — altere manualmente em Configurações de Rede do Windows.')
            else:
                PROBLEMAS_MANUAIS.append('Perfil de rede continua "Pública" — altere manualmente se confiar nesta rede.')
        else:
            PROBLEMAS_MANUAIS.append('Perfil de rede "Pública" — rode este diagnóstico como Administrador para corrigir automaticamente.')
        return False
    else:
        linha('Perfil de rede', True, ', '.join(categorias))
        return True


# ── 4. Firewall do Windows ────────────────────────────────────────────────────
def checar_firewall():
    titulo('4. Firewall do Windows')

    estado = ps("(Get-NetFirewallProfile | Where-Object Enabled -eq True).Name")
    if estado:
        perfis = ', '.join(l.strip() for l in estado.splitlines() if l.strip())
        linha('Windows Defender Firewall', None, f'Ativo nos perfis: {perfis} — regra de entrada será verificada')
    else:
        linha('Windows Defender Firewall', True, 'Desativado em todos os perfis (nenhuma regra necessária)')

    # Verifica TODAS as regras chamadas "SGEA Servidor" (podem existir duplicadas/quebradas de instalações antigas)
    detalhe = ps(
        f"Get-NetFirewallRule -DisplayName '{RULE_NAME}' -ErrorAction SilentlyContinue | "
        f"ForEach-Object {{ $f = $_ | Get-NetFirewallPortFilter; "
        f"\"$($_.Enabled)|$($_.Action)|$($_.Profile)|$($f.Protocol)|$($f.LocalPort)\" }}"
    )
    regras = [l for l in detalhe.splitlines() if l.strip()]

    regra_correta = False
    for r in regras:
        partes = r.split('|')
        if len(partes) == 5:
            enabled, action, profile, proto, port = partes
            if enabled == 'True' and action == 'Allow' and proto == 'TCP' and port == str(PORT):
                regra_correta = True
                break

    if regra_correta:
        linha(f'Regra de entrada para porta {PORT}', True, 'Encontrada, habilitada e correta (TCP/allow)')
        return True

    if regras:
        linha(f'Regra de entrada para porta {PORT}', False,
              f'Existe(m) {len(regras)} regra(s) chamada(s) "{RULE_NAME}", mas nenhuma está correta '
              '(desabilitada, bloqueando, ou porta/protocolo errados).')
    else:
        linha(f'Regra de entrada para porta {PORT}', False, 'Nenhuma regra encontrada.')

    if not is_admin():
        cmd = (f'netsh advfirewall firewall add rule name="{RULE_NAME}" '
               f'dir=in action=allow protocol=TCP localport={PORT}')
        linha('Correção automática indisponível', None,
              'Rode este diagnóstico como Administrador para corrigir automaticamente.',
              f'Ou execute manualmente como Admin:\n       {cmd}')
        PROBLEMAS_MANUAIS.append(f'Regra de firewall da porta {PORT} ausente/incorreta — rode como Administrador para corrigir.')
        return False

    # Remove qualquer regra antiga/quebrada com o mesmo nome e recria correta
    ps(f"Remove-NetFirewallRule -DisplayName '{RULE_NAME}' -ErrorAction SilentlyContinue")
    ps(
        f"New-NetFirewallRule -DisplayName '{RULE_NAME}' -Direction Inbound -Action Allow "
        f"-Protocol TCP -LocalPort {PORT} -Profile Any | Out-Null"
    )
    verifica = ps(
        f"Get-NetFirewallRule -DisplayName '{RULE_NAME}' -ErrorAction SilentlyContinue | "
        f"Select-Object -ExpandProperty Enabled"
    )
    if verifica.strip() == 'True':
        linha('Regra de firewall recriada', True, f'"{RULE_NAME}" — TCP {PORT}, entrada, permitir, todos os perfis')
        FIXES_APLICADOS.append(f'Regra de firewall "{RULE_NAME}" recriada corretamente (TCP {PORT}, allow, todos os perfis)')
        return True
    else:
        linha('Falha ao recriar a regra de firewall', False)
        PROBLEMAS_MANUAIS.append('Falha ao recriar a regra de firewall automaticamente — verifique manualmente.')
        return False


# ── 5. Antivírus de terceiros (firewall próprio, fora do alcance deste script) ─
def checar_antivirus():
    titulo('5. Antivírus / firewall de terceiros')
    saida = ps(
        "Get-CimInstance -Namespace 'root/SecurityCenter2' -ClassName AntiVirusProduct "
        "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty displayName"
    )
    produtos = [p.strip() for p in saida.splitlines() if p.strip()]
    terceiros = [p for p in produtos if 'defender' not in p.lower()]

    if terceiros:
        linha('Antivírus de terceiros detectado', None,
              f'{", ".join(terceiros)} — produtos assim costumam ter firewall próprio, '
              'separado do Firewall do Windows, que este diagnóstico não consegue verificar nem corrigir.',
              f'Se o acesso pela rede continuar falhando, libere a porta {PORT} manualmente nas configurações do {terceiros[0]}.')
        PROBLEMAS_MANUAIS.append(f'Antivírus de terceiros ({", ".join(terceiros)}) pode ter firewall próprio bloqueando a porta {PORT} — verifique manualmente.')
    else:
        linha('Antivírus de terceiros', True, 'Nenhum detectado (apenas Windows Defender)')


# ── 6. Outros dispositivos na rede (detecta isolamento de cliente / VLAN) ─────
def checar_outros_dispositivos(ip_local):
    titulo('6. Outros dispositivos na rede local')
    if ip_local in ('não detectado', '127.0.0.1', ''):
        linha('Varredura da rede', None, 'IP local não detectado — pulando')
        return

    prefixo = '.'.join(ip_local.split('.')[:3])
    gateway = ps("(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Select-Object -First 1).NextHop").strip()

    print(f'       Procurando outros dispositivos em {prefixo}.0/24 (isso pode levar ~15s)...')
    # Ping sweep rápido e paralelo via PowerShell, só pra popular a tabela ARP
    ps(
        f"1..254 | ForEach-Object -Parallel {{ "
        f"Test-Connection -ComputerName \"{prefixo}.$_\" -Count 1 -TimeoutSeconds 1 -Quiet -ErrorAction SilentlyContinue "
        f"}} -ThrottleLimit 64 | Out-Null",
        timeout=30
    )
    arp = ps("Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
             "Where-Object { $_.State -eq 'Reachable' -or $_.State -eq 'Stale' } | "
             "Select-Object -ExpandProperty IPAddress")
    vizinhos = sorted(set(
        ip for ip in (l.strip() for l in arp.splitlines())
        if ip.startswith(prefixo) and ip != ip_local
    ))

    if len(vizinhos) == 0:
        linha('Dispositivos alcançáveis na mesma rede', None,
              'Nenhum outro dispositivo respondeu — isso é comum quando a rede tem '
              '"isolamento de cliente" (AP isolation) ativado, que impede dispositivos '
              'Wi-Fi de se enxergarem entre si.',
              'Peça ao TI para desativar o isolamento de cliente entre estas máquinas, ou conectar o servidor por cabo.')
        PROBLEMAS_MANUAIS.append('Nenhum outro dispositivo visível na rede local — provável isolamento de cliente (AP isolation) ou VLAN separada. Precisa do TI.')
    else:
        linha('Dispositivos alcançáveis na mesma rede', True,
              f'{len(vizinhos)} encontrado(s): {", ".join(vizinhos[:10])}' + (' …' if len(vizinhos) > 10 else ''))
    if gateway:
        linha('Roteador/gateway', True, gateway)


# ── 7. Teste de acesso via IP local (auto-conexão) ────────────────────────────
def checar_conectividade(ip_local, servidor_ativo):
    titulo('7. Auto-teste de conexão pelo IP de rede')
    if ip_local in ('não detectado', '127.0.0.1', ''):
        linha('IP de rede', False, 'IP não detectado')
        return
    if not servidor_ativo:
        linha('Acesso pelo IP da rede', None, 'Inicie o servidor antes de testar.')
        return
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        r = s.connect_ex((ip_local, PORT))
        s.close()
        if r == 0:
            linha('Acesso pelo IP da rede (a partir desta máquina)', True,
                  f'http://{ip_local}:{PORT}/SGEA.html acessível')
        else:
            linha('Acesso pelo IP da rede (a partir desta máquina)', False, 'Conexão recusada.')
    except Exception as e:
        linha('Acesso pelo IP da rede', False, str(e))

    print()
    print(f'  \033[1mTeste real (peça para rodar em OUTRA máquina, com o servidor ligado aqui):\033[0m')
    print(f'  \033[96m  ping {ip_local}\033[0m')
    print(f'  \033[96m  Test-NetConnection -ComputerName {ip_local} -Port {PORT}\033[0m')
    print(f'  Se ambos falharem lá mas a internet funcionar normalmente, é isolamento de rede/VLAN — fora do alcance deste diagnóstico.')


# ── 8. Resumo ──────────────────────────────────────────────────────────────────
def resumo(ip, servidor_ativo, regra_fw, perfil_ok):
    print()
    print('  ' + '═' * 54)
    print('  \033[1mRESUMO\033[0m')
    print('  ' + '═' * 54)

    if FIXES_APLICADOS:
        print(f'  \033[92m✅  {len(FIXES_APLICADOS)} correção(ões) aplicada(s) automaticamente:\033[0m')
        for f in FIXES_APLICADOS:
            print(f'  \033[92m  • {f}\033[0m')
        print()

    problemas = list(PROBLEMAS_MANUAIS)
    if not servidor_ativo:
        problemas.insert(0, 'Servidor não está rodando — inicie pelo Iniciar SGEA.bat')
    if ip in ('não detectado', '127.0.0.1'):
        problemas.insert(0, 'IP de rede não detectado — verifique a conexão de rede')

    if not problemas:
        print(f'  \033[92m✅  Tudo certo do lado desta máquina! Endereço para a rede:\033[0m')
        print(f'  \033[96m    http://{ip}:{PORT}/SGEA.html\033[0m')
    else:
        print(f'  \033[91m❌  {len(problemas)} ponto(s) que ainda precisam de atenção:\033[0m')
        for i, p in enumerate(problemas, 1):
            print(f'  \033[93m  {i}. {p}\033[0m')
    print()


# ── Elevação automática (necessária para corrigir firewall/perfil de rede) ────
def _relancar_como_admin():
    print('  Algumas correções exigem privilégio de Administrador.')
    print('  Reabrindo este diagnóstico com elevação (uma janela do Windows vai pedir confirmação)...')
    params = ' '.join(f'"{a}"' for a in sys.argv)
    try:
        ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable, params, None, 1)
    except Exception as e:
        print(f'  Não foi possível elevar automaticamente ({e}). Rode este arquivo como Administrador manualmente.')
    input('  Pressione Enter para fechar esta janela...')
    sys.exit(0)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    os.system('color')
    print()
    print('  ╔══════════════════════════════════════════════════╗')
    print('  ║   SGEA — Diagnóstico e Correção de Rede          ║')
    print('  ╚══════════════════════════════════════════════════╝')

    if not is_admin():
        print()
        print('  \033[93m⚠️  Rodando sem privilégio de Administrador.\033[0m')
        print('       Este diagnóstico consegue corrigir automaticamente a regra de firewall')
        print('       e o perfil de rede, mas isso exige elevação.')
        resp = input('       Reabrir como Administrador agora? [S/n]: ').strip().lower()
        if resp != 'n':
            _relancar_como_admin()
        print('       Continuando sem elevação — correções serão só indicadas, não aplicadas.')

    ip             = info_maquina()
    servidor_ativo = checar_porta()
    perfil_ok      = checar_perfil_rede()
    regra_fw       = checar_firewall()
    checar_antivirus()
    checar_outros_dispositivos(ip)
    checar_conectividade(ip, servidor_ativo)
    resumo(ip, servidor_ativo, regra_fw, perfil_ok)

    input('  Pressione Enter para fechar...')
