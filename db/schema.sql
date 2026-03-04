-- Open Brain schema
-- Requires pgvector extension

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Embedding dimension is configured at table creation time.
-- Default 1024 matches mxbai-embed-large. If you change the embedding model,
-- recreate the table (or alter the column) to match the new dimension.
-- Common dimensions: nomic-embed-text=768, mxbai-embed-large=1024

CREATE TABLE IF NOT EXISTS brain_entries (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_text        TEXT NOT NULL,
    embedding       vector(1024),
    entry_type      VARCHAR(50) NOT NULL DEFAULT 'observation'
                        CHECK (entry_type IN (
                            'observation', 'decision', 'action_item',
                            'reference', 'project_note'
                        )),
    topics          TEXT[] NOT NULL DEFAULT '{}',
    people          TEXT[] NOT NULL DEFAULT '{}',
    projects        TEXT[] NOT NULL DEFAULT '{}',
    action_items    TEXT[] NOT NULL DEFAULT '{}',
    source_client   VARCHAR(100) NOT NULL DEFAULT 'unknown',
    relevance_score FLOAT NOT NULL DEFAULT 0.0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes

-- IVFFlat index for approximate nearest neighbor search on embeddings.
-- The index requires existing rows to build lists; if the table is empty
-- at migration time the index is still created but will be rebuilt on first use.
-- lists = 100 is a reasonable starting point for up to ~100k rows.
CREATE INDEX IF NOT EXISTS idx_brain_entries_embedding
    ON brain_entries
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Recency queries
CREATE INDEX IF NOT EXISTS idx_brain_entries_created_at
    ON brain_entries (created_at DESC);

-- Tag filtering
CREATE INDEX IF NOT EXISTS idx_brain_entries_topics
    ON brain_entries
    USING GIN (topics);

-- Entry type filtering
CREATE INDEX IF NOT EXISTS idx_brain_entries_entry_type
    ON brain_entries (entry_type);

-- Project filtering
CREATE INDEX IF NOT EXISTS idx_brain_entries_projects
    ON brain_entries
    USING GIN (projects);
