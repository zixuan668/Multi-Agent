from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from uuid import uuid4

from src.agents.strategy.errors import AccessDeniedError


class CampaignRepository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE IF NOT EXISTS campaigns (task_id TEXT PRIMARY KEY, owner TEXT NOT NULL, updated_at TEXT NOT NULL, body TEXT NOT NULL, submission_key TEXT NOT NULL DEFAULT '')")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(campaigns)")}
            if "submission_key" not in columns:
                connection.execute("ALTER TABLE campaigns ADD COLUMN submission_key TEXT NOT NULL DEFAULT ''")
                for task_id, body in connection.execute("SELECT task_id, body FROM campaigns").fetchall():
                    connection.execute("UPDATE campaigns SET submission_key=? WHERE task_id=?", (json.loads(body)["submission_key"], task_id))
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS campaigns_submission ON campaigns(owner, submission_key)")
            connection.execute("CREATE INDEX IF NOT EXISTS campaigns_owner ON campaigns(owner, updated_at DESC)")
            connection.execute("CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, scope TEXT NOT NULL, expires REAL NOT NULL)")

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def session(self, token=None):
        stamp = time.time()
        digest = hashlib.sha256(token.encode()).hexdigest() if isinstance(token, str) else ""
        with self.lock, self.connection() as connection:
            connection.execute("DELETE FROM sessions WHERE expires < ?", (stamp,))
            row = connection.execute("SELECT scope FROM sessions WHERE digest=?", (digest,)).fetchone()
            if row:
                return token, row[0]
            token, scope = secrets.token_urlsafe(32), f"scope-{uuid4().hex}"
            digest = hashlib.sha256(token.encode()).hexdigest()
            connection.execute("INSERT INTO sessions VALUES (?,?,?)", (digest, scope, stamp + 30 * 86400))
            return token, scope

    def scope(self, token):
        digest = hashlib.sha256(token.encode()).hexdigest() if isinstance(token, str) else ""
        with self.connection() as connection:
            row = connection.execute("SELECT scope FROM sessions WHERE digest=? AND expires>?", (digest, time.time())).fetchone()
        if not row:
            raise AccessDeniedError("请先初始化当前工作空间会话")
        return row[0]

    def insert(self, task):
        with self.lock, self.connection() as connection:
            connection.execute("INSERT INTO campaigns (task_id, owner, updated_at, body, submission_key) VALUES (?,?,?,?,?)", (task["task_id"], task["owner_scope"], task["updated_at"], json.dumps(task, ensure_ascii=False), task["submission_key"]))

    def find_submission(self, owner, submission_key):
        with self.connection() as connection:
            row = connection.execute("SELECT body FROM campaigns WHERE owner=? AND submission_key=?", (owner, submission_key)).fetchone()
        return json.loads(row[0]) if row else None

    def get(self, task_id, owner=None, *, include_deleted=False):
        with self.connection() as connection:
            row = connection.execute("SELECT owner, body FROM campaigns WHERE task_id=?", (task_id,)).fetchone()
        if row is None or (owner is not None and row[0] != owner):
            raise AccessDeniedError("任务不存在或不属于当前工作空间")
        task = json.loads(row[1])
        if task.get('deleted_at') and not include_deleted:
            raise AccessDeniedError("任务已移入回收站，请先恢复")
        return task

    def update(self, task_id, mutate):
        with self.lock, self.connection() as connection:
            row = connection.execute("SELECT body FROM campaigns WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                raise AccessDeniedError("任务不存在")
            task = json.loads(row[0])
            mutate(task)
            connection.execute("UPDATE campaigns SET updated_at=?, body=? WHERE task_id=?", (task["updated_at"], json.dumps(task, ensure_ascii=False), task_id))
            return deepcopy(task)

    def list(self, owner, *, deleted=False, limit=100):
        with self.connection() as connection:
            rows = connection.execute("SELECT body FROM campaigns WHERE owner=? AND (json_extract(body, '$.deleted_at') IS NOT NULL)=? ORDER BY updated_at DESC LIMIT ?", (owner, int(deleted), limit if limit is not None else -1)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def recover(self):
        with self.lock, self.connection() as connection:
            rows = connection.execute("SELECT task_id, body FROM campaigns").fetchall()
            for task_id, body in rows:
                task = json.loads(body)
                if task["status"] in ("pending", "running"):
                    task["status"] = "interrupted"
                    task["stage"] = "interrupted"
                    task["error"] = {"code": "INTERRUPTED", "message": "服务已重启；已保存成功阶段，点击继续即可恢复。", "retryable": True}
                    connection.execute("UPDATE campaigns SET body=? WHERE task_id=?", (json.dumps(task, ensure_ascii=False), task_id))
