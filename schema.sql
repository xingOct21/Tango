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

-- ============================================================
-- 迁移 v2.2：多单词本 + 每本额度独立
-- 老用户请在 Supabase SQL Editor 里单独执行下面这一段
-- ============================================================

-- 进度按单词本区分。分书之前只有日语本，故存量行默认归为 'jp'
ALTER TABLE word_progress ADD COLUMN IF NOT EXISTS book TEXT NOT NULL DEFAULT 'jp';

CREATE INDEX IF NOT EXISTS word_progress_book_last_reviewed_idx
  ON word_progress (book, last_reviewed);

-- 每日额度按单词本分开存储，键名形如 new_words_limit_jp
-- 日语本沿用原全局设置的值，找不到则用默认值
INSERT INTO app_settings (key, value)
SELECT 'new_words_limit_jp',
       COALESCE((SELECT value FROM app_settings WHERE key = 'new_words_limit'), '10')
ON CONFLICT (key) DO NOTHING;

INSERT INTO app_settings (key, value)
SELECT 'review_words_limit_jp',
       COALESCE((SELECT value FROM app_settings WHERE key = 'review_words_limit'), '20')
ON CONFLICT (key) DO NOTHING;

INSERT INTO app_settings (key, value) VALUES ('new_words_limit_en', '10') ON CONFLICT (key) DO NOTHING;
INSERT INTO app_settings (key, value) VALUES ('review_words_limit_en', '20') ON CONFLICT (key) DO NOTHING;
