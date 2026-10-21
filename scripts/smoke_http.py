"""真实启动 uvicorn 并调用三个接口的冒烟脚本（用于验收演示）。

用法：python -m scripts.smoke_http
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8123"
DB_PATH = Path("output/smoke_ledger.db")


def wait_until_ready(client: httpx.Client, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if client.get(f"{BASE_URL}/health").status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.3)
    raise RuntimeError("服务启动超时")


def main() -> int:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.ledger.main:app",
         "--host", "127.0.0.1", "--port", "8123", "--log-level", "warning"],
        env={**__import__("os").environ, "LEDGER_DB": str(DB_PATH)},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        with httpx.Client(timeout=10.0) as client:
            wait_until_ready(client)

            print("== POST /records ==")
            for payload in (
                {"amount": 8000, "type": "收入", "category": "工资", "date": "2024-01-10"},
                {"amount": 1200, "type": "支出", "category": "房租", "date": "2024-01-15"},
                {"amount": 300, "type": "支出", "category": "餐饮", "date": "2024-02-03"},
            ):
                response = client.post(f"{BASE_URL}/records", json=payload)
                print(f"  {response.status_code} {response.json()}")

            print("== POST /records 非法金额 ==")
            response = client.post(
                f"{BASE_URL}/records",
                json={"amount": -5, "type": "收入", "category": "工资", "date": "2024-01-10"},
            )
            print(f"  {response.status_code} {response.json()}")

            print("== GET /records?type=支出&page_size=1 ==")
            response = client.get(f"{BASE_URL}/records", params={"type": "支出", "page_size": 1})
            print(f"  {response.status_code} {response.json()}")

            print("== GET /summary ==")
            response = client.get(f"{BASE_URL}/summary")
            print(f"  {response.status_code} {response.json()}")

            print("== GET /summary?start>end ==")
            response = client.get(
                f"{BASE_URL}/summary", params={"start": "2024-03-01", "end": "2024-01-01"}
            )
            print(f"  {response.status_code} {response.json()}")
    finally:
        process.terminate()
        process.wait(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
