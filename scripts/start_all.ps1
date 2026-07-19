param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173
)

chcp 65001 > $null 2>&1
$env:PYTHONUTF8 = '1'
$ErrorActionPreference = 'Stop'

$scriptPath = $PSCommandPath
if (-not $scriptPath) { $scriptPath = $MyInvocation.MyCommand.Path }
$RootDir = Split-Path -Parent (Split-Path -Parent $scriptPath)
$BackendProcess = $null
$FrontendProcess = $null
$InstalledRuntimeTool = $false

function Write-Step {
  param([string]$Message)
  Write-Host "[start_all] $Message"
}

function Test-Command {
  param([string]$Name)
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-HttpOk {
  param([string]$Url)
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
  }
  catch {
    return $false
  }
}

function Test-ExistingService {
  $backendReady = Invoke-HttpOk "http://127.0.0.1:$BackendPort/healthz"
  $frontendReady = Invoke-HttpOk "http://127.0.0.1:$FrontendPort/api/system/status"
  if ($backendReady -and $frontendReady) {
    Write-Step '检测结果：日报系统原本就在运行，本次没有重复启动。'
    Write-Step "请直接在浏览器访问 http://127.0.0.1:$FrontendPort"
    return $true
  }
  return $false
}

function Test-PortInUse {
  param([int]$Port)
  $listener = $null
  try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $Port)
    $listener.Start()
    return $false
  }
  catch {
    return $true
  }
  finally {
    if ($listener) { $listener.Stop() }
  }
}

function Find-AvailablePort {
  param([int]$StartPort)
  $port = $StartPort
  for ($i = 0; $i -lt 100; $i++) {
    if (-not (Test-PortInUse -Port $port)) { return $port }
    $port++
  }
  throw "[start_all] 在 $StartPort 附近没有找到可用端口。"
}

function Ensure-EnvFile {
  $envPath = Join-Path $RootDir '.env'
  $examplePath = Join-Path $RootDir '.env.example'
  if (Test-Path -LiteralPath $envPath) { return }
  if (-not (Test-Path -LiteralPath $examplePath)) {
    throw '[start_all] 缺少 .env.example，无法自动生成 .env。'
  }
  Copy-Item -LiteralPath $examplePath -Destination $envPath
  Write-Step '已自动生成本机配置文件 .env。'
}

function Test-PythonCandidate {
  param(
    [string]$FilePath,
    [string[]]$Arguments
  )
  if (-not (Test-Command $FilePath)) { return $false }
  & $FilePath @Arguments -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" > $null 2>&1
  return ($LASTEXITCODE -eq 0)
}

function Get-CompatiblePython {
  $candidates = @(
    @{ File = 'py'; Args = @('-3.11') },
    @{ File = 'py'; Args = @() },
    @{ File = 'python'; Args = @() },
    @{ File = 'python3'; Args = @() }
  )
  foreach ($candidate in $candidates) {
    if (Test-PythonCandidate -FilePath $candidate.File -Arguments $candidate.Args) {
      return $candidate
    }
  }
  return $null
}

function Ensure-Winget {
  if (Test-Command 'winget') { return }
  throw '[start_all] 缺少 Python 或 Node.js，但没有检测到 winget，无法自动安装。请先安装 Python 3.11+ 和 Node.js 18+ 后重新启动。'
}

function Ensure-Python {
  $python = Get-CompatiblePython
  if ($python) { return $python }

  Write-Step '未检测到 Python 3.11 或更高版本，尝试通过 winget 自动安装。'
  Ensure-Winget
  $script:InstalledRuntimeTool = $true
  winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
  $python = Get-CompatiblePython
  if ($python) { return $python }
  throw '[start_all] Python 自动安装失败。请安装 Python 3.11 或更高版本后重新启动。'
}

function Test-NodeCompatible {
  if (-not (Test-Command 'node')) { return $false }
  node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 18 ? 0 : 1)" > $null 2>&1
  return ($LASTEXITCODE -eq 0)
}

function Ensure-Node {
  if (Test-NodeCompatible) { return }

  Write-Step '未检测到 Node.js 18 或更高版本，尝试通过 winget 自动安装。'
  Ensure-Winget
  $script:InstalledRuntimeTool = $true
  winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
  if (-not (Test-NodeCompatible)) {
    throw '[start_all] Node.js 自动安装失败。请安装 Node.js 18 或更高版本后重新启动。'
  }
}

