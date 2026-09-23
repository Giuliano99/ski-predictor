CREATE TABLE IF NOT EXISTS dsv_ranking_snapshots (
    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES source_documents(id),
    extraction_id TEXT NOT NULL REFERENCES extraction_imports(id), document_code TEXT NOT NULL,
    season_id TEXT NOT NULL, published_at TEXT NOT NULL, timezone TEXT NOT NULL,
    payload TEXT NOT NULL CHECK (json_valid(payload)), UNIQUE (document_code, published_at)
);
CREATE INDEX IF NOT EXISTS dsv_ranking_snapshots_season_idx ON dsv_ranking_snapshots (season_id, published_at DESC);
CREATE TABLE IF NOT EXISTS dsv_ranking_entries (
    snapshot_id TEXT NOT NULL REFERENCES dsv_ranking_snapshots(id) ON DELETE CASCADE,
    scope TEXT NOT NULL, scope_label TEXT NOT NULL, gender TEXT NOT NULL,
    athlete_id TEXT REFERENCES athletes(id), external_athlete_id TEXT NOT NULL,
    first_name TEXT NOT NULL, last_name TEXT NOT NULL, birth_year INTEGER NOT NULL,
    club TEXT NOT NULL, federation TEXT, base_points REAL NOT NULL, list_points REAL NOT NULL,
    overall_rank INTEGER, age_class_rank INTEGER, birth_year_rank INTEGER,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    PRIMARY KEY (snapshot_id, scope_label, gender, external_athlete_id)
);
CREATE INDEX IF NOT EXISTS dsv_ranking_entries_athlete_idx ON dsv_ranking_entries (athlete_id, snapshot_id);
CREATE INDEX IF NOT EXISTS dsv_ranking_entries_external_idx ON dsv_ranking_entries (external_athlete_id, snapshot_id);

CREATE TABLE IF NOT EXISTS dsv_race_count_snapshots (
    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES source_documents(id),
    extraction_id TEXT NOT NULL REFERENCES extraction_imports(id), document_code TEXT NOT NULL,
    season_id TEXT NOT NULL, observed_at TEXT NOT NULL, timezone TEXT NOT NULL,
    complete_season_field INTEGER NOT NULL DEFAULT 0,
    payload TEXT NOT NULL CHECK (json_valid(payload)), UNIQUE (document_code, observed_at)
);
CREATE INDEX IF NOT EXISTS dsv_race_count_snapshots_season_idx ON dsv_race_count_snapshots (season_id, observed_at DESC);
CREATE TABLE IF NOT EXISTS dsv_race_count_entries (
    snapshot_id TEXT NOT NULL REFERENCES dsv_race_count_snapshots(id) ON DELETE CASCADE,
    age_class TEXT NOT NULL, athlete_id TEXT REFERENCES athletes(id),
    external_athlete_id TEXT NOT NULL, first_name TEXT NOT NULL, last_name TEXT NOT NULL,
    birth_year INTEGER NOT NULL, club TEXT NOT NULL, federation TEXT, gender TEXT NOT NULL,
    base_points REAL NOT NULL, list_points REAL NOT NULL, race_count INTEGER NOT NULL,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    PRIMARY KEY (snapshot_id, age_class, external_athlete_id)
);
CREATE INDEX IF NOT EXISTS dsv_race_count_entries_athlete_idx ON dsv_race_count_entries (athlete_id, snapshot_id);
CREATE INDEX IF NOT EXISTS dsv_race_count_entries_external_idx ON dsv_race_count_entries (external_athlete_id, snapshot_id);
