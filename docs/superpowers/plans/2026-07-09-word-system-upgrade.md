# 新词系统 + 斩词 + 继续学习 + 自由复习 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split daily study into independently-limited new-word and review-word pools, formalize per-word review counts, add a "斩词"(mastery) flow that permanently retires maxed-out words, let users lift today's limits to keep drilling due words, and let them freely replay today's studied words without touching SRS state.

**Architecture:** This is a small single-file Flask backend (`app.py`) backed by Supabase Postgres, plus a single-file vanilla-JS frontend (`templates/index.html`). All changes are additive edits to these existing files — no new modules, no new dependencies. The two design docs this plan implements are `docs/superpowers/specs/2026-07-09-new-word-system-design.md` and `docs/superpowers/specs/2026-07-09-mastery-continue-freereview-design.md`.

**Tech Stack:** Python 3 / Flask, Supabase Python SDK, vanilla HTML/CSS/JS. No test framework exists in this repo (confirmed: no `pytest` installed, no `tests/` directory) — verification is done by running the Flask dev server locally and hitting endpoints with `curl`, matching the project's existing all-manual-verification convention.

**Prerequisite for every backend task's verification steps:** a local Flask dev server needs valid `SUPABASE_URL` / `SUPABASE_KEY` env vars (the same Supabase project used for deployment, or a scratch project). Start it with:

```bash
python app.py
```

It listens on `http://localhost:5001`.

---

### Task 1: Database schema migration

**Files:**
- Modify: `schema.sql`

- [ ] **Step 1: Rewrite `schema.sql` with the new columns and settings keys**

Replace the entire file content with:

```sql
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
```

- [ ] **Step 2: Run the incremental migration block against your live Supabase project**

This is a manual step you (the user) run yourself in the Supabase SQL Editor — it alters a live table, so it's not something to automate. Copy just the block under `-- 增量迁移` (the `ALTER TABLE` / `UPDATE` / two `INSERT` statements) and execute it once in the SQL Editor for your existing project. Confirm success by running:

```sql
SELECT jp, review_count, mastered FROM word_progress LIMIT 5;
SELECT * FROM app_settings;
```

Expected: every existing row has `review_count = 1` and `mastered = false`; `app_settings` now has 4 rows (`daily_limit` left over from before, plus `new_words_limit`, `review_words_limit`, and whatever else existed).

- [ ] **Step 3: Commit**

```bash
git add schema.sql
git commit -m "Add review_count/mastered columns and new/review daily limits to schema"
```

---

### Task 2: Track per-word review count

**Files:**
- Modify: `app.py:19-37` (`get_progress`, `save_progress`)
- Modify: `app.py:96-113` (`review`)

- [ ] **Step 1: Update `get_progress` to select `review_count`**

Find:

```python
def get_progress():
    res = sb.table("word_progress").select("jp,level,next_review,last_reviewed").execute()
    return {row["jp"]: row for row in res.data}
```

Replace with:

```python
def get_progress():
    res = sb.table("word_progress").select(
        "jp,level,next_review,last_reviewed,review_count,mastered"
    ).execute()
    return {row["jp"]: row for row in res.data}
```

- [ ] **Step 2: Update `save_progress` to accept and persist `review_count`**

Find:

```python
def save_progress(jp, level, next_review_date):
    today = date.today().isoformat()
    sb.table("word_progress").upsert({
        "jp": jp,
        "level": level,
        "next_review": next_review_date,
        "last_reviewed": today,
    }).execute()
```

Replace with:

```python
def save_progress(jp, level, next_review_date, review_count):
    today = date.today().isoformat()
    sb.table("word_progress").upsert({
        "jp": jp,
        "level": level,
        "next_review": next_review_date,
        "last_reviewed": today,
        "review_count": review_count,
    }).execute()
```

- [ ] **Step 3: Update `review()` to compute and pass the incremented count**

Find:

```python
@app.route("/api/review", methods=["POST"])
def review():
    data = request.get_json()
    jp = data["jp"]
    score = int(data["score"])

    progress = get_progress()
    current_level = progress.get(jp, {}).get("level", 0)

    if score == 1:
        new_level = max(0, current_level - 1)
    elif score == 2:
        new_level = current_level
    else:
        new_level = min(5, current_level + 1)

    save_progress(jp, new_level, next_review(new_level))
    return jsonify({"ok": True})
```

Replace with:

