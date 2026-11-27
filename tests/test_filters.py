from datetime import date

from dashboard.filters import TradeFilter


def test_empty_filter_keeps_everything(trades):
    assert len(TradeFilter().apply(trades)) == len(trades)


def test_single_day(trades):
    day = date(2026, 3, 2)
    out = TradeFilter(start=day, end=day).apply(trades)
    assert out["trade_id"].tolist() == [1, 2]


def test_categorical_filters_combine_with_and(trades):
    out = TradeFilter(underlyings=("QQQ",), option_types=("Call",)).apply(trades)
    assert out["trade_id"].tolist() == [3]


def test_outcome_and_overnight(trades):
    assert TradeFilter(outcome="loss").apply(trades)["trade_id"].tolist() == [2, 3]
    assert TradeFilter(overnight=True).apply(trades)["trade_id"].tolist() == [4]


def test_describe_lists_active_conditions():
    text = TradeFilter(underlyings=("SPY", "QQQ"), outcome="win").describe()
    assert "标的：SPY、QQQ" in text
    assert "结果：盈利" in text
    assert TradeFilter().describe() == ["无筛选（全部交易）"]
