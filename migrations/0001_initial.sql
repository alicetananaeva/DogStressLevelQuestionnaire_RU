CREATE TABLE IF NOT EXISTS dslq_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  app_version TEXT NOT NULL,
  consented_dog INTEGER NOT NULL CHECK (consented_dog = 1),
  dog_sex TEXT NOT NULL,
  dslq_chronic_score REAL NOT NULL,
  interpretation_band TEXT NOT NULL CHECK (
    interpretation_band IN ('normal', 'elevated', 'high', 'ultra_high')
  ),
  health_flag TEXT NOT NULL CHECK (
    health_flag IN ('none', 'reported', 'chronic')
  ),
  visual_scale_pos REAL NOT NULL,
  item_scores_json TEXT NOT NULL,
  behavior_answers_json TEXT NOT NULL,
  general_health_answers_json TEXT NOT NULL,
  research_choices_json TEXT NOT NULL,
  dog_demographics_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dslq_sessions_created_at
  ON dslq_sessions(created_at);

CREATE INDEX IF NOT EXISTS idx_dslq_sessions_band
  ON dslq_sessions(interpretation_band);
