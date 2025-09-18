# GPU Setup Guide for Minitools

このガイドでは、各プラットフォームでGPUアクセラレーションを有効にする方法を説明します。

## プラットフォーム別GPU対応状況

| プラットフォーム | GPU | 対応状況 | 設定方法 |
|-----------------|-----|---------|----------|
| macOS (Apple Silicon) | Metal/MPS | ✅ ネイティブのみ | Ollama.appをホストで実行 |
| Windows | NVIDIA CUDA | ✅ Docker対応 | docker-compose.windows.yml |
| Linux | NVIDIA CUDA | ✅ Docker対応 | docker-compose.yml + nvidia-runtime |

## macOS (Apple Silicon M1/M2/M3/M4) 設定

### 問題点
- **Docker Desktop for MacはGPUアクセスをサポートしていません**
- コンテナ内のOllamaはCPUのみで動作し、5-6倍遅くなります

### 解決策: ハイブリッド構成

```bash
# 1. セットアップスクリプトを実行
chmod +x setup-mac.sh
./setup-mac.sh

# 2. Ollamaをネイティブで起動（GPU使用）
ollama serve

# 3. Minitoolsを実行（Dockerコンテナからホストのollamaに接続）
make medium
```

#### 仕組み
- **Ollama**: ホストmacOSで直接実行（Metal Performance Shaders使用）
- **Minitools**: Dockerコンテナで実行、`host.docker.internal:11434`経由で接続

#### パフォーマンス比較
- ネイティブOllama: ~100 tokens/秒（M2 Pro）
- Docker内Ollama: ~15-20 tokens/秒（CPUのみ）

## Windows (NVIDIA GPU) 設定

### 前提条件
1. NVIDIA GPU（CUDA対応）
2. 最新のNVIDIAドライバ
3. WSL2
4. [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)

### セットアップ

```powershell
# 1. セットアップスクリプトを実行（PowerShell管理者権限）
Set-ExecutionPolicy Bypass -Scope Process -Force
.\setup-windows.ps1

# 2. GPU対応Docker Composeで起動
make up  # 自動的にdocker-compose.windows.ymlを使用

# 3. GPUが認識されているか確認
nvidia-smi
docker logs ollama
```

#### GPU設定内容
```yaml
# docker-compose.windows.yml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
runtime: nvidia
environment:
  - NVIDIA_VISIBLE_DEVICES=all
```

## Linux (NVIDIA GPU) 設定

### 前提条件
1. NVIDIA GPU
2. NVIDIA Driverインストール済み
3. NVIDIA Container Toolkit

### セットアップ

```bash
# 1. NVIDIA Container Toolkitインストール
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 2. 起動
docker-compose up -d

# 3. GPU確認
nvidia-smi
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
```

## トラブルシューティング

### macOS: Ollamaが遅い
- Docker内で実行していないか確認
- `ollama serve`がホストで起動しているか確認
- Activity Monitorで`ollama`プロセスのGPU使用率を確認

### Windows: GPUが認識されない
```powershell
# WSL2内でGPU確認
wsl
nvidia-smi

# Docker内でGPU確認
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
```

### 共通: メモリ不足
- `gemma3:27b`は約16GB VRAM必要
- メモリ不足の場合は`gemma3:12b`や`gemma2:9b`を使用

## パフォーマンスチューニング

### macOS最適化
```bash
# Metal Performance Shadersの確認
system_profiler SPDisplaysDataType | grep Metal

# Ollamaのメモリ設定
export OLLAMA_NUM_PARALLEL=4
export OLLAMA_MAX_LOADED_MODELS=2
```

### Windows/Linux NVIDIA最適化
```bash
# CUDAバージョン確認
nvidia-smi

# Docker Compose設定でGPUメモリ制限
deploy:
  resources:
    limits:
      nvidia.com/gpu: 1
    reservations:
      devices:
        - capabilities: [gpu]
          driver: nvidia
          device_ids: ['0']  # 特定のGPUを指定
```

## ベンチマーク結果

| プラットフォーム | モデル | 処理速度 | メモリ使用量 |
|-----------------|--------|----------|--------------|
| M2 Pro (ネイティブ) | gemma3:27b | ~100 tokens/s | 16GB |
| M2 Pro (Docker) | gemma3:27b | ~15 tokens/s | 16GB |
| RTX 4090 | gemma3:27b | ~200 tokens/s | 16GB |
| RTX 3070 | gemma3:12b | ~120 tokens/s | 8GB |

## 関連リンク

- [Ollama公式ドキュメント](https://ollama.com/docs)
- [Apple Metal Performance Shaders](https://developer.apple.com/documentation/metalperformanceshaders)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)
- [Docker GPU Support](https://docs.docker.com/compose/gpu-support/)