```python
@app.route("/api/review", methods=["POST"])
def review():
    data = request.get_json()
    jp = data["jp"]
    score = int(data["score"])

    progress = get_progress()
    current = progress.get(jp, {})
    current_level = current.get("level", 0)
    current_count = current.get("review_count", 0)

    if score == 1:
        new_level = max(0, current_level - 1)
    elif score == 2:
        new_level = current_level
    else:
        new_level = min(5, current_level + 1)

    new_count = current_count + 1
    save_progress(jp, new_level, next_review(new_level), new_count)

    return jsonify({"ok": True, "level": new_level, "reached_max_level": new_level == 5})
```

Note: `reached_max_level` is added here too (needed by Task 3's frontend flow) since it falls naturally out of this same edit — no separate endpoint round-trip needed.

- [ ] **Step 4: Verify with the dev server**

```bash
python app.py &
sleep 2
curl -s -X POST http://localhost:5001/api/review -H "Content-Type: application/json" \
  -d '{"jp": "テスト単語", "score": 3}'
```

Expected output: `{"level":1,"ok":true,"reached_max_level":false}`

```bash
curl -s -X POST http://localhost:5001/api/review -H "Content-Type: application/json" \
  -d '{"jp": "テスト単語", "score": 3}'
```

Run this 4 more times (5 total `score: 3` calls) — the 5th response should be:
`{"level":5,"ok":true,"reached_max_level":true}`

```bash
kill %1
```

- [ ] **Step 5: Clean up the test row and commit**

```sql
-- Run in Supabase SQL Editor to remove the scratch row created above
DELETE FROM word_progress WHERE jp = 'テスト単語';
```

```bash
git add app.py
git commit -m "Track per-word review_count and report reached_max_level from /api/review"
```

---

### Task 3: Mastery (斩词)

**Files:**
- Modify: `app.py` (add `/api/mastery` route, filter mastered words out of `/api/next`)

- [ ] **Step 1: Add the `/api/mastery` endpoint**

Insert this new route right after the `review()` function (after its `return jsonify(...)` line, before `if __name__ == "__main__":`):

```python
@app.route("/api/mastery", methods=["POST"])
def mastery():
    data = request.get_json()
    jp = data["jp"]
    sb.table("word_progress").update({"mastered": True}).eq("jp", jp).execute()
    return jsonify({"ok": True})
```

- [ ] **Step 2: Verify with the dev server**

```bash
python app.py &
sleep 2
curl -s -X POST http://localhost:5001/api/review -H "Content-Type: application/json" \
  -d '{"jp": "テスト斩词", "score": 3}' > /dev/null
curl -s -X POST http://localhost:5001/api/mastery -H "Content-Type: application/json" \
  -d '{"jp": "テスト斩词"}'
```

Expected output: `{"ok":true}`

```bash
kill %1
```

```sql
-- Run in Supabase SQL Editor to confirm and clean up
SELECT jp, mastered FROM word_progress WHERE jp = 'テスト斩词';  -- expect mastered = true
DELETE FROM word_progress WHERE jp = 'テスト斩词';
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Add /api/mastery endpoint to mark a word as permanently mastered"
```

(The actual filtering of `mastered = true` words out of the review queue happens in Task 6, when `/api/next` is rewritten — `get_progress` from Task 2 already fetches the `mastered` column so it's available there.)

---

### Task 4: Replace `daily_limit` with separate new/review limits

**Files:**
- Modify: `app.py:14-16` (`get_daily_limit`)
- Modify: `app.py:45-52` (`settings`)

- [ ] **Step 1: Replace `get_daily_limit` with two limit getters**

Find:

```python
def get_daily_limit():
    res = sb.table("app_settings").select("value").eq("key", "daily_limit").execute()
    return int(res.data[0]["value"]) if res.data else 20
```

Replace with:

```python
def get_new_words_limit():
    res = sb.table("app_settings").select("value").eq("key", "new_words_limit").execute()
    return int(res.data[0]["value"]) if res.data else 10


def get_review_words_limit():
    res = sb.table("app_settings").select("value").eq("key", "review_words_limit").execute()
    return int(res.data[0]["value"]) if res.data else 20
```

- [ ] **Step 2: Update the `/api/settings` route**

Find:

```python
@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "GET":
        return jsonify({"daily_limit": get_daily_limit()})
    data = request.get_json()
    new_limit = max(1, int(data["daily_limit"]))
    sb.table("app_settings").upsert({"key": "daily_limit", "value": str(new_limit)}).execute()
    return jsonify({"ok": True, "daily_limit": new_limit})
```

Replace with:

```python
@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "GET":
        return jsonify({
            "new_words_limit": get_new_words_limit(),
            "review_words_limit": get_review_words_limit(),
        })
    data = request.get_json()
    new_words_limit = max(0, int(data["new_words_limit"]))
    review_words_limit = max(0, int(data["review_words_limit"]))
    sb.table("app_settings").upsert({"key": "new_words_limit", "value": str(new_words_limit)}).execute()
    sb.table("app_settings").upsert({"key": "review_words_limit", "value": str(review_words_limit)}).execute()
    return jsonify({
        "ok": True,
        "new_words_limit": new_words_limit,
        "review_words_limit": review_words_limit,
    })
```

- [ ] **Step 3: Verify with the dev server**

```bash
python app.py &
sleep 2
curl -s http://localhost:5001/api/settings
```

Expected (first run, before any POST): `{"new_words_limit":10,"review_words_limit":20}`

```bash
curl -s -X POST http://localhost:5001/api/settings -H "Content-Type: application/json" \
  -d '{"new_words_limit": 15, "review_words_limit": 25}'
curl -s http://localhost:5001/api/settings
```

Expected: both calls return `{"new_words_limit":15,"review_words_limit":25,...}`

```bash
# reset back to defaults so later tasks' verification isn't skewed
curl -s -X POST http://localhost:5001/api/settings -H "Content-Type: application/json" \
  -d '{"new_words_limit": 10, "review_words_limit": 20}' > /dev/null
kill %1
```

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "Replace single daily_limit setting with new_words_limit/review_words_limit"
```

---

### Task 5: Today's new/review counts

**Files:**
- Modify: `app.py:24-27` (`get_today_count`)

- [ ] **Step 1: Replace `get_today_count` with two count helpers**

Find:

```python
def get_today_count():
    today = date.today().isoformat()
    res = sb.table("word_progress").select("jp").eq("last_reviewed", today).execute()
    return len(res.data)
```

Replace with:

```python
def get_today_new_count():
    today = date.today().isoformat()
    res = sb.table("word_progress").select("jp").eq("last_reviewed", today).eq("review_count", 1).execute()
    return len(res.data)


def get_today_review_count():
    today = date.today().isoformat()
    res = sb.table("word_progress").select("jp").eq("last_reviewed", today).gt("review_count", 1).execute()
    return len(res.data)
```

This relies on the fact (established in Task 2) that `review_count` is incremented on every review: a row touched today with `review_count == 1` was learned as new today; `review_count > 1` means it had already been studied before today, so today's touch was a review.

- [ ] **Step 2: Verify with the dev server**

```bash
python app.py &
sleep 2
curl -s -X POST http://localhost:5001/api/review -H "Content-Type: application/json" \
  -d '{"jp": "テスト新词", "score": 3}' > /dev/null
python3 -c "
import os
from supabase import create_client
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
from datetime import date
today = date.today().isoformat()
new_rows = sb.table('word_progress').select('jp').eq('last_reviewed', today).eq('review_count', 1).execute()
print('new today:', [r['jp'] for r in new_rows.data])
"
kill %1
```

Expected: `new today: ['テスト新词', ...]` (includes the row just created; list may contain other words from real same-day usage, that's fine).

```sql
-- Run in Supabase SQL Editor to clean up
DELETE FROM word_progress WHERE jp = 'テスト新词';
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Compute today's new-word and review-word counts from review_count"
```

---

### Task 6: Rewrite `/api/next` — split pools, priority, extended, mastered filter

**Files:**
- Modify: `app.py:55-93` (`get_next`)

- [ ] **Step 1: Replace the whole `get_next` function**

Find:

```python
@app.route("/api/next")
def get_next():
    words = parse_words()
    progress = get_progress()
    daily_limit = get_daily_limit()
    today_count = get_today_count()
    today = date.today().isoformat()

    remaining = daily_limit - today_count
    if remaining <= 0:
        return jsonify({"done": True, "reason": "daily_limit",
                        "today_count": today_count, "daily_limit": daily_limit})

    due = []
    for w in words:
        p = progress.get(w["jp"])
        if p is None:
            due.append({**w, "level": 0})
        elif (p["last_reviewed"] is None or p["last_reviewed"] < today) and is_due(p["next_review"]):
            due.append({**w, "level": p["level"]})

    due.sort(key=lambda x: x["level"])

    if not due:
        return jsonify({"done": True, "reason": "all_done",
                        "today_count": today_count, "daily_limit": daily_limit})

    word = due[0]
    return jsonify({
        "done": False,
        "jp": word["jp"],
        "kana": word["kana"],
        "zh": word["zh"],
        "section": word["section"],
        "level": word["level"],
        "today_count": today_count,
        "daily_limit": daily_limit,
        "remaining": remaining,
    })
```

Replace with:

```python
@app.route("/api/next")
def get_next():
    words = parse_words()
    progress = get_progress()
    new_words_limit = get_new_words_limit()
    review_words_limit = get_review_words_limit()
    today_new_count = get_today_new_count()
    today_review_count = get_today_review_count()
    today = date.today().isoformat()
    extended = request.args.get("extended") == "1"

    review_due = []
    new_words = []
    for w in words:
        p = progress.get(w["jp"])
        if p is None:
            new_words.append({**w, "level": 0})
        elif p.get("mastered"):
            continue
        elif (p["last_reviewed"] is None or p["last_reviewed"] < today) and is_due(p["next_review"]):
            review_due.append({**w, "level": p["level"]})

    review_due.sort(key=lambda x: x["level"])

    remaining_review = review_words_limit - today_review_count
    remaining_new = new_words_limit - today_new_count

    def build_response(word):
        return jsonify({
            "done": False,
            "jp": word["jp"],
            "kana": word["kana"],
            "zh": word["zh"],
            "section": word["section"],
            "level": word["level"],
            "today_new_count": today_new_count,
            "new_words_limit": new_words_limit,
            "today_review_count": today_review_count,
            "review_words_limit": review_words_limit,
        })

    if (extended or remaining_review > 0) and review_due:
        return build_response(review_due[0])
    if (extended or remaining_new > 0) and new_words:
        return build_response(new_words[0])

    reason = "all_done" if extended or remaining_review > 0 or remaining_new > 0 else "daily_limit"
    return jsonify({
        "done": True,
        "reason": reason,
        "today_new_count": today_new_count,
        "new_words_limit": new_words_limit,
        "today_review_count": today_review_count,
        "review_words_limit": review_words_limit,
    })
```

- [ ] **Step 2: Verify review-before-new priority and mastered filtering**

```bash
python app.py &
sleep 2
# Pick a real word from word.md that has no progress row yet (guaranteed "new"):
curl -s http://localhost:5001/api/next
```

Expected: `"done":false`, and the returned `jp` is a word with `"level":0` that has never been reviewed — since with default settings (0 words studied today) `remaining_review = 20 > 0` but `review_due` is empty (nothing due yet on a fresh DB), so it falls through to the new-word pool.

```bash
# Exhaust review limit, confirm mastered words never reappear:
curl -s -X POST http://localhost:5001/api/review -H "Content-Type: application/json" \
  -d '{"jp": "テスト遮蔽词", "score": 3}' > /dev/null
curl -s -X POST http://localhost:5001/api/mastery -H "Content-Type: application/json" \
  -d '{"jp": "テスト遮蔽词"}' > /dev/null
python3 -c "
import os
from supabase import create_client
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
sb.table('word_progress').update({'next_review': '2020-01-01'}).eq('jp', 'テスト遮蔽词').execute()
print('backdated next_review so it would be due if not filtered')
"
curl -s http://localhost:5001/api/next | python3 -c "import sys,json; d=json.load(sys.stdin); print('leaked mastered word!' if d.get('jp') == 'テスト遮蔽词' else 'OK: mastered word not returned')"
kill %1
```

Expected: `OK: mastered word not returned`

```sql
-- Run in Supabase SQL Editor to clean up
DELETE FROM word_progress WHERE jp = 'テスト遮蔽词';
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Rewrite /api/next: split new/review pools, review-first priority, extended flag, mastered filter"
```

---

### Task 7: `/api/review_today` endpoint

**Files:**
- Modify: `app.py` (add new route)

- [ ] **Step 1: Add the endpoint**

Insert this route after `mastery()` (before `if __name__ == "__main__":`):

```python
@app.route("/api/review_today")
def review_today():
    today = date.today().isoformat()
    res = sb.table("word_progress").select("jp").eq("last_reviewed", today).execute()
    studied_jp = {row["jp"] for row in res.data}
    words = parse_words()
    today_words = [w for w in words if w["jp"] in studied_jp]
    return jsonify(today_words)
```

- [ ] **Step 2: Verify with the dev server**

```bash
python app.py &
sleep 2
curl -s -X POST http://localhost:5001/api/review -H "Content-Type: application/json" \
  -d '{"jp": "青二才", "score": 3}' > /dev/null
curl -s http://localhost:5001/api/review_today
kill %1
```

Expected: a JSON array containing an object with `"jp":"青二才","kana":"あおにさい","zh":"乳臭未干的年轻人，毛头小子，新手"` (this word exists in `word.md` per the earlier `grep`), plus any other words reviewed today during earlier verification steps.

```sql
-- Run in Supabase SQL Editor to clean up the test row so it doesn't pollute your real progress
DELETE FROM word_progress WHERE jp = '青二才';
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Add /api/review_today for the free-review (斩不影响SRS) mode"
```

---

### Task 8: Frontend — two-limit settings modal and stats bar

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Replace the settings modal's single input with two inputs**

Find:

```html
      <label>
        每天背单词数量
        <input id="limit-input" type="number" min="1" max="200" value="20">
      </label>
```

Replace with:

```html
      <label>
        每天学习新词数量
        <input id="new-limit-input" type="number" min="0" max="200" value="10">
      </label>
      <label>
        每天复习旧词数量
        <input id="review-limit-input" type="number" min="0" max="200" value="20">
      </label>
```

- [ ] **Step 2: Update `openSettings` and `saveSettings`**

Find:

```javascript
    async function openSettings() {
      const res = await fetch("/api/settings");
      const data = await res.json();
      document.getElementById("limit-input").value = data.daily_limit;
      document.getElementById("modal-overlay").classList.add("open");
    }

    function closeSettings() {
      document.getElementById("modal-overlay").classList.remove("open");
    }

    async function saveSettings() {
      const limit = parseInt(document.getElementById("limit-input").value);
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ daily_limit: limit }),
      });
      closeSettings();
    }
