CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_documents (
    id text PRIMARY KEY,
    content_hash text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('START_LIST', 'RESULT_LIST', 'UNKNOWN')),
    original_name text NOT NULL,
    storage_reference text NOT NULL,
    size_bytes bigint NOT NULL,
    modified_at timestamptz NOT NULL,
    media_type text NOT NULL,
    season_id text,
    weekend_date date,
    archived boolean NOT NULL DEFAULT false,
    discovered_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (storage_reference, content_hash)
);
CREATE INDEX IF NOT EXISTS source_documents_weekend_idx ON source_documents (weekend_date, kind);
CREATE INDEX IF NOT EXISTS source_documents_hash_idx ON source_documents (content_hash);

CREATE TABLE IF NOT EXISTS extraction_imports (
    id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES source_documents(id),
    source_content_hash text NOT NULL,
    extractor_version text NOT NULL,
    source_format text,
    status text NOT NULL CHECK (status IN ('REVIEW_REQUIRED', 'APPROVED', 'FAILED')),
    extracted_at timestamptz NOT NULL,
    approved_at timestamptz,
    raw_payload jsonb NOT NULL,
    normalized_payload jsonb NOT NULL,
    source_text text NOT NULL,
    review_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS extraction_imports_document_idx ON extraction_imports (document_id, extracted_at DESC);
CREATE INDEX IF NOT EXISTS extraction_imports_raw_gin_idx ON extraction_imports USING gin (raw_payload);

CREATE TABLE IF NOT EXISTS events (
    id text PRIMARY KEY,
    name text NOT NULL,
    event_date date,
    location text,
    payload jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS races (
    id text PRIMARY KEY,
    event_id text NOT NULL REFERENCES events(id),
    name text NOT NULL,
    race_date date,
    location text,
    discipline text NOT NULL,
    competition_number text,
    payload jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS races_date_idx ON races (race_date, discipline);

CREATE TABLE IF NOT EXISTS race_documents (
    race_id text NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    document_id text NOT NULL REFERENCES source_documents(id),
    extraction_id text NOT NULL REFERENCES extraction_imports(id),
    document_type text NOT NULL,
    PRIMARY KEY (race_id, document_id)
);

CREATE TABLE IF NOT EXISTS athletes (
    id text PRIMARY KEY,
    full_name text NOT NULL,
    display_name text NOT NULL,
    birth_year integer,
    target_club boolean NOT NULL DEFAULT false,
    payload jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS athletes_name_idx ON athletes (lower(full_name), birth_year);

CREATE TABLE IF NOT EXISTS race_groups (
    id bigserial PRIMARY KEY,
    race_id text NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    document_id text NOT NULL REFERENCES source_documents(id),
    source_group_id text NOT NULL,
    label text NOT NULL,
    age_class text,
    competition_category text,
    classification_method text,
    winner_time_seconds numeric,
    slowest_classified_time_seconds numeric,
    payload jsonb NOT NULL,
    UNIQUE (document_id, source_group_id)
);
CREATE INDEX IF NOT EXISTS race_groups_race_idx ON race_groups (race_id, age_class, competition_category);

CREATE TABLE IF NOT EXISTS race_participants (
    id bigserial PRIMARY KEY,
    group_id bigint NOT NULL REFERENCES race_groups(id) ON DELETE CASCADE,
    document_id text NOT NULL REFERENCES source_documents(id),
    race_id text NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    athlete_id text REFERENCES athletes(id),
    participant_type text NOT NULL CHECK (participant_type IN ('START', 'RESULT')),
    start_number integer NOT NULL,
    external_athlete_id text,
    full_name text NOT NULL,
    display_name text NOT NULL,
    birth_year integer,
    federation text,
    club text,
    target_club boolean NOT NULL DEFAULT false,
    seed_points numeric,
    status text,
    rank integer,
    official_time_seconds numeric,
    gap_seconds numeric,
    percentage_gap numeric,
    federation_points numeric,
    payload jsonb NOT NULL,
    UNIQUE (document_id, group_id, participant_type, start_number)
);
CREATE INDEX IF NOT EXISTS race_participants_athlete_idx ON race_participants (athlete_id, race_id);
CREATE INDEX IF NOT EXISTS race_participants_result_idx ON race_participants (race_id, participant_type, status, rank);

CREATE TABLE IF NOT EXISTS run_results (
    participant_id bigint NOT NULL REFERENCES race_participants(id) ON DELETE CASCADE,
    run_number integer NOT NULL,
    status text NOT NULL,
    time_seconds numeric,
    payload jsonb NOT NULL,
    PRIMARY KEY (participant_id, run_number)
);

CREATE TABLE IF NOT EXISTS predictor_submissions (
    id text PRIMARY KEY,
    tip_round_id text NOT NULL,
    tip_round_version text NOT NULL,
    player_id text NOT NULL,
    player_display_name text NOT NULL,
    submitted_at timestamptz NOT NULL,
    answers jsonb NOT NULL,
    raw_payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS predictor_submissions_round_idx ON predictor_submissions (tip_round_id, submitted_at);
CREATE INDEX IF NOT EXISTS predictor_submissions_player_idx ON predictor_submissions (player_id, submitted_at);
