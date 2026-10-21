"""M5-1 单测：存储层（写入 / 筛选 / 分页 / 汇总 / 并发）。"""
from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.ledger.models import RecordCreate, RecordType
from src.ledger.storage import LedgerStorage


@pytest.fixture()
def storage(tmp_path) -> LedgerStorage:
    return LedgerStorage(tmp_path / "ledger.db")


def make_record(amount: float, type_: RecordType, category: str, date_: dt.date) -> RecordCreate:
    return RecordCreate(amount=amount, type=type_, category=category, date=date_)


@pytest.fixture()
def seeded(storage) -> LedgerStorage:
    rows = [
        (100.0, RecordType.INCOME, "工资", dt.date(2024, 1, 10)),
        (50.0, RecordType.EXPENSE, "餐饮", dt.date(2024, 1, 15)),
        (200.0, RecordType.INCOME, "工资", dt.date(2024, 2, 10)),
        (30.0, RecordType.EXPENSE, "交通", dt.date(2024, 2, 20)),
        (20.0, RecordType.EXPENSE, "餐饮", dt.date(2024, 3, 1)),
    ]
    for amount, type_, category, date_ in rows:
        storage.insert(make_record(amount, type_, category, date_))
    return storage


def test_insert_返回自增ID(storage):
    record = storage.insert(
        make_record(10.0, RecordType.INCOME, "工资", dt.date(2024, 1, 1))
    )
    assert record.id == 1
    second = storage.insert(
        make_record(20.0, RecordType.EXPENSE, "餐饮", dt.date(2024, 1, 2))
    )
    assert second.id == 2


def test_query_无条件返回全部并统计总数(seeded):
    items, total = seeded.query()
    assert total == 5
    assert len(items) == 5


def test_query_按类型筛选(seeded):
    items, total = seeded.query(type_=RecordType.EXPENSE)
    assert total == 3
    assert {item.category for item in items} == {"餐饮", "交通"}


def test_query_按分类筛选(seeded):
    items, total = seeded.query(category="工资")
    assert total == 2
    assert all(item.category == "工资" for item in items)


def test_query_按日期区间筛选(seeded):
    items, total = seeded.query(start=dt.date(2024, 2, 1), end=dt.date(2024, 2, 29))
    assert total == 2
    assert {item.date for item in items} == {dt.date(2024, 2, 10), dt.date(2024, 2, 20)}


def test_query_分页(seeded):
    page1, total = seeded.query(page=1, page_size=2)
    page2, _ = seeded.query(page=2, page_size=2)
    page3, _ = seeded.query(page=3, page_size=2)
    assert total == 5
    assert len(page1) == 2 and len(page2) == 2 and len(page3) == 1
    ids = [item.id for item in page1 + page2 + page3]
    assert len(set(ids)) == 5  # 分页不重不漏


def test_summary_全区间(seeded):
    income, expense = seeded.summary()
    assert income == 300.0
    assert expense == 100.0


def test_summary_指定区间(seeded):
    income, expense = seeded.summary(start=dt.date(2024, 2, 1), end=dt.date(2024, 2, 28))
    assert income == 200.0
    assert expense == 30.0


def test_summary_空数据返回0(storage):
    assert storage.summary() == (0.0, 0.0)


def test_并发写入不丢数据(tmp_path):
    storage = LedgerStorage(tmp_path / "concurrent.db")

    def write(index: int) -> None:
        storage.insert(
            make_record(
                float(index + 1), RecordType.INCOME, "并发", dt.date(2024, 5, 1)
            )
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(40)))

    items, total = storage.query(page_size=100)
    assert total == 40
    assert sorted(item.amount for item in items) == [float(i + 1) for i in range(40)]
