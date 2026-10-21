"""生成含脏数据的样例 sales_raw.xlsx（仅用于本地验证，不属于交付主流程）。

脏数据类型刻意覆盖需求中提到的三类：
1. 关键字段缺失（销售员 / 单价 / 日期为空）
2. 数量 <= 0 的异常行（0 与负数）
3. 完全重复行

清洗后应剩余 8 条有效数据，便于人工核对统计结果。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

COLUMNS = ["日期", "销售员", "产品", "数量", "单价", "地区"]

# (日期, 销售员, 产品, 数量, 单价, 地区)
ROWS = [
    # ---- 有效数据：2024-01 ----
    (dt.date(2024, 1, 5), "张三", "A", 10, 100.0, "华东"),
    (dt.date(2024, 1, 6), "张三", "B", 5, 200.0, "华北"),
    (dt.date(2024, 1, 7), "李四", "A", 8, 100.0, "华东"),
    (dt.date(2024, 1, 8), "王五", "C", 3, 50.0, "华南"),
    # ---- 有效数据：2024-02 ----
    (dt.date(2024, 2, 3), "张三", "A", 20, 100.0, "华东"),
    (dt.date(2024, 2, 5), "李四", "B", 4, 200.0, "华北"),
    (dt.date(2024, 2, 10), "王五", "A", 6, 100.0, "华南"),
    (dt.date(2024, 2, 11), "李四", "C", 2, 50.0, "华南"),
    # ---- 脏数据：关键字段缺失 ----
    (dt.date(2024, 2, 12), None, "A", 5, 100.0, "华东"),
    (dt.date(2024, 2, 13), "张三", "B", 5, None, "华北"),
    (None, "李四", "A", 5, 100.0, "华东"),
    # ---- 脏数据：数量 <= 0 ----
    (dt.date(2024, 2, 14), "张三", "C", 0, 50.0, "华东"),
    (dt.date(2024, 2, 15), "王五", "B", -3, 200.0, "华北"),
    # ---- 脏数据：与第 1 行完全重复 ----
    (dt.date(2024, 1, 5), "张三", "A", 10, 100.0, "华东"),
]


def build_dataframe() -> pd.DataFrame:
    return pd.DataFrame(ROWS, columns=COLUMNS)


def main(output_path: str | Path = "data/sales_raw.xlsx") -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = build_dataframe()
    df.to_excel(output_path, index=False, engine="openpyxl")
    print(f"已生成样例数据：{output_path}（共 {len(df)} 行，其中脏数据 6 行）")
    return output_path


if __name__ == "__main__":
    main()
