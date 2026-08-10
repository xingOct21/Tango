-- 在 Supabase SQL Editor 里执行一次即可

-- 主键是 (jp, book)：同一条文本可以同时存在于不同单词本，各记各的进度。
-- 只用 jp 做主键会让 upsert 把已有行的 book 改掉，进度在两本之间互相覆盖。
CREATE TABLE IF NOT EXISTS word_progress (
  jp            TEXT    NOT NULL,
  book          TEXT    NOT NULL DEFAULT 'jp',
  level         INTEGER NOT NULL DEFAULT 0,
  next_review   DATE    NOT NULL DEFAULT CURRENT_DATE,
  last_reviewed DATE,
  review_count  INTEGER NOT NULL DEFAULT 0,
  mastered      BOOLEAN NOT NULL DEFAULT false,
  PRIMARY KEY (jp, book)
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

-- ============================================================
-- 迁移 v2.3：修复单词本之间的进度 / 额度污染
-- 老用户请在 Supabase SQL Editor 里执行下面这一段（先跑，再部署新代码）
--
-- 起因：v2.2 之前有一段时间英语本已经能出题，但后端还不认 book，
-- 写进来的行没有 book 列；v2.2 的 ADD COLUMN book ... DEFAULT 'jp'
-- 把这些英语行统统盖成了日语本，于是英语进度去占日语的每日额度。
-- 当时用 `SELECT book, count(*) GROUP BY book` 做的验证是恒真的，查不出这个问题。
-- ============================================================

-- 1) 先看有哪些行被错标了：属于日语本、但内容其实是英语本的题目
--    英语本第一列形如「中文问题\nEnglish question」，带一个字面量的反斜杠 n；
--    word.md 的 1146 条日语词里没有任何一条带它，所以这个判据不会误伤。
--    这里用 strpos 而不是 LIKE：LIKE 会把反斜杠当转义符，'%\n%' 反而等于匹配字母 n。
SELECT jp, book, level, review_count, last_reviewed
FROM word_progress
WHERE book = 'jp' AND strpos(jp, '\n') > 0;

-- 2) 把它们改回英语本。确认上面查出来的确实都是英语题目之后再执行
UPDATE word_progress
SET book = 'en'
WHERE book = 'jp' AND strpos(jp, '\n') > 0;

-- 3) 主键从 (jp) 改成 (jp, book)
--    这是 upsert 的冲突目标；不改的话同一条文本在两本之间会互相覆盖，
--    每被覆盖一次，level 和 review_count 就重置一次
ALTER TABLE word_progress DROP CONSTRAINT IF EXISTS word_progress_pkey;
ALTER TABLE word_progress ADD PRIMARY KEY (jp, book);

-- 4) 让 PostgREST 立刻重新读取表结构（Supabase 通常会自动重载，执行一次更保险）
NOTIFY pgrst, 'reload schema';