```

Replace with:

```javascript
    async function openSettings() {
      const res = await fetch("/api/settings");
      const data = await res.json();
      document.getElementById("new-limit-input").value = data.new_words_limit;
      document.getElementById("review-limit-input").value = data.review_words_limit;
      document.getElementById("modal-overlay").classList.add("open");
    }

    function closeSettings() {
      document.getElementById("modal-overlay").classList.remove("open");
    }

    async function saveSettings() {
      const newWordsLimit = parseInt(document.getElementById("new-limit-input").value);
      const reviewWordsLimit = parseInt(document.getElementById("review-limit-input").value);
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_words_limit: newWordsLimit, review_words_limit: reviewWordsLimit }),
      });
      closeSettings();
    }
```

- [ ] **Step 3: Update the stats line in `loadNext` and the done-message text**

Find:

```javascript
      if (data.done) {
        const msg = data.reason === "daily_limit"
          ? `今天的 ${data.daily_limit} 个单词已完成！<br><span style="font-size:0.85rem;color:#aaa">明天继续 💪</span>`
          : `所有到期单词复习完了！<br><span style="font-size:0.85rem;color:#aaa">今日 ${data.today_count}/${data.daily_limit} 个</span>`;

        document.getElementById("card").innerHTML =
          `<div style="text-align:center;color:#555;font-size:1.1rem;line-height:2">${msg}</div>`;
        document.getElementById("flip-btn").style.display = "none";
        document.getElementById("stats").textContent = "";
        return;
      }
