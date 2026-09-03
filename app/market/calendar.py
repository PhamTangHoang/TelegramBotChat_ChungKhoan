from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass(frozen=True, slots=True)
class TradingSession:
    name: str
    start: time
    end: time
    regular: bool = True


class ExchangeCalendar(ABC):
    timezone = VIETNAM_TZ

    @abstractmethod
    def is_trading_day(self, trading_date: date) -> bool:
        raise NotImplementedError

    @abstractmethod
    def sessions(self, trading_date: date) -> tuple[TradingSession, ...]:
        raise NotImplementedError

    def _local_time(self, value: datetime) -> time:
        if value.tzinfo is None:
            return value.replace(tzinfo=self.timezone).time()
        return value.astimezone(self.timezone).time()

    def is_regular_trading_time(self, value: datetime) -> bool:
        trading_date = value.astimezone(self.timezone).date() if value.tzinfo else value.date()
        current_time = self._local_time(value)
        return self.is_trading_day(trading_date) and any(
            session.regular and session.start <= current_time < session.end
            for session in self.sessions(trading_date)
        )

    def is_post_market_time(self, value: datetime) -> bool:
        trading_date = value.astimezone(self.timezone).date() if value.tzinfo else value.date()
        current_time = self._local_time(value)
        return self.is_trading_day(trading_date) and any(
            not session.regular and session.start <= current_time < session.end
            for session in self.sessions(trading_date)
        )

    def elapsed_trading_minutes(self, value: datetime) -> int:
        trading_date = value.astimezone(self.timezone).date() if value.tzinfo else value.date()
        if not self.is_trading_day(trading_date):
            return 0
        current_time = self._local_time(value)
        elapsed = 0
        for session in self.sessions(trading_date):
            duration = _minutes_between(session.start, session.end)
            if current_time >= session.end:
                if session.regular:
                    elapsed += duration
                continue
            if session.regular and current_time >= session.start:
                elapsed += _minutes_between(session.start, current_time)
            break
        return max(0, min(elapsed, self.total_regular_trading_minutes(trading_date)))

    def total_regular_trading_minutes(self, trading_date: date) -> int:
        if not self.is_trading_day(trading_date):
            return 0
        return sum(
            _minutes_between(session.start, session.end)
            for session in self.sessions(trading_date)
            if session.regular
        )

    def describe_session(self, value: datetime) -> str:
        local = (
            value.replace(tzinfo=self.timezone)
            if value.tzinfo is None
            else value.astimezone(self.timezone)
        )
        trading_date = local.date()
        current_time = local.time()
        regular_sessions = [
            session for session in self.sessions(trading_date) if session.regular
        ]
        regular_hours = " và ".join(
            f"{_format_time(session.start)}–{_format_time(session.end)}"
            for session in _merge_display_sessions(regular_sessions)
        )

        if not self.is_trading_day(trading_date):
            return f"HOSE: ĐÓNG CỬA\nNgày {trading_date.isoformat()} không có giao dịch."

        current_session = next(
            (
                session
                for session in self.sessions(trading_date)
                if session.start <= current_time < session.end
            ),
            None,
        )
        if current_session is not None:
            state = "ĐANG GIAO DỊCH" if current_session.regular else "HẬU PHIÊN"
            return (
                f"HOSE: {state}\n"
                f"Phiên: {current_session.name} "
                f"({_format_time(current_session.start)}–{_format_time(current_session.end)})\n"
                f"Giờ regular: {regular_hours}"
            )

        next_session = next(
            (session for session in self.sessions(trading_date) if current_time < session.start),
            None,
        )
        if next_session is not None and any(
            session.regular and current_time >= session.end for session in regular_sessions
        ):
            return (
                "HOSE: NGHỈ GIỮA PHIÊN\n"
                f"Phiên tiếp theo: {next_session.name} "
                f"({_format_time(next_session.start)}–{_format_time(next_session.end)})\n"
                f"Giờ regular: {regular_hours}"
            )
        if next_session is not None:
            return (
                "HOSE: CHƯA MỞ\n"
                f"Phiên tiếp theo: {next_session.name} "
                f"({_format_time(next_session.start)}–{_format_time(next_session.end)})\n"
                f"Giờ regular: {regular_hours}"
            )
        return f"HOSE: ĐÃ ĐÓNG CỬA\nGiờ regular: {regular_hours}"


def _minutes_between(start: time, end: time) -> int:
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


def _format_time(value: time) -> str:
    return value.strftime("%H:%M")


def _merge_display_sessions(sessions: list[TradingSession]) -> list[TradingSession]:
    if not sessions:
        return []
    merged: list[TradingSession] = [sessions[0]]
    for session in sessions[1:]:
        previous = merged[-1]
        if previous.end == session.start:
            merged[-1] = TradingSession(
                name=previous.name,
                start=previous.start,
                end=session.end,
                regular=True,
            )
        else:
            merged.append(session)
    return merged


class HOSECalendar(ExchangeCalendar):
    """HOSE equity sessions for the configured calendar version."""

    _sessions = (
        TradingSession("ATO", time(9, 0), time(9, 15)),
        TradingSession("CONTINUOUS_I", time(9, 15), time(11, 30)),
        TradingSession("CONTINUOUS_II", time(13, 0), time(14, 30)),
        TradingSession("ATC", time(14, 30), time(14, 45)),
        TradingSession("OFF_SESSION", time(14, 45), time(15, 0), regular=False),
    )

    def __init__(self, holidays: set[date] | None = None) -> None:
        self.holidays = frozenset(holidays or set())

    def is_trading_day(self, trading_date: date) -> bool:
        return trading_date.weekday() < 5 and trading_date not in self.holidays

    def sessions(self, trading_date: date) -> tuple[TradingSession, ...]:
        return self._sessions
