"""Консольный интерфейс: разбор аргументов и печать результата."""

from __future__ import annotations

import argparse
import sys
import urllib.error
from urllib.parse import urlparse

from . import core


def _valid_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise argparse.ArgumentTypeError(f"нужен http(s)-адрес, получено: {value!r}")
    return value


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("должно быть >= 1")
    return n


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="netspeed",
        description="Замер скорости интернета: N последовательных скачиваний одного адреса.",
    )
    parser.add_argument("url", type=_valid_url, help="адрес тяжёлого файла, например картинки")
    parser.add_argument("-n", "--count", type=_positive_int, default=10, help="число запросов (по умолчанию 10)")
    parser.add_argument(
        "-t", "--timeout", type=float, default=core.DEFAULT_TIMEOUT,
        help=f"таймаут одного запроса в секундах (по умолчанию {core.DEFAULT_TIMEOUT:g})",
    )
    return parser


def _print_progress(index: int, result: core.RequestResult) -> None:
    print(
        f"  запрос {index:>2}: {result.bytes_received / 1_000_000:8.3f} МБ "
        f"за {result.seconds:7.3f} с  ({core.mbps(result.bytes_received, result.seconds):8.2f} Мбит/с)",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    # При выводе в pipe/файл на Windows кодировка бывает cp1252 — кириллица
    # превращается в "???". Переключаемся на UTF-8 и построчную буферизацию,
    # чтобы stdout и stderr не перемешивались.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
            if encoding != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
            stream.reconfigure(line_buffering=True)

    args = build_parser().parse_args(argv)
    print(f"Замер скорости: {args.url}")
    print(f"Запросов: {args.count}, последовательно\n")

    try:
        summary = core.measure(args.url, count=args.count, timeout=args.timeout, on_result=_print_progress)
    except urllib.error.HTTPError as e:
        print(f"\nОшибка HTTP {e.code}: {e.reason}", file=sys.stderr)
        return 2
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        print(f"\nСетевая ошибка: {reason}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nПрервано пользователем", file=sys.stderr)
        return 130

    if summary.total_bytes == 0:
        print("\nСервер вернул пустой ответ — скорость посчитать нельзя.", file=sys.stderr)
        return 3

    print()
    print(f"Среднее время запроса:  {summary.avg_seconds:.3f} с")
    print(f"Всего скачано:          {summary.total_bytes / 1_000_000:.2f} МБ ({summary.total_bytes} байт)")
    print(f"Скорость скачивания:    {summary.speed_mbps:.2f} Мбит/с")
    return 0


if __name__ == "__main__":
    sys.exit(main())
