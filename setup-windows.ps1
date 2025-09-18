# Setup script for Windows with NVIDIA GPU support
# This script configures Docker and Ollama with CUDA support

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Minitools Setup for Windows (NVIDIA GPU)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check if running on Windows
if (-not ($PSVersionTable.Platform -eq $null -or $PSVersionTable.Platform -eq "Win32NT")) {
    Write-Host "Error: This script is for Windows only" -ForegroundColor Red
    exit 1
}

# Check if running as Administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "Warning: Not running as Administrator. Some features may require admin privileges." -ForegroundColor Yellow
}

# Check if Docker is installed
$dockerInstalled = Get-Command docker -ErrorAction SilentlyContinue

if (-not $dockerInstalled) {
    Write-Host "Docker is not installed." -ForegroundColor Red
    Write-Host "Please install Docker Desktop from: https://docs.docker.com/desktop/install/windows-install/" -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ Docker is installed" -ForegroundColor Green

# Check if Docker is running
try {
    docker info | Out-Null
    Write-Host "✓ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "Docker is not running. Please start Docker Desktop." -ForegroundColor Red
    exit 1
}

# Check for WSL2
Write-Host ""
Write-Host "Checking WSL2 configuration..." -ForegroundColor Cyan

$wslVersion = wsl --list --verbose 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "WSL2 is not installed or configured." -ForegroundColor Yellow
    Write-Host "For GPU support, WSL2 is required. Please install it from:" -ForegroundColor Yellow
    Write-Host "https://docs.microsoft.com/en-us/windows/wsl/install" -ForegroundColor Yellow
} else {
    Write-Host "✓ WSL2 is available" -ForegroundColor Green
}

# Check for NVIDIA GPU
Write-Host ""
Write-Host "Checking for NVIDIA GPU..." -ForegroundColor Cyan

$nvidiaGPU = Get-WmiObject Win32_VideoController | Where-Object { $_.Name -match "NVIDIA" }

if ($nvidiaGPU) {
    Write-Host "✓ NVIDIA GPU detected: $($nvidiaGPU.Name)" -ForegroundColor Green

    # Check for nvidia-smi
    $nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($nvidiaSmi) {
        Write-Host "✓ NVIDIA drivers installed" -ForegroundColor Green

        # Display GPU info
        Write-Host ""
        Write-Host "GPU Information:" -ForegroundColor Cyan
        nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
    } else {
        Write-Host "NVIDIA drivers not found. Please install the latest NVIDIA drivers." -ForegroundColor Yellow
    }

    # Check for NVIDIA Container Toolkit
    Write-Host ""
    Write-Host "Checking NVIDIA Container Toolkit..." -ForegroundColor Cyan

    try {
        docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi | Out-Null
        Write-Host "✓ NVIDIA Container Toolkit is working" -ForegroundColor Green
    } catch {
        Write-Host "NVIDIA Container Toolkit is not configured properly." -ForegroundColor Yellow
        Write-Host "Please install it from:" -ForegroundColor Yellow
        Write-Host "https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html" -ForegroundColor Yellow
    }
} else {
    Write-Host "No NVIDIA GPU detected." -ForegroundColor Yellow
    Write-Host "The system will run in CPU-only mode, which will be significantly slower." -ForegroundColor Yellow
}

# Check for configuration files
Write-Host ""
Write-Host "Checking configuration files..." -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Write-Host "Creating .env from .env.example..."
        Copy-Item ".env.example" ".env"
        Write-Host "Please edit .env and add your API keys" -ForegroundColor Yellow
    } else {
        Write-Host ".env file not found. Please create it with your API keys." -ForegroundColor Red
    }
} else {
    Write-Host "✓ .env file exists" -ForegroundColor Green
}

if (-not (Test-Path "settings.yaml")) {
    if (Test-Path "settings.yaml.example") {
        Write-Host "Creating settings.yaml from settings.yaml.example..."
        Copy-Item "settings.yaml.example" "settings.yaml"
        Write-Host "✓ settings.yaml created" -ForegroundColor Green
    } else {
        Write-Host "settings.yaml not found" -ForegroundColor Yellow
    }
} else {
    Write-Host "✓ settings.yaml exists" -ForegroundColor Green
}

# Gmail credentials check
if (-not (Test-Path "credentials.json")) {
    Write-Host "Gmail credentials.json not found (required for Medium/Google Alerts)" -ForegroundColor Yellow
}

# Build Docker images
Write-Host ""
Write-Host "Building Docker images with GPU support..." -ForegroundColor Cyan

docker-compose -f docker-compose.windows.yml build

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Docker images built successfully" -ForegroundColor Green
} else {
    Write-Host "Failed to build Docker images" -ForegroundColor Red
    exit 1
}

# Start Ollama with models
Write-Host ""
Write-Host "Starting Ollama service..." -ForegroundColor Cyan

docker-compose -f docker-compose.windows.yml up -d ollama ollama-setup

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Ollama started successfully" -ForegroundColor Green

    Write-Host ""
    Write-Host "Waiting for models to download (this may take a while)..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10

    # Check Ollama status
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing
        Write-Host "✓ Ollama is accessible" -ForegroundColor Green
    } catch {
        Write-Host "Ollama is not responding. Check docker logs with: docker logs ollama" -ForegroundColor Yellow
    }
} else {
    Write-Host "Failed to start Ollama" -ForegroundColor Red
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "✨ Setup Complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Windows Configuration:" -ForegroundColor Cyan
if ($nvidiaGPU) {
    Write-Host "- NVIDIA GPU support enabled via CUDA" -ForegroundColor Green
} else {
    Write-Host "- Running in CPU-only mode (no GPU detected)" -ForegroundColor Yellow
}
Write-Host "- Ollama runs in Docker with full GPU acceleration" -ForegroundColor Green
Write-Host ""
Write-Host "Quick Start Commands:" -ForegroundColor Cyan
Write-Host "  make arxiv        # Search and translate ArXiv papers"
Write-Host "  make medium       # Process Medium Daily Digest"
Write-Host "  make google       # Process Google Alerts"
Write-Host "  make youtube      # Summarize YouTube videos"
Write-Host ""
Write-Host "GPU Monitoring:" -ForegroundColor Cyan
Write-Host "  nvidia-smi        # Check GPU usage"
Write-Host "  docker logs ollama # Check Ollama logs"
Write-Host ""