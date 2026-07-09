-- 在 Supabase SQL Editor 里执行一次即可

CREATE TABLE IF NOT EXISTS word_progress (
  jp            TEXT PRIMARY KEY,
  level         INTEGER NOT NULL DEFAULT 0,
  next_review   DATE    NOT NULL DEFAULT CURRENT_DATE,
  last_reviewed DATE,
  review_count  INTEGER NOT NULL DEFAULT 0,
  mastered      BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS app_settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- 默认每日新词/复习词上限
INSERT INTO app_settings (key, value)
VALUES ('new_words_limit', '10')
ON CONFLICT (key) DO NOTHING;

INSERT INTO app_settings (key, value)
VALUES ('review_words_limit', '20')
ON CONFLICT (key) DO NOTHING;

-- ============================================================
-- 增量迁移：如果你是已经执行过旧版 schema.sql 的老用户，
-- 只需要在 Supabase SQL Editor 里单独执行下面这一段即可
-- ============================================================

ALTER TABLE word_progress ADD COLUMN IF NOT EXISTS review_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE word_progress ADD COLUMN IF NOT EXISTS mastered BOOLEAN NOT NULL DEFAULT false;
UPDATE word_progress SET review_count = 1 WHERE review_count = 0;

INSERT INTO app_settings (key, value) VALUES ('new_words_limit', '10') ON CONFLICT (key) DO NOTHING;
INSERT INTO app_settings (key, value) VALUES ('review_words_limit', '20') ON CONFLICT (key) DO NOTHING;
