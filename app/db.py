import sqlite3
from pathlib import Path

DB_PATH = Path('data/app.db')
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with conn() as c:
        c.execute(
            '''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )'''
        )
        c.execute(
            '''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                warnings TEXT,
                result_path TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )'''
        )
        c.execute('INSERT OR IGNORE INTO users(id,name,email,password_hash) VALUES(1,?,?,?)', ('Default', 'default@local', ''))


def create_job(job_id: str, user_id: int):
    with conn() as c:
        c.execute('INSERT INTO jobs(id,user_id,status,message) VALUES(?,?,?,?)', (job_id, user_id, 'queued', 'Queued'))


def set_job_status(job_id: str, status: str, message: str = '', warnings: str = None, result_path: str = None):
    with conn() as c:
        c.execute(
            '''UPDATE jobs SET status=?, message=?, warnings=COALESCE(?,warnings),
               result_path=COALESCE(?,result_path), updated_at=CURRENT_TIMESTAMP WHERE id=?''',
            (status, message, warnings, result_path, job_id),
        )


def get_job(job_id: str):
    with conn() as c:
        return c.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()


def get_user_jobs(user_id: int, limit: int = 20):
    with conn() as c:
        return c.execute('SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?', (user_id, limit)).fetchall()
