# Conversational Robot — Windows/Desktop Setup
# Run: .\scripts\setup_desktop.ps1

$ErrorActionPreference = "Stop"
$RobotDir = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

Write-Host "══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Conversational Robot — Desktop Setup (Simulate)" -ForegroundColor Cyan
Write-Host "══════════════════════════════════════════════════" -ForegroundColor Cyan

# ── 1. Check Python ──────────────────────────────────────────
Write-Host "`n[1/4] Checking Python..." -ForegroundColor Yellow
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "  ✗ Python not found. Install Python 3.11+ from python.org" -ForegroundColor Red
    exit 1
}
python --version

# ── 2. Create virtual environment ────────────────────────────
Write-Host "`n[2/4] Setting up virtual environment..." -ForegroundColor Yellow
$venvDir = Join-Path $RobotDir ".venv"
if (-not (Test-Path $venvDir)) {
    python -m venv $venvDir
}
& "$venvDir\Scripts\Activate.ps1"
pip install --upgrade pip | Out-Null

# Install desktop-compatible deps (no RPi.GPIO, no picamera2)
pip install requests sseclient-py numpy Pillow

# Try PyAudio (needs pre-built wheel on Windows)
Write-Host "  Installing PyAudio..." -ForegroundColor Gray
pip install pyaudio 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ⚠ PyAudio failed — will use text input for audio. Install manually if needed." -ForegroundColor DarkYellow
}

Write-Host "  ✓ Virtual environment ready" -ForegroundColor Green

# ── 3. Download llama.cpp pre-built binary ───────────────────
Write-Host "`n[3/4] Setting up llama.cpp..." -ForegroundColor Yellow
$llamaDir = Join-Path $RobotDir "llama.cpp"
if (-not (Test-Path (Join-Path $llamaDir "llama-server.exe"))) {
    Write-Host "  Downloading llama.cpp Windows build..." -ForegroundColor Gray
    $llamaRelease = "https://github.com/ggml-org/llama.cpp/releases/latest/download/llama-bin-win-x64.zip"
    $zipPath = Join-Path $RobotDir "llama-bin.zip"
    
    Invoke-WebRequest -Uri $llamaRelease -OutFile $zipPath -UseBasicParsing
    
    if (-not (Test-Path $llamaDir)) { New-Item -ItemType Directory -Path $llamaDir | Out-Null }
    Expand-Archive -Path $zipPath -DestinationPath $llamaDir -Force
    Remove-Item $zipPath
    Write-Host "  ✓ llama.cpp binaries extracted" -ForegroundColor Green
} else {
    Write-Host "  ✓ llama.cpp already present" -ForegroundColor Green
}

# ── 4. Download Gemma 4 E4B model ────────────────────────────
Write-Host "`n[4/4] Downloading Gemma 4 E4B model (~4 GB)..." -ForegroundColor Yellow
$modelsDir = Join-Path $RobotDir "models"
if (-not (Test-Path $modelsDir)) { New-Item -ItemType Directory -Path $modelsDir | Out-Null }

$modelFile = Join-Path $modelsDir "gemma-4-e4b-it-q4_k_m.gguf"
if (-not (Test-Path $modelFile)) {
    Write-Host "  This will take a while (~4 GB download)..." -ForegroundColor Gray
    $modelUrl = "https://huggingface.co/bartowski/google_gemma-4-4b-it-GGUF/resolve/main/google_gemma-4-4b-it-Q4_K_M.gguf"
    
    # Use BITS transfer for resume support
    Start-BitsTransfer -Source $modelUrl -Destination $modelFile -DisplayName "Downloading Gemma 4 E4B"
    
    Write-Host "  ✓ Model downloaded" -ForegroundColor Green
} else {
    Write-Host "  ✓ Model already exists" -ForegroundColor Green
}

# ── Done ─────────────────────────────────────────────────────
Write-Host "`n══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  To start:" -ForegroundColor White
Write-Host "    1. Start llama.cpp server:" -ForegroundColor Gray
Write-Host "       .\scripts\start_llama_server.ps1" -ForegroundColor White
Write-Host ""
Write-Host "    2. In another terminal, run the robot in simulate mode:" -ForegroundColor Gray
Write-Host "       .\.venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "       python openclaw/main.py --simulate" -ForegroundColor White
Write-Host "══════════════════════════════════════════════════" -ForegroundColor Cyan
