# Đóng gói Python và dependency để người dùng installer không phải cài Python.
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = 'python' }

& $python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name tool-crawler-backend `
  --distpath build/backend-dist `
  --workpath build/backend-work `
  --specpath build `
  --paths src `
  --collect-all playwright `
  --hidden-import crawl_pipeline `
  --hidden-import cookie_refresh `
  --hidden-import xuat_csv `
  server.py

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