function Invoke-Python {
  param(
    [hashtable]$Python,
    [string[]]$Arguments
  )
  & $Python.File @($Python.Args + $Arguments)
  return $LASTEXITCODE
}

function Add-CommonToolPaths {
  $paths = @(
    "$env:APPDATA\Python\Scripts",
    "$env:APPDATA\npm",
    "$env:LOCALAPPDATA\Programs\Python\Python311\Scripts",
    "$env:USERPROFILE\.local\bin"
  )
  foreach ($path in $paths) {
    if ($path -and (Test-Path -LiteralPath $path) -and ($env:PATH -notlike "*$path*")) {
      $env:PATH = "$path;$env:PATH"
    }
  }
}

function Ensure-Poetry {
  param([hashtable]$Python)
  Add-CommonToolPaths
  if (Test-Command 'poetry') { return }

  Write-Step '未检测到 Poetry，现在自动安装。'
  $script:InstalledRuntimeTool = $true
  $installer = Join-Path ([System.IO.Path]::GetTempPath()) 'install-poetry.py'
  try {
    Invoke-WebRequest -Uri 'https://install.python-poetry.org' -UseBasicParsing -OutFile $installer
    $exitCode = Invoke-Python -Python $Python -Arguments @($installer)
    if ($exitCode -ne 0) { throw 'poetry installer failed' }
  }
  finally {
    Remove-Item -LiteralPath $installer -ErrorAction SilentlyContinue
  }
  Add-CommonToolPaths
  if (-not (Test-Command 'poetry')) {
    throw '[start_all] Poetry 自动安装失败。请安装 Poetry 后重新启动。'
  }
}

function Ensure-Pnpm {
  Ensure-Node
  Add-CommonToolPaths
  if (Test-Command 'pnpm') { return }

  Write-Step '未检测到 pnpm，现在自动安装。'
  $script:InstalledRuntimeTool = $true
  if (Test-Command 'corepack') {
    corepack enable > $null 2>&1
    corepack prepare pnpm@latest --activate > $null 2>&1
  }
  Add-CommonToolPaths
  if (-not (Test-Command 'pnpm')) {
    if (-not (Test-Command 'npm')) {
      throw '[start_all] 未检测到 npm，无法自动安装 pnpm。请安装 Node.js LTS 后重新启动。'
    }
    npm install -g pnpm
    Add-CommonToolPaths
  }
  if (-not (Test-Command 'pnpm')) {
    throw '[start_all] pnpm 自动安装失败。请安装 pnpm 后重新启动。'
  }
}

function Ensure-RuntimeDependencies {
  Write-Step '第 1 步：检查电脑基础运行环境（Python/Node.js/Poetry/pnpm）。'
  $python = Ensure-Python
  Ensure-Node
  Ensure-Poetry -Python $python
  Ensure-Pnpm
  if ($InstalledRuntimeTool) {
    Write-Step '检查结果：缺少的电脑基础运行环境已自动安装完成。'
  }
  else {
    Write-Step '检查结果：电脑基础运行环境原本已齐全，本次没有安装新软件。'
  }
}

function Ensure-BackendProjectDependencies {
  Write-Step '第 2 步：检查后端环境依赖（项目里的 Python 包）。'
  Push-Location $RootDir
  try {
    $output = & poetry install --no-root --dry-run --no-ansi 2>&1
    $dryRunText = ($output | Out-String)
    if ($LASTEXITCODE -ne 0) {
      Write-Host $dryRunText
      throw '[start_all] 后端环境依赖检查失败。请保持这个窗口打开，将报错截图发给帮你的人。'
    }
    $ready = $dryRunText -like '*Package operations: 0 installs, 0 updates, 0 removals*'
    if ($ready) {
      Write-Step '检查结果：本地后端环境依赖已齐全，本次没有安装新依赖。'
      return
    }
    & poetry install --no-root --no-ansi
    if ($LASTEXITCODE -ne 0) {
      throw '[start_all] 后端环境依赖安装失败。请保持这个窗口打开，将报错截图发给帮你的人。'
    }
    Write-Step '检查结果：本地后端环境依赖已自动补齐。'
  }
  finally {
    Pop-Location
  }
}

