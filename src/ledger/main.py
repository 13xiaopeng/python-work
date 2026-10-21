"""M5-2：FastAPI 记账服务。

接口：
    POST /records   新增一条流水
    GET  /records   按类型 / 分类 / 日期区间筛选，分页返回
    GET  /summary   返回指定日期区间内的收入合计、支出合计与结余

非法参数统一由 pydantic / FastAPI 返回 4xx + 结构化错误体（默认 422）。
"""
from __future__ import annotations

import datetime as dt
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status

from .models import RecordCreate, RecordOut, RecordPage, RecordType, SummaryOut
from .storage import LedgerStorage

DEFAULT_DB_PATH = "ledger.db"


def create_app(db_path: str | Path | None = None) -> FastAPI:
    """应用工厂：便于测试时注入临时数据库。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.storage = LedgerStorage(
            db_path or os.environ.get("LEDGER_DB", DEFAULT_DB_PATH)
        )
        yield

    app = FastAPI(title="简易记账服务", version="1.0.0", lifespan=lifespan)

    def get_storage(request: Request) -> LedgerStorage:
        return request.app.state.storage

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/records", response_model=RecordOut, status_code=status.HTTP_201_CREATED)
    def create_record(
        payload: RecordCreate, storage: LedgerStorage = Depends(get_storage)
    ) -> RecordOut:
        return storage.insert(payload)

    @app.get("/records", response_model=RecordPage)
    def list_records(
        type: RecordType | None = Query(None, description="类型：收入 / 支出"),
        category: str | None = Query(None, min_length=1, description="分类"),
        start: dt.date | None = Query(None, description="起始日期 YYYY-MM-DD"),
        end: dt.date | None = Query(None, description="结束日期 YYYY-MM-DD"),
        page: int = Query(1, ge=1, description="页码，从 1 开始"),
        page_size: int = Query(10, ge=1, le=100, description="每页条数，最大 100"),
        storage: LedgerStorage = Depends(get_storage),
    ) -> RecordPage:
        _check_date_range(start, end)
        items, total = storage.query(
            type_=type, category=category, start=start, end=end,
            page=page, page_size=page_size,
        )
        return RecordPage(total=total, page=page, page_size=page_size, items=items)

    @app.get("/summary", response_model=SummaryOut)
    def get_summary(
        start: dt.date | None = Query(None, description="起始日期 YYYY-MM-DD"),
        end: dt.date | None = Query(None, description="结束日期 YYYY-MM-DD"),
        storage: LedgerStorage = Depends(get_storage),
    ) -> SummaryOut:
        _check_date_range(start, end)
        income, expense = storage.summary(start=start, end=end)
        return SummaryOut(
            start=start,
            end=end,
            income_total=income,
            expense_total=expense,
            balance=round(income - expense, 2),
        )

    return app


def _check_date_range(start: dt.date | None, end: dt.date | None) -> None:
    """日期区间起止颠倒属于非法参数，返回 422 结构化错误。"""
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=422,  # Unprocessable Content
            detail=[
                {
                    "loc": ["query", "start"],
                    "msg": "开始日期不能晚于结束日期",
                    "type": "value_error.date_range",
                }
            ],
        )


# uvicorn src.ledger.main:app
app = create_app()
