"""M1 单测：原始表读取 + 数据清洗。"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from src.make_sample_data import COLUMNS, build_dataframe
from src.report_gen import (
    REQUIRED_COLUMNS,
    SHEET_BY_REGION,
    SHEET_BY_SALESMAN,
    SHEET_DETAIL,
    SHEET_OVERVIEW,
    MissingColumnsError,
    NoValidDataError,
    ReportError,
    add_amount,
    build_monthly_summary,
    build_region_summary,
    build_salesman_summary,
    clean_data,
    generate_report,
    main,
    read_raw,
    round_amount,
    total_amount,
    write_report,
)


@pytest.fixture()
def raw_df() -> pd.DataFrame:
    """样例原始表：14 行，其中 6 行脏数据。"""
    return build_dataframe()


@pytest.fixture()
def raw_xlsx(tmp_path, raw_df):
    path = tmp_path / "sales_raw.xlsx"
    raw_df.to_excel(path, index=False, engine="openpyxl")
    return path


# ---------- 读取 ----------

def test_read_raw_正常读取(raw_xlsx):
    df = read_raw(raw_xlsx)
    assert list(df.columns) == COLUMNS
    assert len(df) == 14


def test_read_raw_文件不存在(tmp_path):
    with pytest.raises(ReportError, match="不存在"):
        read_raw(tmp_path / "not_exist.xlsx")


def test_read_raw_非xlsx后缀(tmp_path):
    path = tmp_path / "sales_raw.csv"
    path.write_text("日期,销售员\n", encoding="utf-8")
    with pytest.raises(ReportError, match="xlsx"):
        read_raw(path)


def test_read_raw_缺少必需字段列(tmp_path):
    df = pd.DataFrame({"日期": [dt.date(2024, 1, 1)], "销售员": ["张三"]})
    path = tmp_path / "missing.xlsx"
    df.to_excel(path, index=False, engine="openpyxl")
    with pytest.raises(MissingColumnsError, match="缺少必需字段列"):
        read_raw(path)


def test_read_raw_空表只有表头(tmp_path):
    path = tmp_path / "empty.xlsx"
    pd.DataFrame(columns=COLUMNS).to_excel(path, index=False, engine="openpyxl")
    with pytest.raises(ReportError, match="为空"):
        read_raw(path)


# ---------- 清洗 ----------

def test_clean_样例数据剩8行(raw_df):
    cleaned = clean_data(raw_df)
    assert len(cleaned) == 8


def test_clean_关键字段无缺失且数量为正(raw_df):
    cleaned = clean_data(raw_df)
    assert cleaned[REQUIRED_COLUMNS].notna().all().all()
    assert (cleaned["数量"] > 0).all()


def test_clean_按全字段去重(raw_df):
    cleaned = clean_data(raw_df)
    assert not cleaned.duplicated(subset=REQUIRED_COLUMNS).any()
    # 与第 1 行重复的脏数据被去掉，只剩一条 2024-01-05 张三 A
    dup = cleaned[
        (cleaned["日期"] == pd.Timestamp("2024-01-05"))
        & (cleaned["销售员"] == "张三")
        & (cleaned["产品"] == "A")
    ]
    assert len(dup) == 1


def test_clean_删除关键字段缺失行(raw_df):
    cleaned = clean_data(raw_df)
    # 销售员为空 / 单价为空 / 日期为空的三行都应被删除
    assert not cleaned["销售员"].isna().any()
    assert not cleaned["单价"].isna().any()
    assert not cleaned["日期"].isna().any()


def test_clean_剔除数量非正(raw_df):
    cleaned = clean_data(raw_df)
    assert 0 not in set(cleaned["数量"])
    assert cleaned["数量"].min() > 0
    # 原始脏数据里的 0 和 -3 不应出现在结果中
    assert set(cleaned["数量"]) == {10, 5, 8, 3, 20, 4, 6, 2}


def test_clean_不修改原始DataFrame(raw_df):
    before = raw_df.copy(deep=True)
    clean_data(raw_df)
    pd.testing.assert_frame_equal(raw_df, before)


def test_clean_空白字符串视为缺失():
    df = pd.DataFrame(
        [
            [dt.date(2024, 1, 1), "  ", "A", 1, 10.0, "华东"],
            [dt.date(2024, 1, 2), "张三", "A", 1, 10.0, "  "],
        ],
        columns=COLUMNS,
    )
    with pytest.raises(NoValidDataError):
        clean_data(df)


def test_clean_数量为文本视为缺失():
    df = pd.DataFrame(
        [
            [dt.date(2024, 1, 1), "张三", "A", "5个", 10.0, "华东"],
            [dt.date(2024, 1, 2), "李四", "A", 3, 10.0, "华东"],
        ],
        columns=COLUMNS,
    )
    cleaned = clean_data(df)
    assert len(cleaned) == 1
    assert cleaned.iloc[0]["销售员"] == "李四"


def test_clean_无有效数据报错():
    df = pd.DataFrame(
        [[dt.date(2024, 1, 1), "张三", "A", 0, 10.0, "华东"]],
        columns=COLUMNS,
    )
    with pytest.raises(NoValidDataError, match="没有任何有效数据"):
        clean_data(df)


# ---------- 统计聚合 ----------

@pytest.fixture()
def cleaned_with_amount(raw_df) -> pd.DataFrame:
    return add_amount(clean_data(raw_df))


def test_round_amount_四舍五入():
    assert round_amount(1.005) == 1.01
    assert round_amount(2.675) == 2.68
    assert round_amount(100) == 100.0


def test_add_amount_销售额等于数量乘单价(cleaned_with_amount):
    row = cleaned_with_amount[
        (cleaned_with_amount["销售员"] == "张三") & (cleaned_with_amount["产品"] == "B")
    ].iloc[0]
    assert row["销售额"] == 1000.0


def test_按销售员汇总(cleaned_with_amount):
    summary = build_salesman_summary(cleaned_with_amount)
    assert list(summary.columns) == ["销售员", "销售额"]
    result = dict(zip(summary["销售员"], summary["销售额"]))
    assert result == {"张三": 4000.0, "李四": 1700.0, "王五": 750.0}
    # 降序排列
    assert list(summary["销售额"]) == [4000.0, 1700.0, 750.0]


def test_按地区汇总(cleaned_with_amount):
    summary = build_region_summary(cleaned_with_amount)
    result = dict(zip(summary["地区"], summary["销售额"]))
    assert result == {"华东": 3800.0, "华北": 1800.0, "华南": 850.0}


def test_按月汇总(cleaned_with_amount):
    summary = build_monthly_summary(cleaned_with_amount)
    assert list(summary.columns) == ["月份", "销售额"]
    result = dict(zip(summary["月份"], summary["销售额"]))
    assert result == {"2024-01": 2950.0, "2024-02": 3500.0}


def test_总额与两种维度汇总一致(cleaned_with_amount):
    total = total_amount(cleaned_with_amount)
    assert total == 6450.0
    assert total == round_amount(build_salesman_summary(cleaned_with_amount)["销售额"].sum())
    assert total == round_amount(build_region_summary(cleaned_with_amount)["销售额"].sum())
    assert total == round_amount(build_monthly_summary(cleaned_with_amount)["销售额"].sum())


# ---------- Excel 输出 ----------

@pytest.fixture()
def report_file(tmp_path, raw_df):
    cleaned = add_amount(clean_data(raw_df))
    return write_report(
        tmp_path / "report.xlsx",
        raw_count=len(raw_df),
        cleaned_with_amount=cleaned,
        salesman_summary=build_salesman_summary(cleaned),
        region_summary=build_region_summary(cleaned),
        monthly_summary=build_monthly_summary(cleaned),
    )


def test_报告包含四个工作表(report_file):
    import openpyxl

    workbook = openpyxl.load_workbook(report_file)
    assert workbook.sheetnames == [SHEET_DETAIL, SHEET_BY_SALESMAN, SHEET_BY_REGION, SHEET_OVERVIEW]


def test_明细清洗后工作表内容(report_file):
    detail = pd.read_excel(report_file, sheet_name=SHEET_DETAIL)
    assert len(detail) == 8
    assert "销售额" in detail.columns


def test_按销售员工作表内容(report_file):
    sheet = pd.read_excel(report_file, sheet_name=SHEET_BY_SALESMAN)
    assert dict(zip(sheet["销售员"], sheet["销售额"])) == {
        "张三": 4000.0,
        "李四": 1700.0,
        "王五": 750.0,
    }


def test_按地区工作表内容(report_file):
    sheet = pd.read_excel(report_file, sheet_name=SHEET_BY_REGION)
    assert dict(zip(sheet["地区"], sheet["销售额"])) == {
        "华东": 3800.0,
        "华北": 1800.0,
        "华南": 850.0,
    }


def test_总览工作表含指标与月度明细(report_file):
    sheet = pd.read_excel(report_file, sheet_name=SHEET_OVERVIEW)
    result = dict(zip(sheet["指标"].astype(str), sheet["数值"]))
    assert result["原始记录数"] == 14
    assert result["清洗后记录数"] == 8
    assert result["剔除记录数"] == 6
    assert result["涉及月份数"] == 2
    assert result["销售总额"] == 6450.0
    assert result["2024-01"] == 2950.0
    assert result["2024-02"] == 3500.0


# ---------- 端到端 / CLI ----------

def test_端到端_生成报表且原始文件未被修改(tmp_path, raw_df):
    import hashlib

    def digest(path):
        return hashlib.md5(path.read_bytes()).hexdigest()

    raw_path = tmp_path / "sales_raw.xlsx"
    raw_df.to_excel(raw_path, index=False, engine="openpyxl")
    before = digest(raw_path)

    output_path = tmp_path / "report.xlsx"
    generate_report(raw_path, output_path)

    assert output_path.exists()
    assert digest(raw_path) == before, "原始文件被修改了！"
    assert raw_df.iloc[0]["销售员"] == "张三"  # 内存中的原始数据未被就地改动


def test_CLI_文件不存在返回1并提示(tmp_path, capsys):
    exit_code = main(["--input", str(tmp_path / "none.xlsx"), "--output", str(tmp_path / "o.xlsx")])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "不存在" in captured.err


def test_CLI_缺列返回1并提示缺哪列(tmp_path, capsys):
    path = tmp_path / "bad.xlsx"
    pd.DataFrame({"日期": [dt.date(2024, 1, 1)], "销售员": ["张三"]}).to_excel(
        path, index=False, engine="openpyxl"
    )
    exit_code = main(["--input", str(path), "--output", str(tmp_path / "o.xlsx")])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "缺少必需字段列" in captured.err
    assert "数量" in captured.err


def test_CLI_无有效数据返回1并提示(tmp_path, capsys):
    path = tmp_path / "zero.xlsx"
    pd.DataFrame(
        [[dt.date(2024, 1, 1), "张三", "A", 0, 10.0, "华东"]], columns=COLUMNS
    ).to_excel(path, index=False, engine="openpyxl")
    exit_code = main(["--input", str(path), "--output", str(tmp_path / "o.xlsx")])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "没有任何有效数据" in captured.err


def test_CLI_正常执行返回0(tmp_path, raw_df, capsys):
    raw_path = tmp_path / "sales_raw.xlsx"
    raw_df.to_excel(raw_path, index=False, engine="openpyxl")
    exit_code = main(["--input", str(raw_path), "--output", str(tmp_path / "report.xlsx")])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "销售总额：6450.0" in captured.out
