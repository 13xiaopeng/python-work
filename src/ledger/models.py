"""M5-1：记账接口的数据模型（pydantic v2）。"""
from __future__ import annotations

import datetime as dt
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RecordType(str, Enum):
    """流水类型，只允许 收入 / 支出。"""

    INCOME = "收入"
    EXPENSE = "支出"


class RecordCreate(BaseModel):
    """POST /records 的请求体。"""

    model_config = ConfigDict(extra="forbid")

    amount: float = Field(..., gt=0, description="金额，必须大于 0")
    type: RecordType = Field(..., description="类型：收入 / 支出")
    category: str = Field(..., min_length=1, max_length=50, description="分类")
    date: dt.date = Field(..., description="日期，格式 YYYY-MM-DD")

    @field_validator("category")
    @classmethod
    def _strip_category(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("分类不能为空")
        return value


class RecordOut(RecordCreate):
    """返回给调用方的流水。"""

    id: int


class RecordPage(BaseModel):
    """GET /records 的分页返回结构。"""

    total: int
    page: int
    page_size: int
    items: list[RecordOut]


class SummaryOut(BaseModel):
    """GET /summary 的返回结构。"""

    start: dt.date | None = None
    end: dt.date | None = None
    income_total: float
    expense_total: float
    balance: float
