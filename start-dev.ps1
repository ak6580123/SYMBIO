# Starts the Symbio backend (FastAPI/uvicorn) and frontend (Next.js) together,
# each in its own PowerShell window.

$root = $PSScriptRoot

$backendCmd = "Set-Location '$root'; " +
    "& '$root\venv\Scripts\Activate.ps1'; " +
    "uvicorn backend.main:app --reload"

$frontendCmd = "Set-Location '$root\frontend'; npm run dev"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

Write-Host "Backend starting at http://localhost:8000"
Write-Host "Frontend starting at http://localhost:3000"
