import sqlite3
from datetime import datetime, timedelta

DB_FILE = "assistant.db"


def get_connection():
    """Подключение к базе данных."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # чтобы обращаться к колонкам по имени
    return conn


def init_db():
    """Создаёт таблицы, если их ещё нет."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
            CREATE TABLE IF NOT EXISTS usage (
                user_id INTEGER,
                date TEXT,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
        """)

    # Пользователи бота
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TEXT,
            last_seen TEXT
        )
    """)

    # Заметки
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            created_at TEXT
        )
    """)

    # Напоминания
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            remind_at TEXT,
            is_sent INTEGER DEFAULT 0
        )
    """)

    # Привычки
    cur.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            streak INTEGER DEFAULT 0,
            last_check TEXT,
            created_at TEXT
        )
    """)
    # Подписки
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            expires_at TEXT,
            plan TEXT DEFAULT 'free'
        )
    """)

    conn.commit()

    conn.commit()
    conn.close()


def add_user(user_id, username, first_name):
    """Регистрирует пользователя или обновляет данные."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()

    cur.execute("""
        INSERT INTO users (user_id, username, first_name, joined_at, last_seen)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_seen = excluded.last_seen
    """, (user_id, username, first_name, now, now))

    conn.commit()
    conn.close()


# ===== ЗАМЕТКИ =====

def add_note(user_id, text):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO notes (user_id, text, created_at) VALUES (?, ?, ?)",
        (user_id, text, datetime.now().isoformat())
    )
    note_id = cur.lastrowid
    conn.commit()
    conn.close()
    return note_id


def get_notes(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM notes WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_note(user_id, note_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted > 0


# ===== НАПОМИНАНИЯ =====

def add_reminder(user_id, text, remind_at):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reminders (user_id, text, remind_at) VALUES (?, ?, ?)",
        (user_id, text, remind_at)
    )
    conn.commit()
    conn.close()


def get_pending_reminders():
    """Возвращает напоминания, которые пора отправить."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute(
        "SELECT * FROM reminders WHERE is_sent = 0 AND remind_at <= ?",
        (now,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def mark_reminder_sent(reminder_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE reminders SET is_sent = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


# ===== ПРИВЫЧКИ =====

def add_habit(user_id, name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO habits (user_id, name, created_at) VALUES (?, ?, ?)",
        (user_id, name, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_habits(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM habits WHERE user_id = ?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

# ===== СТАТИСТИКА =====

def get_stats(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM notes WHERE user_id = ?", (user_id,))
    notes_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM habits WHERE user_id = ?", (user_id,))
    habits_count = cur.fetchone()[0]
    conn.close()
    return {"notes": notes_count, "habits": habits_count}

# ===== ЛИМИТЫ И ПОДПИСКИ =====

FREE_LIMIT = 5


def get_usage_today(user_id):
    """Сколько запросов сделал юзер сегодня."""
    conn = get_connection()
    cur = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute(
        "SELECT count FROM usage WHERE user_id = ? AND date = ?",
        (user_id, today)
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def increment_usage(user_id):
    """Увеличивает счётчик запросов на 1."""
    conn = get_connection()
    cur = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
        INSERT INTO usage (user_id, date, count) VALUES (?, ?, 1)
        ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1
    """, (user_id, today))
    conn.commit()
    conn.close()


def has_subscription(user_id):
    """Проверяет, активна ли подписка."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT expires_at FROM subscriptions WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return False
    try:
        expires = datetime.fromisoformat(row[0])
        return expires > datetime.now()
    except Exception:
        return False


def give_subscription(user_id, days=30, plan="premium"):
    """Выдаёт подписку на N дней."""
    conn = get_connection()
    cur = conn.cursor()
    expires_at = (datetime.now() + timedelta(days=days)).isoformat()
    cur.execute("""
        INSERT INTO subscriptions (user_id, expires_at, plan) VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            expires_at = excluded.expires_at,
            plan = excluded.plan
    """, (user_id, expires_at, plan))
    conn.commit()
    conn.close()

    
def add_bonus_requests(user_id, amount):
    """Начисляет бонусные запросы (уменьшает счётчик использования)."""
    conn = get_connection()
    cur = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute(
        "SELECT count FROM usage WHERE user_id = ? AND date = ?",
        (user_id, today)
    )
    row = cur.fetchone()
    current = row[0] if row else 0
    new_count = max(0, current - amount)

    cur.execute("""
        INSERT INTO usage (user_id, date, count) VALUES (?, ?, ?)
        ON CONFLICT(user_id, date) DO UPDATE SET count = excluded.count
    """, (user_id, today, new_count))

    conn.commit()
    conn.close()


