$root = $PSScriptRoot

Write-Host "Starting Market Intelligence Agent..." -ForegroundColor Cyan

Start-Process powershell -ArgumentList "-NoExit", "-Command", `
  "cd '$root\market-agent'; Write-Host 'FastAPI (port 8000)' -ForegroundColor Yellow; .venv\Scripts\uvicorn server:app --reload --port 8000"

Start-Process powershell -ArgumentList "-NoExit", "-Command", `
  "cd '$root\market-agent'; Write-Host 'ADK Playground (port 8001)' -ForegroundColor Yellow; .venv\Scripts\adk web --port 8001"

Start-Process powershell -ArgumentList "-NoExit", "-Command", `
  "cd '$root\market-agent\frontend'; Write-Host 'Frontend (port 3000)' -ForegroundColor Yellow; npm run dev"

Write-Host ""
Write-Host "All servers starting in separate windows:" -ForegroundColor Green
Write-Host "  Frontend:       http://localhost:3000" -ForegroundColor White
Write-Host "  ADK Playground: http://localhost:8001" -ForegroundColor White
Write-Host "  FastAPI:        http://localhost:8000/docs" -ForegroundColor White
