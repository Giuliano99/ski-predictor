CREATE TABLE IF NOT EXISTS app_users (
    id text PRIMARY KEY,
    username text NOT NULL UNIQUE,
    display_name text NOT NULL,
    password_hash text NOT NULL,
    role text NOT NULL CHECK (role IN ('PLAYER', 'GAME_MASTER')),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS app_users_username_lower_idx ON app_users (lower(username));

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash text PRIMARY KEY,
    user_id text NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    csrf_token text NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS auth_sessions_user_idx ON auth_sessions (user_id, expires_at DESC);

ALTER TABLE predictor_submissions ADD COLUMN IF NOT EXISTS authenticated_user_id text REFERENCES app_users(id);
CREATE INDEX IF NOT EXISTS predictor_submissions_auth_user_idx ON predictor_submissions (authenticated_user_id, tip_round_id, submitted_at DESC);
