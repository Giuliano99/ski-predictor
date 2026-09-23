ALTER TABLE source_documents DROP CONSTRAINT IF EXISTS source_documents_kind_check;
ALTER TABLE source_documents ADD CONSTRAINT source_documents_kind_check
    CHECK (kind IN ('START_LIST', 'RESULT_LIST', 'DSV_RANKING', 'DSV_RACE_COUNT', 'UNKNOWN'));

CREATE TABLE IF NOT EXISTS dsv_ranking_snapshots (
    id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES source_documents(id),
    extraction_id text NOT NULL REFERENCES extraction_imports(id),
    document_code text NOT NULL,
    season_id text NOT NULL,
    published_at timestamp NOT NULL,
    timezone text NOT NULL,
    payload jsonb NOT NULL,
    UNIQUE (document_code, published_at)
);
CREATE INDEX IF NOT EXISTS dsv_ranking_snapshots_season_idx
    ON dsv_ranking_snapshots (season_id, published_at DESC);

CREATE TABLE IF NOT EXISTS dsv_ranking_entries (
    snapshot_id text NOT NULL REFERENCES dsv_ranking_snapshots(id) ON DELETE CASCADE,
    scope text NOT NULL,
    scope_label text NOT NULL,
    gender text NOT NULL,
    athlete_id text REFERENCES athletes(id),
    external_athlete_id text NOT NULL,
    first_name text NOT NULL,
    last_name text NOT NULL,
    birth_year integer NOT NULL,
    club text NOT NULL,
    federation text,
    base_points numeric NOT NULL,
    list_points numeric NOT NULL,
    overall_rank integer,
    age_class_rank integer,
    birth_year_rank integer,
    payload jsonb NOT NULL,
    PRIMARY KEY (snapshot_id, scope_label, gender, external_athlete_id)
);
CREATE INDEX IF NOT EXISTS dsv_ranking_entries_athlete_idx
    ON dsv_ranking_entries (athlete_id, snapshot_id);
CREATE INDEX IF NOT EXISTS dsv_ranking_entries_external_idx
    ON dsv_ranking_entries (external_athlete_id, snapshot_id);

CREATE TABLE IF NOT EXISTS dsv_race_count_snapshots (
    id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES source_documents(id),
    extraction_id text NOT NULL REFERENCES extraction_imports(id),
    document_code text NOT NULL,
    season_id text NOT NULL,
    observed_at timestamp NOT NULL,
    timezone text NOT NULL,
    complete_season_field boolean NOT NULL DEFAULT false,
    payload jsonb NOT NULL,
    UNIQUE (document_code, observed_at)
);
CREATE INDEX IF NOT EXISTS dsv_race_count_snapshots_season_idx
    ON dsv_race_count_snapshots (season_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS dsv_race_count_entries (
    snapshot_id text NOT NULL REFERENCES dsv_race_count_snapshots(id) ON DELETE CASCADE,
    age_class text NOT NULL,
    athlete_id text REFERENCES athletes(id),
    external_athlete_id text NOT NULL,
    first_name text NOT NULL,
    last_name text NOT NULL,
    birth_year integer NOT NULL,
    club text NOT NULL,
    federation text,
    gender text NOT NULL,
    base_points numeric NOT NULL,
    list_points numeric NOT NULL,
    race_count integer NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (snapshot_id, age_class, external_athlete_id)
);
CREATE INDEX IF NOT EXISTS dsv_race_count_entries_athlete_idx
    ON dsv_race_count_entries (athlete_id, snapshot_id);
CREATE INDEX IF NOT EXISTS dsv_race_count_entries_external_idx
    ON dsv_race_count_entries (external_athlete_id, snapshot_id);
