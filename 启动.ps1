$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    Write-Host '请先运行 python -m venv .venv，再运行 .venv\Scripts\python.exe -m pip install -r requirements.txt'
    exit 1
}
$env:PYTHONIOENCODING = 'utf-8'
& $taskPython (Join-Path $PSScriptRoot 'scripts\start.py')
exit $LASTEXITCODE