```

Replace with:

```javascript
      if (data.done) {
        const progressLine = `新词 ${data.today_new_count}/${data.new_words_limit} · 复习 ${data.today_review_count}/${data.review_words_limit}`;
        const msg = data.reason === "daily_limit"
          ? `今天的额度已用完！<br><span style="font-size:0.85rem;color:#aaa">${progressLine}</span>`
          : `所有到期单词复习完了！<br><span style="font-size:0.85rem;color:#aaa">${progressLine}</span>`;

        document.getElementById("card").innerHTML =
          `<div style="text-align:center;color:#555;font-size:1.1rem;line-height:2">${msg}</div>`;
        document.getElementById("flip-btn").style.display = "none";
        document.getElementById("stats").textContent = "";
        return;
      }
```

(The `done-actions` buttons for this screen are added in Task 10 — this step only fixes the text so it no longer references the removed `daily_limit`/`today_count` fields.)

- [ ] **Step 4: Update the stats line for the normal (non-done) case**

Find:

```javascript
      document.getElementById("stats").textContent =
        `今日 ${data.today_count + 1}/${data.daily_limit}`;
```

Replace with:

```javascript
      document.getElementById("stats").textContent =
        `新词 ${data.today_new_count}/${data.new_words_limit} · 复习 ${data.today_review_count}/${data.review_words_limit}`;
