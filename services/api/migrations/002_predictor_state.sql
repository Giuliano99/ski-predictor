CREATE TABLE IF NOT EXISTS predictor_rounds (
    id text PRIMARY KEY,
    season_id text NOT NULL,
    weekend_date date NOT NULL,
    title text NOT NULL,
    status text NOT NULL,
    content_version text,
    opens_at timestamptz,
    closes_at timestamptz,
    payload jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS predictor_rounds_current_idx ON predictor_rounds (status, weekend_date DESC);

CREATE TABLE IF NOT EXISTS predictor_questions (
    tip_round_id text NOT NULL REFERENCES predictor_rounds(id) ON DELETE CASCADE,
    id text NOT NULL,
    position integer NOT NULL,
    question_type text NOT NULL,
    prompt text NOT NULL,
    race_label text,
    payload jsonb NOT NULL,
    PRIMARY KEY (tip_round_id, id)
);

CREATE TABLE IF NOT EXISTS predictor_round_status_history (
    tip_round_id text NOT NULL REFERENCES predictor_rounds(id) ON DELETE CASCADE,
    position integer NOT NULL,
    status text NOT NULL,
    changed_at timestamptz,
    reason text,
    payload jsonb NOT NULL,
    PRIMARY KEY (tip_round_id, position)
);

CREATE TABLE IF NOT EXISTS weekend_evaluations (
    tip_round_id text PRIMARY KEY REFERENCES predictor_rounds(id) ON DELETE CASCADE,
    season_id text NOT NULL,
    tip_round_version text,
    generated_at timestamptz,
    payload jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS season_leaderboards (
    season_id text PRIMARY KEY,
    generated_at timestamptz,
    payload jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
