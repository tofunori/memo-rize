# config.example.py — Copy to config.py and adapt to your environment
# config.py is in .gitignore — never commit your personal paths or keys.

# ─── Paths ────────────────────────────────────────────────────────────────────

# Directory containing your atomic notes (.md files)
VAULT_NOTES_DIR = "/home/yourname/notes"

# Directory where Qdrant stores its on-disk index
QDRANT_PATH = "/home/yourname/.claude/hooks/vault_qdrant"

# .env file containing API keys
ENV_FILE = "/home/yourname/.claude/hooks/.env"

# Queue directory (async tickets)
QUEUE_DIR = "/home/yourname/.claude/hooks/queue"

# Log file
LOG_FILE = "/home/yourname/.claude/hooks/auto_remember.log"


# ─── Models ───────────────────────────────────────────────────────────────────

# Cohere embeddings (multilingual, 1024 dims)
COHERE_EMBED_MODEL = "embed-multilingual-v3.0"
EMBED_DIM = 1024

# LLM for fact extraction (via OpenAI-compatible API)
FIREWORKS_MODEL = "accounts/fireworks/models/kimi-k2p5"
FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"


# ─── Thresholds ───────────────────────────────────────────────────────────────

# Active retrieval: minimum cosine score to surface a note
RETRIEVE_SCORE_THRESHOLD = 0.60
RETRIEVE_TOP_K = 3

# Semantic deduplication: minimum score to consider a duplicate
DEDUP_THRESHOLD = 0.85

# Minimum message length (chars) to trigger retrieval
MIN_QUERY_LENGTH = 20

# Minimum number of turns in a session to enqueue for extraction
MIN_TURNS = 5

# Maximum batch size for Cohere API calls
COHERE_BATCH_SIZE = 96
