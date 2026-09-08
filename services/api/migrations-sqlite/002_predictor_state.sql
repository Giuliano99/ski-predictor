CREATE TABLE IF NOT EXISTS predictor_rounds (
    id TEXT PRIMARY KEY, season_id TEXT NOT NULL, weekend_date TEXT NOT NULL,
    title TEXT NOT NULL, status TEXT NOT NULL, content_version TEXT,
    opens_at TEXT, closes_at TEXT,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS predictor_rounds_current_idx ON predictor_rounds (status, weekend_date DESC);

CREATE TABLE IF NOT EXISTS predictor_questions (
    tip_round_id TEXT NOT NULL REFERENCES predictor_rounds(id) ON DELETE CASCADE,
    id TEXT NOT NULL, position INTEGER NOT NULL, question_type TEXT NOT NULL,
    prompt TEXT NOT NULL, race_label TEXT,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    PRIMARY KEY (tip_round_id, id)
);

CREATE TABLE IF NOT EXISTS predictor_round_status_history (
    tip_round_id TEXT NOT NULL REFERENCES predictor_rounds(id) ON DELETE CASCADE,
    position INTEGER NOT NULL, status TEXT NOT NULL, changed_at TEXT, reason TEXT,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    PRIMARY KEY (tip_round_id, position)
);

CREATE TABLE IF NOT EXISTS weekend_evaluations (
    tip_round_id TEXT PRIMARY KEY REFERENCES predictor_rounds(id) ON DELETE CASCADE,
    season_id TEXT NOT NULL, tip_round_version TEXT, generated_at TEXT,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS season_leaderboards (
    season_id TEXT PRIMARY KEY, generated_at TEXT,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
