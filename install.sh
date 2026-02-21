#!/bin/bash
# install.sh — Interactive setup for claude-vault-memory
# Usage: bash install.sh

set -e

echo "=== claude-vault-memory — Setup ==="
echo ""

# 1. Python dependencies
echo "[1/4] Installing Python packages..."
pip3 install voyageai qdrant-client openai --break-system-packages 2>/dev/null || \
pip3 install voyageai qdrant-client openai

echo "  ✓ voyageai, qdrant-client, openai installed"
echo ""

# 2. Config
if [ ! -f config.py ]; then
    echo "[2/4] Creating config.py from config.example.py..."
    cp config.example.py config.py
    echo "  → Edit config.py with your paths before continuing"
    echo "  → Then re-run: bash install.sh"
    exit 0
else
    echo "[2/4] config.py found ✓"
fi

# 3. API keys
echo ""
echo "[3/4] API keys configuration"
ENV_FILE=$(python3 -c "from config import ENV_FILE; print(ENV_FILE)" 2>/dev/null || echo "$HOME/.claude/hooks/.env")
mkdir -p "$(dirname "$ENV_FILE")"

echo "  [a] Voyage AI (embeddings, voyage-4-large) — https://dash.voyageai.com"
read -p "      VOYAGE_API_KEY (leave blank to configure manually in .env): " voyage_key
if [ -n "$voyage_key" ]; then
    if grep -q "VOYAGE_API_KEY" "$ENV_FILE" 2>/dev/null; then
        sed -i.bak "s|VOYAGE_API_KEY=.*|VOYAGE_API_KEY=$voyage_key|" "$ENV_FILE"
    else
        echo "VOYAGE_API_KEY=$voyage_key" >> "$ENV_FILE"
    fi
    echo "      ✓ Key saved to $ENV_FILE"
fi

echo "  [b] Fireworks (LLM extraction, end of session) — https://fireworks.ai"
read -p "      FIREWORKS_API_KEY (leave blank to configure manually in .env): " fireworks_key
if [ -n "$fireworks_key" ]; then
    if grep -q "FIREWORKS_API_KEY" "$ENV_FILE" 2>/dev/null; then
        sed -i.bak "s|FIREWORKS_API_KEY=.*|FIREWORKS_API_KEY=$fireworks_key|" "$ENV_FILE"
    else
        echo "FIREWORKS_API_KEY=$fireworks_key" >> "$ENV_FILE"
    fi
    echo "      ✓ Key saved to $ENV_FILE"
fi

# 4. Build initial index
echo ""
echo "[4/4] Building initial vector index..."
python3 vault_embed.py
echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Add vault_retrieve.py to UserPromptSubmit in ~/.claude/settings.json"
echo "  2. Configure the launchd plist (see launchd/com.example.vault-queue-worker.plist)"
echo "  3. Test: echo '{\"prompt\":\"your question\"}' | python3 vault_retrieve.py"
