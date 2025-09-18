#!/bin/bash

# Setup script for macOS with Apple Silicon (M1/M2/M3/M4)
# This script configures Ollama to run natively for GPU support via Metal Performance Shaders

echo "============================================"
echo "Minitools Setup for macOS (Apple Silicon)"
echo "============================================"
echo ""

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ Error: This script is for macOS only"
    exit 1
fi

# Check for Apple Silicon
if [[ $(uname -m) != "arm64" ]]; then
    echo "⚠️  Warning: Not running on Apple Silicon. GPU acceleration may not be available."
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed."
    echo "Please install Docker Desktop from: https://docs.docker.com/desktop/install/mac-install/"
    exit 1
fi

echo "✅ Docker is installed"

# Check if Docker is running
if ! docker info &> /dev/null; then
    echo "❌ Docker is not running. Please start Docker Desktop."
    exit 1
fi

echo "✅ Docker is running"

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo ""
    echo "⚠️  Ollama is not installed."
    echo ""
    echo "To use GPU acceleration on macOS, Ollama must be installed natively."
    echo "Docker containers cannot access Apple Silicon GPUs (Metal/MPS)."
    echo ""
    echo "Would you like to install Ollama now? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        echo "Installing Ollama..."
        curl -fsSL https://ollama.ai/install.sh | sh

        if command -v ollama &> /dev/null; then
            echo "✅ Ollama installed successfully"
        else
            echo "❌ Ollama installation failed. Please install manually from: https://ollama.com/download/mac"
            exit 1
        fi
    else
        echo ""
        echo "Please install Ollama manually from: https://ollama.com/download/mac"
        echo "Without native Ollama, processing will be significantly slower (CPU-only in Docker)."
        echo ""
    fi
else
    echo "✅ Ollama is installed"
fi

# Check if Ollama is running
if command -v ollama &> /dev/null; then
    if ! curl -s http://localhost:11434/api/tags &> /dev/null; then
        echo ""
        echo "⚠️  Ollama is installed but not running."
        echo "Starting Ollama..."

        # Try to start Ollama in the background
        nohup ollama serve > /dev/null 2>&1 &
        sleep 5

        if curl -s http://localhost:11434/api/tags &> /dev/null; then
            echo "✅ Ollama started successfully"
        else
            echo "❌ Failed to start Ollama. Please start it manually with: ollama serve"
        fi
    else
        echo "✅ Ollama is running on http://localhost:11434"
    fi

    # Check for required models
    echo ""
    echo "Checking for required models..."

    models_output=$(ollama list 2>/dev/null)

    if ! echo "$models_output" | grep -q "gemma3:27b"; then
        echo "⚠️  Model gemma3:27b is not installed."
        echo "Would you like to download it now? (y/n) [~16GB download]"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            echo "Downloading gemma3:27b (this may take a while)..."
            ollama pull gemma3:27b
        fi
    else
        echo "✅ Model gemma3:27b is available"
    fi

    if ! echo "$models_output" | grep -q "gemma3:12b"; then
        echo "⚠️  Model gemma3:12b is not installed."
        echo "Would you like to download it now? (y/n) [~8GB download]"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            echo "Downloading gemma3:12b (this may take a while)..."
            ollama pull gemma3:12b
        fi
    else
        echo "✅ Model gemma3:12b is available"
    fi
fi

# Check for configuration files
echo ""
echo "Checking configuration files..."

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "Creating .env from .env.example..."
        cp .env.example .env
        echo "⚠️  Please edit .env and add your API keys"
    else
        echo "❌ .env file not found. Please create it with your API keys."
    fi
else
    echo "✅ .env file exists"
fi

if [ ! -f "settings.yaml" ]; then
    if [ -f "settings.yaml.example" ]; then
        echo "Creating settings.yaml from settings.yaml.example..."
        cp settings.yaml.example settings.yaml
        echo "✅ settings.yaml created"
    else
        echo "⚠️  settings.yaml not found"
    fi
else
    echo "✅ settings.yaml exists"
fi

# Build Docker images
echo ""
echo "Building Docker images..."
docker-compose -f docker-compose.mac.yml build

if [ $? -eq 0 ]; then
    echo "✅ Docker images built successfully"
else
    echo "❌ Failed to build Docker images"
    exit 1
fi

echo ""
echo "============================================"
echo "✨ Setup Complete!"
echo "============================================"
echo ""
echo "macOS Configuration:"
echo "- Ollama runs natively for GPU acceleration (Metal/MPS)"
echo "- Minitools runs in Docker and connects to host Ollama"
echo ""
echo "Quick Start Commands:"
echo "  make arxiv        # Search and translate ArXiv papers"
echo "  make medium       # Process Medium Daily Digest"
echo "  make google       # Process Google Alerts"
echo "  make youtube      # Summarize YouTube videos"
echo ""
echo "Note: Ensure Ollama is always running when using minitools."
echo "You can start it with: ollama serve"
echo ""