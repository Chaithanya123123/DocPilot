# Starts the DocPilot backend (http://127.0.0.1:8000)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $root "backend")
if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created backend/.env from template - add your MISTRAL_API_KEY." -ForegroundColor Yellow
}
python -m uvicorn app.main:app --reload --port 8000
