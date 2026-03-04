-- Token usage tracking
-- Append-only log of every LLM/embedding call with token counts and cost estimates.

CREATE TABLE IF NOT EXISTS token_usage (
    id                BIGSERIAL PRIMARY KEY,
    provider          VARCHAR(50) NOT NULL,          -- 'ollama', 'nvidia', 'openai', etc.
    model             VARCHAR(100) NOT NULL,          -- 'qwen3:8b', 'mxbai-embed-large', etc.
    operation         VARCHAR(50) NOT NULL DEFAULT 'chat',  -- 'classify', 'extract', 'embed', 'chat'
    prompt_tokens     INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    total_tokens      INT GENERATED ALWAYS AS (prompt_tokens + completion_tokens) STORED,
    estimated_cost    NUMERIC(12, 8) NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Fast lookups for dashboard queries
CREATE INDEX IF NOT EXISTS idx_token_usage_created_at
    ON token_usage (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_token_usage_provider_model
    ON token_usage (provider, model);

CREATE INDEX IF NOT EXISTS idx_token_usage_operation
    ON token_usage (operation);