```

- [ ] **Step 5: Manually verify in the browser**

```bash
python app.py &
sleep 2
open http://localhost:5001
```

Click the ⚙ settings icon — confirm two number inputs appear ("每天学习新词数量", "每天复习旧词数量") pre-filled with the current values. Change both, save, reopen settings, confirm the new values persisted. Confirm the stats line at the top now reads like `新词 0/10 · 复习 0/20`.

```bash
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add templates/index.html
git commit -m "Frontend: split settings into new/review limits, update stats display"
```

---

### Task 9: Frontend — mastery confirmation

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Update `score()` to prompt on `reached_max_level`**

Find:

```javascript
    async function score(s) {
      await fetch("/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jp: current.jp, score: s }),
      });
      loadNext();
    }
```

Replace with:

```javascript
    async function score(s) {
      const res = await fetch("/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jp: current.jp, score: s }),
      });
      const data = await res.json();

      if (data.reached_max_level) {
        const wantsMastery = confirm(`「${current.jp}」已经记得很牢固了，要斩掉吗？`);
        if (wantsMastery) {
          await fetch("/api/mastery", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jp: current.jp }),
          });
        }
      }

      loadNext();
    }
```

This uses the browser's native `confirm()` dialog rather than a custom modal — the project has no existing confirm-dialog pattern to extend, and a native dialog is the minimal correct implementation for a simple yes/no prompt.

- [ ] **Step 2: Manually verify in the browser**

```bash
python app.py &
sleep 2
open http://localhost:5001
```

Pick any word, flip it, and click "记住了" (记住了 button) five times in a row (reloading between each — the app will keep serving the same word once it's the only one due). On the 5th time, a browser confirm dialog should pop up: `「<word>」已经记得很牢固了，要斩掉吗？`. Click OK — confirm the word never appears again by refreshing repeatedly. Repeat with a different word and click Cancel — confirm the word keeps appearing in the normal review cycle.

```bash
kill %1
```

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "Frontend: prompt to mark a word as mastered when it reaches level 5"
```

