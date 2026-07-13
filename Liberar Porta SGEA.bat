@echo off
echo.
echo  SGEA — Liberar porta 3003 no Firewall do Windows
echo  -------------------------------------------------
echo  Este arquivo precisa ser executado como Administrador.
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo  ERRO: Execute este arquivo clicando com o botao direito
    echo        e escolhendo "Executar como administrador".
    echo.
    pause
    exit /b 1
)

netsh advfirewall firewall show rule name="SGEA Servidor" >nul 2>&1
if not errorlevel 1 (
    echo  A regra "SGEA Servidor" ja existe no firewall.
) else (
    netsh advfirewall firewall add rule name="SGEA Servidor" dir=in action=allow protocol=TCP localport=3003
    echo  Regra criada com sucesso! Porta 3003 liberada para conexoes de entrada.
)

echo.
echo  Pressione qualquer tecla para fechar...
pause >nul
