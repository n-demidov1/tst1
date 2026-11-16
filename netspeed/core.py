"""Логика замера: запросы, тайминги, расчёт скорости. Без вывода в консоль."""

from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass, field

CHUNK_SIZE = 64 * 1024
DEFAULT_TIMEOUT = 30.0
USER_AGENT = "netspeed/0.1 (+python-urllib)"


@dataclass(frozen=True)
class RequestResult:
    """Результат одного запроса."""

    bytes_received: int
    seconds: float


@dataclass(frozen=True)
class Summary:
    """Итог серии запросов."""

    results: list[RequestResult] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.results)

    @property
    def total_bytes(self) -> int:
        return sum(r.bytes_received for r in self.results)

    @property
    def total_seconds(self) -> float:
        return sum(r.seconds for r in self.results)

    @property
    def avg_seconds(self) -> float:
        return self.total_seconds / self.count if self.count else 0.0

    @property
    def speed_mbps(self) -> float:
        """Скорость в мегабитах в секунду (1 Мбит = 10^6 бит)."""
        return mbps(self.total_bytes, self.total_seconds)


def mbps(num_bytes: int, seconds: float) -> float:
    """Перевод байт за секунды в Мбит/с (десятичные мегабиты, как у провайдеров)."""
    if seconds <= 0:
        return 0.0
    return num_bytes * 8 / seconds / 1_000_000


def fetch_once(url: str, timeout: float = DEFAULT_TIMEOUT) -> RequestResult:
    """Скачивает ресурс целиком и возвращает объём и время.

    Время меряется от начала запроса (включая DNS, TCP/TLS-рукопожатие)
    до получения последнего байта тела ответа.
    """
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            # Просим не отдавать из кэша промежуточных прокси/CDN.
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            # Явно просим несжатые данные, чтобы мерить реальный объём.
            "Accept-Encoding": "identity",
        },
    )
    received = 0
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        while True:
            chunk = response.read(CHUNK_SIZE)
            if not chunk:
                break
            received += len(chunk)
    elapsed = time.perf_counter() - start
    return RequestResult(bytes_received=received, seconds=elapsed)


def measure(url: str, count: int = 10, timeout: float = DEFAULT_TIMEOUT, on_result=None) -> Summary:
    """Делает `count` последовательных запросов и возвращает сводку.

    `on_result(index, result)` вызывается после каждого запроса (для прогресса).
    """
    if count < 1:
        raise ValueError("count должен быть >= 1")
    results: list[RequestResult] = []
    for i in range(1, count + 1):
        result = fetch_once(url, timeout=timeout)
        results.append(result)
        if on_result is not None:
            on_result(i, result)
    return Summary(results=results)