---

### Task 10: Frontend — done screen with continue-learning action

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Add the `done-actions` container to the HTML**

Find:

```html
  <button id="flip-btn" onclick="flip()">翻牌</button>
  <div id="score-btns">
    <button class="score-btn s1" onclick="score(1)">不会</button>
    <button class="score-btn s2" onclick="score(2)">模糊</button>
    <button class="score-btn s3" onclick="score(3)">记住了</button>
  </div>
```

Replace with:

```html
  <button id="flip-btn" onclick="flip()">翻牌</button>
  <div id="score-btns">
    <button class="score-btn s1" onclick="score(1)">不会</button>
    <button class="score-btn s2" onclick="score(2)">模糊</button>
    <button class="score-btn s3" onclick="score(3)">记住了</button>
  </div>
  <div id="done-actions">
    <button class="done-action-btn" onclick="continueLearning()">继续学习</button>
    <button class="done-action-btn" onclick="startFreeReview()">复习</button>
  </div>
```

(`startFreeReview` is defined in Task 11 — this button will exist but do nothing until then. That's fine as an intermediate state since this task's own verification only exercises "继续学习".)

- [ ] **Step 2: Add CSS for `done-actions`**

Find:

```css
    #score-btns {
      display: none;
      gap: 12px;
      width: 100%;
      max-width: 400px;
      margin-top: 12px;
    }
```

Replace with:

```css
    #score-btns {
      display: none;
      gap: 12px;
      width: 100%;
      max-width: 400px;
      margin-top: 12px;
    }

    #done-actions {
      display: none;
      gap: 12px;
      width: 100%;
      max-width: 400px;
      margin-top: 12px;
    }

    .done-action-btn {
      flex: 1;
      padding: 14px 0;
      font-size: 0.95rem;
      border: none;
      border-radius: 12px;
      cursor: pointer;
      font-weight: 600;
      background: #eee;
      color: #555;
    }
```

- [ ] **Step 3: Show/hide `done-actions` at the right points in `loadNext`, and add `continueLearning`**

Find:

```javascript
      document.getElementById("score-btns").style.display = "none";
      document.getElementById("answer").style.display = "none";
      document.getElementById("flip-btn").style.display = "block";

      if (data.done) {
```

Replace with:

```javascript
      document.getElementById("score-btns").style.display = "none";
      document.getElementById("answer").style.display = "none";
      document.getElementById("flip-btn").style.display = "block";
      document.getElementById("done-actions").style.display = "none";

      if (data.done) {
```

Then find the end of the `done` branch:

```javascript
        document.getElementById("card").innerHTML =
          `<div style="text-align:center;color:#555;font-size:1.1rem;line-height:2">${msg}</div>`;
        document.getElementById("flip-btn").style.display = "none";
        document.getElementById("stats").textContent = "";
        return;
      }
```

