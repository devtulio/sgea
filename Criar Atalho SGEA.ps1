# Cria atalho "Iniciar SGEA.lnk" na Area de Trabalho com icone personalizado
$batPath  = Join-Path $PSScriptRoot "Iniciar SGEA.bat"
$icoPath  = Join-Path $PSScriptRoot "sgea.ico"
$desktop  = [Environment]::GetFolderPath("Desktop")
$lnkPath  = Join-Path $desktop "Iniciar SGEA.lnk"

$wsh  = New-Object -ComObject WScript.Shell
$link = $wsh.CreateShortcut($lnkPath)
$link.TargetPath       = $batPath
$link.IconLocation     = "$icoPath,0"
$link.WorkingDirectory = $PSScriptRoot
$link.WindowStyle      = 7
$link.Description      = "SGEA - Sistema de Gestao de Estoque do Almoxarifado"
$link.Save()

Write-Host "Atalho criado em: $lnkPath" -ForegroundColor Green
