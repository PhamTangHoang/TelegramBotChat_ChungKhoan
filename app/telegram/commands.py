from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    command: str
    description: str


TELEGRAM_COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(command="start", description="Bắt đầu và xem hướng dẫn"),
    CommandSpec(command="help", description="Xem danh sách lệnh"),
    CommandSpec(command="analyze", description="Phân tích cổ phiếu: /analyze FPT"),
    CommandSpec(command="chart", description="Xem biểu đồ: /chart FPT"),
    CommandSpec(command="news", description="Xem tin tức: /news FPT"),
    CommandSpec(command="market", description="Xem trạng thái thị trường"),
)


HELP_TEXT = """VN Stock Analyst Bot hỗ trợ:

/analyze FPT
Phân tích kỹ thuật và bộ tiêu chí PP10Ulti của FPT.

/chart FPT
Xem biểu đồ kỹ thuật của FPT.

/news FPT
Xem tin tức liên quan, nguồn và link bài viết gốc.

/market
Xem trạng thái phiên giao dịch thị trường.

Bạn cũng có thể nhắn tự nhiên, ví dụ: "phân tích FPT" hoặc "tin tức FPT".

Lưu ý: Kết quả chỉ nhằm mục đích tham khảo và giáo dục, không phải khuyến nghị đầu tư."""


def command_menu() -> list[CommandSpec]:
    """Return a fresh, dependency-free command list for tests and adapters."""
    return list(TELEGRAM_COMMANDS)


def aiogram_command_menu() -> list[object]:
    """Convert the public command specs only when aiogram is installed at runtime."""
    from aiogram.types import BotCommand

    return [
        BotCommand(command=item.command, description=item.description)
        for item in command_menu()
    ]
