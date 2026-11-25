"""Простое хранилище состояния диалога по каждому VK-пользователю.

В памяти процесса — при перезапуске контейнера незавершённые диалоги
сбрасываются, это ожидаемо и не критично.
"""

_sessions: dict[int, dict] = {}


def get_session(user_id: int) -> dict:
    return _sessions.setdefault(user_id, {})


def reset_session(user_id: int) -> None:
    _sessions[user_id] = {}
