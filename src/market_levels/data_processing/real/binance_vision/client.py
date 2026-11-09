"""Adresy Binance Vision oraz transfer HTTP z ponawianiem i plikami .part."""
from __future__ import annotations

import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE = "https://data.binance.vision/data/spot"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
INTERVAL = "4h"
USER_AGENT = "Academic-OHLC-Research/1.0 (non-commercial)"


class DownloadError(RuntimeError):
    """Błąd pobrania lub weryfikacji archiwum źródłowego."""


def _remote_url(symbol: str, period: str, category: str = "monthly") -> str:
    return f"{BASE}/{category}/klines/{symbol}/{INTERVAL}/{symbol}-{INTERVAL}-{period}.zip"


def _get(url: str, target: Path, offline: bool, attempts: int = 3) -> None:
    if target.exists():
        return
    if offline:
        raise DownloadError(f"Brak pliku w trybie offline: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=35) as stream, tmp.open("wb") as out:
                while True:
                    block = stream.read(128 * 1024)
                    if not block:
                        break
                    out.write(block)
            tmp.replace(target)
            time.sleep(0.15)
            return
        except HTTPError as exc:
            tmp.unlink(missing_ok=True)
            if exc.code == 404:
                raise DownloadError(f"404: {url}") from exc
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise DownloadError(f"HTTP {exc.code}: {url}") from exc
        except (OSError, URLError) as exc:
            tmp.unlink(missing_ok=True)
            if attempt == attempts - 1:
                raise DownloadError(f"Błąd pobierania {url}: {exc}") from exc
        time.sleep(2 ** attempt)
