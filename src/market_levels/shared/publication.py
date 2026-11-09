"""Atomic publication, bounded Windows retries and staging cleanup."""
from __future__ import annotations

import errno
import logging
import shutil
import tempfile
import time
from pathlib import Path
from contextlib import contextmanager
from collections.abc import Iterator


LOGGER = logging.getLogger("market_levels.data_processing.staging")


RETRY_DELAYS = (0.05, 0.15, 0.3)


def _access_conflict(error: OSError) -> bool:
    winerror = getattr(error, "winerror", None)
    if winerror is not None:
        return winerror in (5, 32, 33)
    return error.errno in (errno.EACCES, errno.EPERM)


def _require_absent(path: Path) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise FileExistsError(errno.EEXIST, "Kolizja publikacji: cel już istnieje; odmowa nadpisania", str(path))


def publish_directory(stage: Path, final: Path) -> None:
    """Atomowy rename kompletnego katalogu: 4 próby, 0.05/0.15/0.3 s.

    Ponawiamy tylko rename, nigdy tworzenie zawartości. Windows rename nie
    zastępuje istniejącego celu, również gdy pojawi się po kontroli lstat.
    Nie ma fallbacku kopiowania między woluminami ani replace(). Po wyczerpaniu
    limitu zachowujemy pierwszy wyjątek dostępu; każda próba ma wpis w logu.
    """
    stage, final = Path(stage), Path(final)
    if stage.stat().st_dev != final.parent.stat().st_dev:
        raise OSError(errno.EXDEV, "Publikacja wymaga tego samego woluminu", str(final))
    first_error = None
    attempts = len(RETRY_DELAYS)+1
    for attempt in range(attempts):
        LOGGER.info("Publikacja próba %d/%d: %s -> %s", attempt+1, attempts, stage, final)
        _require_absent(final)
        try:
            stage.rename(final)
        except OSError as error:
            LOGGER.warning("Publikacja próba %d/%d nieudana: %s -> %s; winerror=%s errno=%s: %s",
                           attempt+1, attempts, stage, final, getattr(error, 'winerror', None), error.errno, error)
            # Kolizja po rename jest błędem, nawet gdy wyjątek wygląda jak blokada.
            _require_absent(final)
            if not _access_conflict(error):
                raise
            if first_error is None:
                first_error = error
            if attempt == attempts-1:
                LOGGER.error("Publikacja: wyczerpano %d prób %s -> %s; zachowano pierwszy błąd: %s",
                             attempts, stage, final, first_error)
                raise first_error
            LOGGER.warning("Publikacja: ponowienie za %.2f s", RETRY_DELAYS[attempt])
            time.sleep(RETRY_DELAYS[attempt])
        else:
            if attempt:
                LOGGER.warning("Publikacja zakończona powodzeniem, próba %d/%d: %s -> %s",
                               attempt+1, attempts, stage, final)
            return


def _cleanup(root: Path) -> OSError | None:
    """Cztery próby dla blokad dostępu; inne błędy nie są ponawiane."""
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            shutil.rmtree(root)
            return None
        except FileNotFoundError as error:
            # Może dotyczyć znikniętego wpisu wewnątrz, nie całego katalogu.
            try:
                if not root.exists():
                    return None
            except OSError:
                pass
            return error
        except OSError as error:
            if not _access_conflict(error) or attempt == len(RETRY_DELAYS):
                return error
            time.sleep(RETRY_DELAYS[attempt])
    return None


@contextmanager
def publication_workspace(parent: Path, *, prefix: str) -> Iterator[Path]:
    """Ciało kończy się sukcesem dopiero po atomowej publikacji wyniku.

    Błąd w ciele zawsze pozostaje głównym wyjątkiem. Po sukcesie wyłącznie
    niesprzątana blokada dostępu staje się ostrzeżeniem. Nie ma finalizera
    TemporaryDirectory, który mógłby ponownie zgłosić ten sam błąd.
    """
    parent = Path(parent).resolve()
    root = Path(tempfile.mkdtemp(prefix=prefix, dir=parent)).resolve()
    if root.parent != parent:
        raise ValueError("Katalog roboczy wychodzi poza wskazany katalog nadrzędny")
    operation_error = None
    try:
        yield root
    except BaseException as error:
        operation_error = error
        raise
    finally:
        try:
            cleanup_error = _cleanup(root)
        except Exception as error:
            # Także nieoczekiwany błąd sprzątania nie zastępuje błędu operacji.
            cleanup_error = error
        if cleanup_error is not None:
            if operation_error is not None:
                LOGGER.warning("OSTRZEŻENIE: nie udało się posprzątać %s po błędzie operacji; "
                               "zachowano pierwotny błąd. Sprzątanie: %s", root, cleanup_error)
            elif isinstance(cleanup_error, OSError) and _access_conflict(cleanup_error):
                LOGGER.warning("OSTRZEŻENIE: wynik został opublikowany, ale po 4 próbach "
                               "nie udało się usunąć katalogu roboczego %s: %s. "
                               "Można posprzątać ten katalog po zwolnieniu blokady.", root, cleanup_error)
            else:
                raise cleanup_error