Replace with:

```javascript
        document.getElementById("card").innerHTML =
          `<div style="text-align:center;color:#555;font-size:1.1rem;line-height:2">${msg}</div>`;
        document.getElementById("flip-btn").style.display = "none";
        document.getElementById("stats").textContent = "";
        document.getElementById("done-actions").style.display = "flex";
        return;
      }
```

Then add `continueLearning` right before the final `loadNext();` call at the bottom of the `<script>` block. Find:

```javascript
    loadNext();
  </script>
```

Replace with:

```javascript
    function continueLearning() {
      const today = new Date().toISOString().slice(0, 10);
      localStorage.setItem("tango_extended_date", today);
      loadNext();
    }

    loadNext();
  </script>
```

- [ ] **Step 4: Make `loadNext` send the `extended` flag when today's local flag is set**

Find:

```javascript
    async function loadNext() {
      const res = await fetch("/api/next");
      const data = await res.json();
```

Replace with:

```javascript
    async function loadNext() {
      const today = new Date().toISOString().slice(0, 10);
      const extended = localStorage.getItem("tango_extended_date") === today;
      const res = await fetch("/api/next" + (extended ? "?extended=1" : ""));
      const data = await res.json();
```

- [ ] **Step 5: Manually verify in the browser**

```bash
python app.py &
sleep 2
```

In the settings modal, set both limits to `0` and save. Refresh — the done screen should appear immediately with both "继续学习" and "复习" buttons visible (message should say "今天的额度已用完！"). Open the browser console and run `localStorage.getItem("tango_extended_date")` — should be `null`. Click "继续学习" — confirm a due word now loads (since the limit is bypassed). Check the console again: `localStorage.getItem("tango_extended_date")` should now equal today's date (`YYYY-MM-DD`). Set the limits back to `10`/`20` in settings afterward.

```bash
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add templates/index.html
git commit -m "Frontend: add done-screen continue-learning action backed by extended flag"
```

---

### Task 11: Frontend — free review mode

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Add free-review state variables**

Find:

```javascript
    let current = null;
```

Replace with:

```javascript
    let current = null;
    let isFreeReview = false;
    let freeReviewList = [];
    let freeReviewIndex = 0;
```

- [ ] **Step 2: Add `startFreeReview` and `showFreeReviewCard`**

Find:

```javascript
    function continueLearning() {
```

Replace with:

```javascript
    async function startFreeReview() {
      const res = await fetch("/api/review_today");
      freeReviewList = await res.json();
      freeReviewIndex = 0;
      isFreeReview = true;
      document.getElementById("done-actions").style.display = "none";
      showFreeReviewCard();
    }

    function showFreeReviewCard() {
      document.getElementById("score-btns").style.display = "none";
      document.getElementById("answer").style.display = "none";
      document.getElementById("flip-btn").style.display = "block";

      if (freeReviewIndex >= freeReviewList.length) {
        isFreeReview = false;
        document.getElementById("card").innerHTML =
          `<div style="text-align:center;color:#555;font-size:1.1rem;line-height:2">复习完了！</div>`;
        document.getElementById("flip-btn").style.display = "none";
        document.getElementById("done-actions").style.display = "flex";
        return;
      }

      const word = freeReviewList[freeReviewIndex];
      current = word;
      document.getElementById("jp").textContent = word.jp;
      document.getElementById("kana").textContent = word.kana || "";
      document.getElementById("answer").textContent = word.zh;
      document.getElementById("section-tag").textContent = word.section;
      document.getElementById("level-bar").innerHTML = "";
      document.getElementById("stats").textContent =
        `自由复习 ${freeReviewIndex + 1}/${freeReviewList.length}`;
    }

    function continueLearning() {
```

- [ ] **Step 3: Route `score()` through the free-review branch when active**

Find:

```javascript
    async function score(s) {
      const res = await fetch("/api/review", {
```

Replace with:

```javascript
    async function score(s) {
      if (isFreeReview) {
        freeReviewIndex++;
        showFreeReviewCard();
        return;
      }

      const res = await fetch("/api/review", {
```

- [ ] **Step 4: Manually verify in the browser**

```bash
python app.py &
sleep 2
```

