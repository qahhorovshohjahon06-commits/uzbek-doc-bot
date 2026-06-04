import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "history.db")

MAX_HISTORY_PER_USER = 10
BONUS_PER_REFERRAL = 2  # bonus docs granted per successful referral


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                doc_type    TEXT NOT NULL,
                topic       TEXT NOT NULL,
                count       INTEGER NOT NULL,
                filename    TEXT NOT NULL,
                file_data   BLOB NOT NULL,
                created_at  TEXT NOT NULL,
                date        TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user ON history(user_id, id DESC)")

        # Migrate: add `date` column if the table existed before this change
        existing_h = {row[1] for row in conn.execute("PRAGMA table_info(history)").fetchall()}
        if "date" not in existing_h:
            conn.execute("ALTER TABLE history ADD COLUMN date TEXT NOT NULL DEFAULT ''")
            conn.execute("UPDATE history SET date = substr(created_at, 1, 10) WHERE date = ''")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_date ON history(user_id, date)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id     INTEGER PRIMARY KEY,
                plan        TEXT NOT NULL DEFAULT 'free',
                expires_at  TEXT,
                granted_by  INTEGER,
                granted_at  TEXT,
                bonus_docs  INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Migrate: add `bonus_docs` column if missing
        existing_s = {row[1] for row in conn.execute("PRAGMA table_info(subscriptions)").fetchall()}
        if "bonus_docs" not in existing_s:
            conn.execute("ALTER TABLE subscriptions ADD COLUMN bonus_docs INTEGER NOT NULL DEFAULT 0")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL UNIQUE,
                created_at  TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_referrer ON referrals(referrer_id)")

        conn.commit()


# ── Subscription helpers ───────────────────────────────────────────────────

def get_user_plan(user_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT plan, expires_at, bonus_docs FROM subscriptions WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if not row:
        return {"plan": "free", "expires_at": None, "active": True, "bonus_docs": 0}

    plan = row["plan"]
    expires_at = row["expires_at"]

    if plan == "premium" and expires_at:
        expired = datetime.now().strftime("%Y-%m-%d") > expires_at
        if expired:
            return {"plan": "free", "expires_at": None, "active": True, "bonus_docs": row["bonus_docs"]}

    return {"plan": plan, "expires_at": expires_at, "active": True, "bonus_docs": row["bonus_docs"]}


def set_user_plan(user_id: int, plan: str, expires_at: str | None, granted_by: int) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO subscriptions (user_id, plan, expires_at, granted_by, granted_at, bonus_docs)
            VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                plan       = excluded.plan,
                expires_at = excluded.expires_at,
                granted_by = excluded.granted_by,
                granted_at = excluded.granted_at
            """,
            (user_id, plan, expires_at, granted_by, now),
        )
        conn.commit()


def get_daily_count(user_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM history WHERE user_id = ? AND date = ?",
            (user_id, today),
        ).fetchone()
    return row["cnt"] if row else 0


# ── Referral helpers ────────────────────────────────────────────────────────

def register_referral(referrer_id: int, referred_id: int) -> bool:
    """
    Register a referral. Returns True if this is a new referral (and bonus should be granted),
    False if the referred_id was already registered or is trying to refer themselves.
    """
    if referrer_id == referred_id:
        return False

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?, ?, ?)",
                (referrer_id, referred_id, now),
            )
            # Grant bonus docs to referrer
            conn.execute(
                """
                INSERT INTO subscriptions (user_id, plan, bonus_docs)
                VALUES (?, 'free', ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    bonus_docs = bonus_docs + ?
                """,
                (referrer_id, BONUS_PER_REFERRAL, BONUS_PER_REFERRAL),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # referred_id already has a referrer (UNIQUE constraint on referred_id)
            return False


def get_referral_stats(user_id: int) -> dict:
    with get_conn() as conn:
        count_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM referrals WHERE referrer_id = ?",
            (user_id,),
        ).fetchone()
        sub_row = conn.execute(
            "SELECT bonus_docs FROM subscriptions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return {
        "referral_count": count_row["cnt"] if count_row else 0,
        "bonus_docs": sub_row["bonus_docs"] if sub_row else 0,
    }


def get_bonus_docs(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT bonus_docs FROM subscriptions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row["bonus_docs"] if row else 0


def use_bonus_doc(user_id: int) -> None:
    """Decrement bonus_docs by 1 (min 0)."""
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE subscriptions
            SET bonus_docs = MAX(0, bonus_docs - 1)
            WHERE user_id = ?
            """,
            (user_id,),
        )
        conn.commit()


# ── Document helpers ───────────────────────────────────────────────────────

def save_document(
    user_id: int,
    doc_type: str,
    topic: str,
    count: int,
    filename: str,
    file_data: bytes,
) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO history (user_id, doc_type, topic, count, filename, file_data, created_at, date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, doc_type, topic, count, filename, file_data, now, today),
        )
        new_id = cursor.lastrowid

        conn.execute(
            """
            DELETE FROM history
            WHERE user_id = ?
              AND id NOT IN (
                  SELECT id FROM history WHERE user_id = ? ORDER BY id DESC LIMIT ?
              )
            """,
            (user_id, user_id, MAX_HISTORY_PER_USER),
        )
        conn.commit()
    return new_id


def get_history(user_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, doc_type, topic, count, filename, created_at
            FROM history
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()
    return rows


def get_document(doc_id: int, user_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM history WHERE id = ? AND user_id = ?",
            (doc_id, user_id),
        ).fetchone()
    return row


def get_all_user_ids() -> list[int]:
    """Return every distinct user_id that has ever used the bot."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT user_id FROM history
            UNION
            SELECT DISTINCT user_id FROM subscriptions
            """
        ).fetchall()
    return [row[0] for row in rows]


def get_all_users_stats() -> list[sqlite3.Row]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                h.user_id,
                COUNT(*) AS total_docs,
                COALESCE(s.plan, 'free') AS plan,
                s.expires_at,
                COALESCE(s.bonus_docs, 0) AS bonus_docs
            FROM history h
            LEFT JOIN subscriptions s ON s.user_id = h.user_id
            GROUP BY h.user_id
            ORDER BY total_docs DESC
            """,
        ).fetchall()
    return rows
