import os
from contextlib import contextmanager
from datetime import date

import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, render_template, request

from parser import parse_words
from scheduler import next_review, is_due

app = Flask(__name__)
DATABASE_URL = os.environ["DATABASE_URL"]


@contextmanager
def db():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_daily_limit():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM app_settings WHERE key = 'daily_limit'")
            row = cur.fetchone()
            return int(row[0]) if row else 20


def get_progress():
    with db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT jp, level, next_review, last_reviewed FROM word_progress")
            return {
                row["jp"]: {
                    "level": row["level"],
                    "next_review": str(row["next_review"]),
                    "last_reviewed": str(row["last_reviewed"]) if row["last_reviewed"] else None,
                }
                for row in cur.fetchall()
            }


def get_today_count():
    today = date.today().isoformat()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM word_progress WHERE last_reviewed = %s", (today,)
            )
            return cur.fetchone()[0]


def save_progress(jp, level, next_review_date):
    today = date.today().isoformat()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO word_progress (jp, level, next_review, last_reviewed)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (jp) DO UPDATE SET
                    level = EXCLUDED.level,
                    next_review = EXCLUDED.next_review,
                    last_reviewed = EXCLUDED.last_reviewed
                """,
                (jp, level, next_review_date, today),
            )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "GET":
        return jsonify({"daily_limit": get_daily_limit()})
    data = request.get_json()
    new_limit = max(1, int(data["daily_limit"]))
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_settings (key, value) VALUES ('daily_limit', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                (str(new_limit),),
            )
    return jsonify({"ok": True, "daily_limit": new_limit})


@app.route("/api/next")
def get_next():
    words = parse_words()
    progress = get_progress()
    daily_limit = get_daily_limit()
    today_count = get_today_count()
    today = date.today().isoformat()

    remaining = daily_limit - today_count
    if remaining <= 0:
        return jsonify({
            "done": True,
            "reason": "daily_limit",
            "today_count": today_count,
            "daily_limit": daily_limit,
        })

    due = []
    for w in words:
        key = w["jp"]
        p = progress.get(key)
        if p is None:
            due.append({**w, "level": 0})
        elif (p["last_reviewed"] is None or p["last_reviewed"] < today) and is_due(p["next_review"]):
            due.append({**w, "level": p["level"]})

    due.sort(key=lambda x: x["level"])

    if not due:
        return jsonify({
            "done": True,
            "reason": "all_done",
            "today_count": today_count,
            "daily_limit": daily_limit,
        })

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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