Study at least one word normally (flip, click any score button) so there's something in today's history. Trigger the done screen (set both limits to a low number in settings, e.g. `1`/`1`, if needed to reach it quickly). Click "复习" — confirm it shows the word(s) studied today, flip works, and clicking a score button (不会/模糊/记住了) just advances to the next card without any network call to `/api/review` (check the Network tab — no `POST /api/review` should fire while in this mode). After the last card, confirm it shows "复习完了！" and both "继续学习"/"复习" buttons reappear. Reset your settings limits back to `10`/`20` afterward.

```bash
kill %1
```

- [ ] **Step 5: Commit**

```bash
git add templates/index.html
git commit -m "Frontend: add free-review mode that replays today's studied words without touching SRS state"
```

---

### Task 12: Update documentation

**Files:**
- Modify: `README.md`
- Modify: `DEVLOG.md`

- [ ] **Step 1: Update the usage section**

Find:

```markdown
## 使用说明

- 打开网页，点击**翻牌**查看答案
- 根据掌握程度点击「不会 / 模糊 / 记住了」
- 点击右上角 ⚙ 可设置每日复习量
- 熟悉度越高（橙点越多），复习间隔越长（最长 30 天）
```

Replace with:

```markdown
## 使用说明

- 打开网页，点击**翻牌**查看答案
- 根据掌握程度点击「不会 / 模糊 / 记住了」
- 点击右上角 ⚙ 可分别设置每天学习的新词数量、复习的旧词数量
- 熟悉度越高（橙点越多），复习间隔越长（最长 30 天）
- 一个词连续记熟到熟悉度满格（5 个橙点）时，会问你要不要把它「斩」掉——斩掉之后这个词永远不会再出现
- 今天的额度用完后，完成界面会同时提供「继续学习」（取消今天的上限，继续学到期词）和「复习」（自由回顾今天学过的词，不影响进度）两个按钮
```

- [ ] **Step 2: Update the feature bullet list**

Find:

```markdown
- **每日上限可调** — 页面内直接设置每天要背多少，不给自己太大压力
```

Replace with:

```markdown
- **新词/复习分别可调** — 页面内直接设置每天学几个新词、复习几个旧词，不给自己太大压力
- **斩词** — 记得足够牢固的词可以永久退场，不再占用复习时间
```

- [ ] **Step 3: Update the deployment steps to mention the new schema.sql**

Find:

```markdown
2. 进入 **SQL Editor**，执行 `schema.sql` 里的内容（建表）
```

Replace with:

```markdown
2. 进入 **SQL Editor**，执行 `schema.sql` 里的内容（建表）。如果你之前已经部署过旧版本，只需要执行 `schema.sql` 里"增量迁移"那一段
```

- [ ] **Step 4: Add a DEVLOG entry**

Find:

```markdown
# DEVLOG

## v1.0 — 2026-06-29
```

Replace with:

```markdown
# DEVLOG

## v2.0 — 2026-07-09

### 已完成
- 新词/复习词每日额度分开设置，复习优先于新词
- 每个词记录累计学习次数（`review_count`），用于区分"今天是新学还是复习"
- 斩词：熟悉度满格时可选择永久退场，不再出现
- 继续学习：今日额度用完后可取消限制，继续学完当天已到期的词
- 自由复习：完成后可回顾今天学过的词，不影响 SRS 进度

---

## v1.0 — 2026-06-29
```

- [ ] **Step 5: Commit**

```bash
git add README.md DEVLOG.md
git commit -m "Update docs for new-word/review split, mastery, continue-learning, and free-review"
```

---

## Self-Review Notes

- **Spec coverage:** every section of both design docs maps to a task above — schema (Task 1), review_count (Task 2), mastery backend+frontend (Tasks 3, 9), settings split (Task 4), today-count helpers (Task 5), `/api/next` rewrite incl. extended+mastered filter (Task 6), `/api/review_today` (Task 7), settings/stats UI (Task 8), continue-learning UI+localStorage (Task 10), free-review UI (Task 11), docs (Task 12).
- **Type/name consistency check:** `save_progress(jp, level, next_review_date, review_count)` signature from Task 2 is used identically in Task 2's own `review()` call — no other call site exists. `get_new_words_limit`/`get_review_words_limit` (Task 4) are the only names used everywhere they're referenced (Task 6, Task 8's settings GET). `today_new_count`/`today_review_count`/`new_words_limit`/`review_words_limit` field names are identical across `/api/next`'s two response shapes (Task 6) and the frontend's two consumption points (Task 8's `loadNext`). `done-actions` id and `.done-action-btn` class are consistent between Task 10 (creation) and Task 11 (reuse in `showFreeReviewCard`).
- **No placeholders:** all steps contain literal code, exact `find`/`replace` blocks, and runnable commands with stated expected output.
