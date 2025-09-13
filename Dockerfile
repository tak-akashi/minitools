# Multi-stage build for minitools
# Stage 1: Base dependencies
FROM python:3.11-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ffmpeg \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Stage 2: Development environment (includes all extras)
FROM base AS development

# Copy application code first (needed for local package build)
COPY minitools ./minitools
COPY scripts ./scripts
COPY settings.yaml.example ./settings.yaml.example
COPY docker-entrypoint.sh ./docker-entrypoint.sh

# Make entrypoint script executable
RUN chmod +x ./docker-entrypoint.sh

# Install all dependencies including whisper
RUN uv sync --extra whisper --no-editable

# Create necessary directories
RUN mkdir -p outputs/logs outputs/temp

# Stage 3: Production environment (minimal dependencies)
FROM base AS production

# Copy application code first (needed for local package build)
COPY minitools ./minitools
COPY scripts ./scripts
COPY settings.yaml.example ./settings.yaml.example
COPY docker-entrypoint.sh ./docker-entrypoint.sh

# Make entrypoint script executable
RUN chmod +x ./docker-entrypoint.sh

# Install only core dependencies
RUN uv sync --no-editable

# Create necessary directories
RUN mkdir -p outputs/logs outputs/temp

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["--help"]