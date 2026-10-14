param([int]$Port = 8010)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$agentExecutable = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $agentExecutable)) {
    throw 'Install dependencies into .venv first. See README.md.'
}
& $agentExecutable scripts/serve.py --port $Port
exit $LASTEXITCODE