function Ensure-FrontendProjectDependencies {
  Write-Step '第 3 步：检查网页环境依赖（项目里的网页包）。'
  $webDir = Join-Path $RootDir 'web'
  Push-Location $webDir
  try {
    $output = & pnpm install --reporter append-only 2>&1
    $installText = ($output | Out-String)
    if ($LASTEXITCODE -ne 0) {
      Write-Host $installText
      throw '[start_all] 网页环境依赖检查失败。请保持这个窗口打开，将报错截图发给帮你的人。'
    }
    if ($installText -like '*Already up to date*' -or $installText -like '*Lockfile is up to date*') {
      Write-Step '检查结果：本地网页环境依赖已齐全，本次没有安装新依赖。'
    }
    else {
      Write-Step '检查结果：本地网页环境依赖已自动补齐。'
    }
  }
  finally {
    Pop-Location
  }
}

function Stop-Services {
  $running = @($script:BackendProcess, $script:FrontendProcess) | Where-Object { $_ -and -not $_.HasExited }
  if (-not $running -or $running.Count -eq 0) { return }
  Write-Host ''
  Write-Step '正在停止服务...'
  foreach ($process in $running) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
  }
}

function Start-Services {
  $appMain = Join-Path $RootDir 'src\app\main.py'
  if (-not (Test-Path -LiteralPath $appMain)) {
    throw '[start_all] 项目结构不完整：缺少 src\app\main.py。'
  }

  $requestedBackendPort = $BackendPort
  $requestedFrontendPort = $FrontendPort
  $script:BackendPort = Find-AvailablePort -StartPort $requestedBackendPort
  $script:FrontendPort = Find-AvailablePort -StartPort $requestedFrontendPort

  if ($BackendPort -ne $requestedBackendPort) {
    Write-Step "$requestedBackendPort 端口已被其他软件占用，后端自动改用 $BackendPort。"
  }
  if ($FrontendPort -ne $requestedFrontendPort) {
    Write-Step "$requestedFrontendPort 端口已被其他软件占用，日报页面自动改用 $FrontendPort。"
  }

  $env:BACKEND_PORT = [string]$BackendPort
  $env:FRONTEND_PORT = [string]$FrontendPort

  Write-Step "启动后端 http://127.0.0.1:$BackendPort"
  $backendArgs = @('run', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', [string]$BackendPort, '--reload', '--app-dir', 'src')
  $script:BackendProcess = Start-Process -FilePath 'poetry' -ArgumentList $backendArgs -WorkingDirectory $RootDir -NoNewWindow -PassThru

  Write-Step "启动前端 http://127.0.0.1:$FrontendPort"
  $frontendArgs = @('dev', '--host', '0.0.0.0', '--port', [string]$FrontendPort, '--strictPort')
  $script:FrontendProcess = Start-Process -FilePath 'pnpm' -ArgumentList $frontendArgs -WorkingDirectory (Join-Path $RootDir 'web') -NoNewWindow -PassThru
}

function Test-ServicesReady {
  return ((Invoke-HttpOk "http://127.0.0.1:$BackendPort/healthz") -and (Invoke-HttpOk "http://127.0.0.1:$FrontendPort/"))
}

function Wait-ServicesReady {
  for ($i = 0; $i -lt 120; $i++) {
    if (Test-ServicesReady) { return }
    if ($BackendProcess -and $BackendProcess.HasExited) {
      throw '[start_all] 后端启动失败，请保持这个窗口打开，将报错截图发给帮你的人。'
    }
    if ($FrontendProcess -and $FrontendProcess.HasExited) {
      throw '[start_all] 前端启动失败，请保持这个窗口打开，将报错截图发给帮你的人。'
    }
    Start-Sleep -Milliseconds 500
  }
  throw '[start_all] 启动超时，请保持这个窗口打开，将报错截图发给帮你的人。'
}

try {
  if (Test-ExistingService) { exit 0 }
  Ensure-EnvFile
  Ensure-RuntimeDependencies
  Ensure-BackendProjectDependencies
  Ensure-FrontendProjectDependencies
  Start-Services
  Wait-ServicesReady

  Write-Host ''
  Write-Step '服务已启动。'
  Write-Host "  后端：http://127.0.0.1:$BackendPort"
  Write-Host "  前端：http://127.0.0.1:$FrontendPort"
  Write-Step "请打开这个日报页面：http://127.0.0.1:$FrontendPort"
  Write-Step '保持本窗口打开；按 Ctrl+C 或关闭窗口可停止服务。'

  Wait-Process -Id $BackendProcess.Id, $FrontendProcess.Id
}
finally {
  Stop-Services
}