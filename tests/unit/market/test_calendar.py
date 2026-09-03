from datetime import date, datetime, time

from app.market.calendar import HOSECalendar


def dt(hour: int, minute: int, day: date = date(2026, 9, 3)) -> datetime:
    return datetime.combine(day, time(hour, minute))


def test_hose_total_regular_minutes_is_255() -> None:
    calendar = HOSECalendar()

    assert calendar.total_regular_trading_minutes(date(2026, 9, 3)) == 255


def test_elapsed_minutes_respects_session_boundaries() -> None:
    calendar = HOSECalendar()

    assert calendar.elapsed_trading_minutes(dt(9, 0)) == 0
    assert calendar.elapsed_trading_minutes(dt(9, 15)) == 15
    assert calendar.elapsed_trading_minutes(dt(11, 30)) == 150
    assert calendar.elapsed_trading_minutes(dt(12, 0)) == 150
    assert calendar.elapsed_trading_minutes(dt(13, 0)) == 150
    assert calendar.elapsed_trading_minutes(dt(13, 30)) == 180
    assert calendar.elapsed_trading_minutes(dt(14, 30)) == 240
    assert calendar.elapsed_trading_minutes(dt(14, 45)) == 255
    assert calendar.elapsed_trading_minutes(dt(14, 50)) == 255


def test_regular_and_post_market_windows_are_disjoint() -> None:
    calendar = HOSECalendar()

    assert calendar.is_regular_trading_time(dt(9, 15)) is True
    assert calendar.is_regular_trading_time(dt(11, 30)) is False
    assert calendar.is_regular_trading_time(dt(14, 44)) is True
    assert calendar.is_regular_trading_time(dt(14, 45)) is False
    assert calendar.is_post_market_time(dt(14, 45)) is True
    assert calendar.is_post_market_time(dt(15, 0)) is False


def test_weekends_and_configured_holidays_are_not_trading_days() -> None:
    holiday = date(2026, 9, 4)
    calendar = HOSECalendar(holidays={holiday})

    assert calendar.is_trading_day(date(2026, 9, 3)) is True
    assert calendar.is_trading_day(holiday) is False
    assert calendar.is_trading_day(date(2026, 9, 5)) is False
