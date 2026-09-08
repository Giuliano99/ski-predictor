CREATE TABLE IF NOT EXISTS source_documents (
    id TEXT PRIMARY KEY, content_hash TEXT NOT NULL, kind TEXT NOT NULL,
    original_name TEXT NOT NULL, storage_reference TEXT NOT NULL,
    size_bytes INTEGER NOT NULL, modified_at TEXT NOT NULL, media_type TEXT NOT NULL,
    season_id TEXT, weekend_date TEXT, archived INTEGER NOT NULL DEFAULT 0,
    discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (storage_reference, content_hash)
);
CREATE INDEX IF NOT EXISTS source_documents_weekend_idx ON source_documents (weekend_date, kind);
CREATE INDEX IF NOT EXISTS source_documents_hash_idx ON source_documents (content_hash);

CREATE TABLE IF NOT EXISTS extraction_imports (
    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES source_documents(id),
    source_content_hash TEXT NOT NULL, extractor_version TEXT NOT NULL, source_format TEXT,
    status TEXT NOT NULL, extracted_at TEXT NOT NULL, approved_at TEXT,
    raw_payload TEXT NOT NULL CHECK (json_valid(raw_payload)),
    normalized_payload TEXT NOT NULL CHECK (json_valid(normalized_payload)),
    source_text TEXT NOT NULL,
    review_payload TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(review_payload)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS extraction_imports_document_idx ON extraction_imports (document_id, extracted_at DESC);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, event_date TEXT, location TEXT,
    payload TEXT NOT NULL CHECK (json_valid(payload))
);
CREATE TABLE IF NOT EXISTS races (
    id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(id), name TEXT NOT NULL,
    race_date TEXT, location TEXT, discipline TEXT NOT NULL, competition_number TEXT,
    payload TEXT NOT NULL CHECK (json_valid(payload))
);
CREATE INDEX IF NOT EXISTS races_date_idx ON races (race_date, discipline);
CREATE TABLE IF NOT EXISTS race_documents (
    race_id TEXT NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES source_documents(id),
    extraction_id TEXT NOT NULL REFERENCES extraction_imports(id), document_type TEXT NOT NULL,
    PRIMARY KEY (race_id, document_id)
);

CREATE TABLE IF NOT EXISTS athletes (
    id TEXT PRIMARY KEY, full_name TEXT NOT NULL, display_name TEXT NOT NULL,
    birth_year INTEGER, target_club INTEGER NOT NULL DEFAULT 0,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS athletes_name_idx ON athletes (lower(full_name), birth_year);

CREATE TABLE IF NOT EXISTS race_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT, race_id TEXT NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES source_documents(id), source_group_id TEXT NOT NULL,
    label TEXT NOT NULL, age_class TEXT, competition_category TEXT, classification_method TEXT,
    winner_time_seconds REAL, slowest_classified_time_seconds REAL,
    payload TEXT NOT NULL CHECK (json_valid(payload)), UNIQUE (document_id, source_group_id)
);
CREATE INDEX IF NOT EXISTS race_groups_race_idx ON race_groups (race_id, age_class, competition_category);

CREATE TABLE IF NOT EXISTS race_participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER NOT NULL REFERENCES race_groups(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES source_documents(id), race_id TEXT NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    athlete_id TEXT REFERENCES athletes(id), participant_type TEXT NOT NULL, start_number INTEGER NOT NULL,
    external_athlete_id TEXT, full_name TEXT NOT NULL, display_name TEXT NOT NULL, birth_year INTEGER,
    federation TEXT, club TEXT, target_club INTEGER NOT NULL DEFAULT 0, seed_points REAL,
    status TEXT, rank INTEGER, official_time_seconds REAL, gap_seconds REAL,
    percentage_gap REAL, federation_points REAL, payload TEXT NOT NULL CHECK (json_valid(payload)),
    UNIQUE (document_id, group_id, participant_type, start_number)
);
CREATE INDEX IF NOT EXISTS race_participants_athlete_idx ON race_participants (athlete_id, race_id);
CREATE INDEX IF NOT EXISTS race_participants_result_idx ON race_participants (race_id, participant_type, status, rank);

CREATE TABLE IF NOT EXISTS run_results (
    participant_id INTEGER NOT NULL REFERENCES race_participants(id) ON DELETE CASCADE,
    run_number INTEGER NOT NULL, status TEXT NOT NULL, time_seconds REAL,
    payload TEXT NOT NULL CHECK (json_valid(payload)), PRIMARY KEY (participant_id, run_number)
);
CREATE TABLE IF NOT EXISTS predictor_submissions (
    id TEXT PRIMARY KEY, tip_round_id TEXT NOT NULL, tip_round_version TEXT NOT NULL,
    player_id TEXT NOT NULL, player_display_name TEXT NOT NULL, submitted_at TEXT NOT NULL,
    answers TEXT NOT NULL CHECK (json_valid(answers)), raw_payload TEXT NOT NULL CHECK (json_valid(raw_payload)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS predictor_submissions_round_idx ON predictor_submissions (tip_round_id, submitted_at);
CREATE INDEX IF NOT EXISTS predictor_submissions_player_idx ON predictor_submissions (player_id, submitted_at);
