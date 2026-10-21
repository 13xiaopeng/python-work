"""M5-1：SQLite 存储层。

并发写入保证思路：
  * 每次操作使用独立连接，写操作显式 `BEGIN IMMEDIATE` 事务，由 SQLite 串行化写入；
  * 打开 WAL 模式提升读写并发（读不阻塞写）；
  * 设置 `busy_timeout=5000`，遇到锁等待而不是立刻报 "database is locked"。
因此并发写入不会出现部分写入或脏数据。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from .models import RecordCreate, RecordOut, RecordType

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS records (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    amount   REAL    NOT NULL,
    type     TEXT    NOT NULL,
    category TEXT    NOT NULL,
    date     TEXT    NOT NULL
);
"""

_CREATE_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_records_date ON records(date);"


class LedgerStorage:
    """记账数据的内存无关持久化层（SQLite 文件）。"""

    def __init__(self, db_path: str | Path = "ledger.db") -> None:
        self.db_path = str(db_path)
        self._init_db()

    # ---------- 连接管理 ----------

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(CREATE_TABLE_SQL)
            conn.execute(_CREATE_INDEX_SQL)

    # ---------- 写 ----------

    def insert(self, record: RecordCreate) -> RecordOut:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    "INSERT INTO records (amount, type, category, date) VALUES (?, ?, ?, ?)",
                    (record.amount, record.type.value, record.category, record.date.isoformat()),
                )
                new_id = cursor.lastrowid
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return RecordOut(id=new_id, **record.model_dump())

    def clear(self) -> None:
        """仅测试使用：清空表。"""
        with self._connect() as conn:
            conn.execute("DELETE FROM records")

    # ---------- 读 ----------

    def query(
        self,
        *,
        type_: RecordType | None = None,
        category: str | None = None,
        start: date | None = None,
        end: date | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[RecordOut], int]:
        where, params = _build_filters(type_, category, start, end)
        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM records {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM records {where} ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return [_row_to_record(row) for row in rows], int(total)

    def summary(
        self, *, start: date | None = None, end: date | None = None
    ) -> tuple[float, float]:
        where, params = _build_filters(None, None, start, end)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT
                    COALESCE(SUM(CASE WHEN type = ? THEN amount ELSE 0 END), 0) AS income,
                    COALESCE(SUM(CASE WHEN type = ? THEN amount ELSE 0 END), 0) AS expense
                FROM records {where}
                """,
                (RecordType.INCOME.value, RecordType.EXPENSE.value, *params),
            ).fetchone()
        return round(float(row["income"]), 2), round(float(row["expense"]), 2)


# ---------- 内部工具 ----------

def _build_filters(
    type_: RecordType | None,
    category: str | None,
    start: date | None,
    end: date | None,
) -> tuple[str, list]:
    conditions: list[str] = []
    params: list = []
    if type_ is not None:
        conditions.append("type = ?")
        params.append(type_.value)
    if category:
        conditions.append("category = ?")
        params.append(category)
    if start is not None:
        conditions.append("date >= ?")
        params.append(start.isoformat())
    if end is not None:
        conditions.append("date <= ?")
        params.append(end.isoformat())
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where, params


def _row_to_record(row: sqlite3.Row) -> RecordOut:
    return RecordOut(
        id=row["id"],
        amount=row["amount"],
        type=RecordType(row["type"]),
        category=row["category"],
        date=date.fromisoformat(row["date"]),
    )
