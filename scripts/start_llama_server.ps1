# Start llama.cpp server on Windows
# Run: .\scripts\start_llama_server.ps1

$RobotDir = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$ModelPath = Join-Path $RobotDir "models\gemma-4-e4b-it-q4_k_m.gguf"

# Find llama-server binary
$LlamaServer = $null
$candidates = @(
    (Join-Path $RobotDir "llama.cpp\llama-server.exe"),
    (Join-Path $RobotDir "llama.cpp\bin\llama-server.exe"),
    (Join-Path $RobotDir "llama.cpp\build\bin\Release\llama-server.exe"),
    "llama-server"  # system PATH
)
foreach ($c in $candidates) {
    if (Test-Path $c -ErrorAction SilentlyContinue) { $LlamaServer = $c; break }
    if (Get-Command $c -ErrorAction SilentlyContinue) { $LlamaServer = $c; break }
}

if (-not $LlamaServer) {
    Write-Host "✗ llama-server not found. Run setup_desktop.ps1 first." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ModelPath)) {
    Write-Host "✗ Model not found at $ModelPath. Run setup_desktop.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host "Starting llama.cpp server..." -ForegroundColor Cyan
Write-Host "  Binary: $LlamaServer" -ForegroundColor Gray
Write-Host "  Model:  $ModelPath" -ForegroundColor Gray
Write-Host ""

& $LlamaServer `
    -m $ModelPath `
    --host 127.0.0.1 `
    --port 8080 `
    -c 4096 `
    -t 4 `
    --n-predict 256
