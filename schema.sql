-- 在 Supabase SQL Editor 里执行一次即可

CREATE TABLE IF NOT EXISTS word_progress (
  jp            TEXT PRIMARY KEY,
  level         INTEGER NOT NULL DEFAULT 0,
  next_review   DATE    NOT NULL DEFAULT CURRENT_DATE,
  last_reviewed DATE
);

CREATE TABLE IF NOT EXISTS app_settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- 默认每日上限 20 个
INSERT INTO app_settings (key, value)
VALUES ('daily_limit', '20')
ON CONFLICT (key) DO NOTHING;
