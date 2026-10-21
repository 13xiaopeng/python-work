"""M5-2 单测：记账 HTTP 接口（正常 + 边界/异常）。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.ledger.main import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "test_ledger.db")
    with TestClient(app) as test_client:
        yield test_client


def post_record(client: TestClient, **overrides):
    payload = {
        "amount": 100.0,
        "type": "收入",
        "category": "工资",
        "date": "2024-01-10",
    }
    payload.update(overrides)
    return client.post("/records", json=payload)


# ---------- 正常路径 ----------

def test_健康检查(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_新增流水返回201(client):
    response = post_record(client)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["amount"] == 100.0
    assert body["type"] == "收入"
    assert body["category"] == "工资"
    assert body["date"] == "2024-01-10"


def test_列表分页与筛选(client):
    post_record(client, amount=100.0, category="工资", date="2024-01-10")
    post_record(client, amount=50.0, type="支出", category="餐饮", date="2024-01-15")
    post_record(client, amount=200.0, category="工资", date="2024-02-10")
    post_record(client, amount=30.0, type="支出", category="交通", date="2024-02-20")

    page = client.get("/records", params={"page": 1, "page_size": 2}).json()
    assert page["total"] == 4
    assert len(page["items"]) == 2

    income = client.get("/records", params={"type": "收入"}).json()
    assert income["total"] == 2

    category = client.get("/records", params={"category": "工资"}).json()
    assert category["total"] == 2

    ranged = client.get(
        "/records", params={"start": "2024-02-01", "end": "2024-02-28"}
    ).json()
    assert ranged["total"] == 2
    assert {item["date"] for item in ranged["items"]} == {"2024-02-10", "2024-02-20"}


def test_汇总收入支出与结余(client):
    post_record(client, amount=100.0, category="工资", date="2024-01-10")
    post_record(client, amount=50.0, type="支出", category="餐饮", date="2024-01-15")
    post_record(client, amount=200.0, category="工资", date="2024-02-10")

    body = client.get("/summary").json()
    assert body["income_total"] == 300.0
    assert body["expense_total"] == 50.0
    assert body["balance"] == 250.0

    ranged = client.get(
        "/summary", params={"start": "2024-02-01", "end": "2024-02-28"}
    ).json()
    assert ranged["income_total"] == 200.0
    assert ranged["expense_total"] == 0.0
    assert ranged["balance"] == 200.0


def test_汇总空数据返回0而不是报错(client):
    response = client.get("/summary")
    assert response.status_code == 200
    assert response.json()["balance"] == 0.0


# ---------- 参数校验（异常路径） ----------

@pytest.mark.parametrize("amount", [0, -1, -99.9])
def test_金额必须大于0(client, amount):
    response = post_record(client, amount=amount)
    assert response.status_code == 422
    assert any("amount" in item["loc"] for item in response.json()["detail"])


def test_类型必须合法(client):
    response = post_record(client, type="转账")
    assert response.status_code == 422
    assert any("type" in item["loc"] for item in response.json()["detail"])


@pytest.mark.parametrize("bad_date", ["2024/01/10", "20240110", "not-a-date", ""])
def test_日期格式非法(client, bad_date):
    response = post_record(client, date=bad_date)
    assert response.status_code == 422
    assert any("date" in item["loc"] for item in response.json()["detail"])


def test_缺少必填字段(client):
    response = client.post("/records", json={"amount": 10.0})
    assert response.status_code == 422


def test_分类为空字符串(client):
    response = post_record(client, category="   ")
    assert response.status_code == 422
    assert any("category" in item["loc"] for item in response.json()["detail"])


def test_分页参数越界(client):
    assert client.get("/records", params={"page": 0}).status_code == 422
    assert client.get("/records", params={"page_size": 0}).status_code == 422
    assert client.get("/records", params={"page_size": 101}).status_code == 422
    assert client.get("/records", params={"page": "abc"}).status_code == 422


def test_日期区间起止颠倒(client):
    response = client.get(
        "/records", params={"start": "2024-03-01", "end": "2024-01-01"}
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "value_error.date_range"


def test_非法参数返回结构化错误体(client):
    response = post_record(client, amount=-1)
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert {"type", "loc", "msg"} <= set(detail[0].keys())
