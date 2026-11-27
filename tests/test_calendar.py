from datetime import date

from dashboard.calendar_view import (
    SELECTED_OUTLINE,
    calendar_figure,
    daily_summary,
    month_range,
    month_weekdays,
    month_weeks,
    shift_month,
    week_range,
)


def test_month_weekdays():
    days = month_weekdays(2026, 3)
    assert len(days) == 22
    assert all(d.weekday() < 5 and d.month == 3 for d in days)
    assert days[0] == date(2026, 3, 2)


def test_shift_month_across_years():
    assert shift_month(date(2026, 12, 1), 1) == date(2027, 1, 1)
    assert shift_month(date(2026, 1, 1), -1) == date(2025, 12, 1)


def test_daily_summary(trades):
    daily = daily_summary(trades)
    assert daily.loc[date(2026, 3, 2), "n"] == 2
    assert daily.loc[date(2026, 3, 2), "pnl"] == 50.0


def test_calendar_marks_notes_and_selection(trades):
    fig = calendar_figure(2026, 3, daily_summary(trades), {date(2026, 3, 3)}, selected=date(2026, 3, 4))
    points = fig.data[0]
    days = month_weekdays(2026, 3)
    assert len(points.x) == len(days)
    assert points.text[days.index(date(2026, 3, 3))] == "3•"
    assert points.marker.line.color[days.index(date(2026, 3, 4))] == SELECTED_OUTLINE


def test_calendar_in_english(trades):
    fig = calendar_figure(2026, 3, daily_summary(trades), set(), lang="en")
    assert list(fig.layout.xaxis.ticktext) == ["Wk", "Mon", "Tue", "Wed", "Thu", "Fri"]


def test_month_weeks_and_ranges():
    weeks = month_weeks(2026, 3)
    assert weeks[0] == date(2026, 3, 2) and weeks[-1] == date(2026, 3, 30)
    assert all(w.weekday() == 0 for w in weeks)
    assert week_range(date(2026, 3, 2)) == (date(2026, 3, 2), date(2026, 3, 6))
    assert month_range(2026, 2) == (date(2026, 2, 1), date(2026, 2, 28))
    # A month starting mid-week still gets a row for that partial week.
    assert month_weeks(2026, 10)[0] == date(2026, 9, 28)


def test_week_column(trades):
    fig = calendar_figure(2026, 3, daily_summary(trades), set(), selected_week=date(2026, 3, 2))
    weeks = fig.data[1]
    assert len(weeks.x) == len(month_weeks(2026, 3))
    assert weeks.text[0] == "W10"
    assert weeks.marker.line.color[0] == SELECTED_OUTLINE
    # Each day sits on the same row as its week marker.
    days = month_weekdays(2026, 3)
    assert fig.data[0].y[days.index(date(2026, 3, 2))] == weeks.y[0]
    assert fig.data[0].y[days.index(date(2026, 3, 31))] == weeks.y[-1]
