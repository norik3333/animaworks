FROM python:3.12-slim

WORKDIR /app

# 0) Node.js + Claude Code CLI のインストール
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# 1) 依存関係だけ先にインストール（ソース変更時もキャッシュが効く）
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    "claude-agent-sdk>=0.1.40" \
    "anthropic>=0.42.0" \
    "openai-codex-sdk>=0.1.11,<0.2" \
    "litellm>=1.55.0" \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.34.0" \
    "apscheduler>=3.10.0" \
    "pydantic>=2.0" \
    "pydantic-settings>=2.0" \
    "httpx>=0.27.0" \
    "python-dotenv>=1.0" \
    "chromadb>=1.0.0" \
    "sentence-transformers>=2.2.0" \
    "numpy>=1.24.0" \
    "structlog>=24.1.0" \
    "orjson>=3.9.0" \
    "json-repair>=0.30.0" \
    "pwdlib[argon2]>=0.3.0" \
    "markdownify>=0.14.1" \
    "PyNaCl>=1.5.0" \
    "tzlocal>=5.0"

# 2) ソースコードをコピーしてパッケージとしてインストール
COPY core/ core/
COPY cli/ cli/
COPY server/ server/
COPY templates/ templates/
COPY main.py .
RUN pip install --no-cache-dir --no-deps .

EXPOSE 18500
CMD ["python", "main.py", "start", "--foreground", "--host", "0.0.0.0", "--port", "18500"]
