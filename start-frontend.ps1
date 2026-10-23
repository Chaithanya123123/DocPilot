# Starts the DocPilot frontend (http://localhost:5173)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $root "frontend")
npm run dev
