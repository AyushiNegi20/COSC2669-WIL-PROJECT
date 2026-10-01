$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& '.\.venv-retrieval\Scripts\python.exe' -X utf8 scripts/serve_fintrace_demo.py --port 8771
if ($LASTEXITCODE -ne 0) { throw 'Demo startup failed. Check whether port 8771 is already in use, or Ollama is unavailable.' }
