"""Утилиты для работы с временем и другими вспомогательными функциями."""

import re
from datetime import timedelta

# Паттерн для парсинга времени: 1d2h30m, 5m, 1w и т.д.
# Поддержка английских (w, d, h, m, s) и русских (н, д, ч, м, с) модификаторов
TIME_PATTERN = re.compile(r"(?P<value>\d+)(?P<modifier>[wdhmsндчмс])")

# Множители для конвертации в секунды
SECONDS_IN_MINUTE = 60
SECONDS_IN_HOUR = 3600
SECONDS_IN_DAY = 86400
SECONDS_IN_WEEK = 604800

TIME_MULTIPLIERS = {
    # Английские модификаторы
    "w": SECONDS_IN_WEEK,
    "d": SECONDS_IN_DAY,
    "h": SECONDS_IN_HOUR,
    "m": SECONDS_IN_MINUTE,
    "s": 1,
    # Русские модификаторы
    "н": SECONDS_IN_WEEK,  # неделя
    "д": SECONDS_IN_DAY,  # день
    "ч": SECONDS_IN_HOUR,  # час
    "м": SECONDS_IN_MINUTE,  # минута
    "с": 1,  # секунда
}


def parse_timedelta(time_str: str) -> timedelta | None:
    """
    Парсит строку времени в timedelta.

    Поддерживаемые форматы (английские):
    - 30s — 30 секунд
    - 5m — 5 минут
    - 2h — 2 часа
    - 1d — 1 день
    - 1w — 1 неделя
    - 1d12h30m — комбинации

    Поддерживаемые форматы (русские):
    - 30с — 30 секунд
    - 5м — 5 минут
    - 2ч — 2 часа
    - 1д — 1 день
    - 1н — 1 неделя
    - 1д12ч30м — комбинации

    Возвращает None если формат неверный.
    """
    if not time_str:
        return None

    matches = TIME_PATTERN.findall(time_str.lower())
    if not matches:
        return None

    total_seconds = 0
    for value, modifier in matches:
        total_seconds += int(value) * TIME_MULTIPLIERS[modifier]

    if total_seconds == 0:
        return None

    return timedelta(seconds=total_seconds)


def format_timedelta(td: timedelta) -> str:
    """Форматирует timedelta в читаемую строку."""
    total_seconds = int(td.total_seconds())

    if total_seconds < SECONDS_IN_MINUTE:
        return f"{total_seconds} сек."

    parts = []
    days, remainder = divmod(total_seconds, SECONDS_IN_DAY)
    hours, remainder = divmod(remainder, SECONDS_IN_HOUR)
    minutes, seconds = divmod(remainder, SECONDS_IN_MINUTE)

    if days:
        parts.append(f"{days} дн.")
    if hours:
        parts.append(f"{hours} ч.")
    if minutes:
        parts.append(f"{minutes} мин.")
    if seconds and not days:  # Секунды показываем только если нет дней
        parts.append(f"{seconds} сек.")

    return " ".join(parts) if parts else "0 сек."
