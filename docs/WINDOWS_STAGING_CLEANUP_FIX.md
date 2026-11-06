# Windows: sprzątanie po publikacji

Weryfikacja: 2026-11-05, Windows / CPython 3.13.15.

## Przyczyna potwierdzona

`stage.rename(final)` kończyło publikację wewnątrz `TemporaryDirectory`, a dopiero
wyjście z kontekstu usuwało pusty katalog `.synthetic-*`. WinError 32 w tym
sprzątaniu propagował się z funkcji i CLI błędnie zgłaszało nieudaną generację.

Sprawdzono lokalny przypadek autora: `.synthetic-4terleld` jest pusty. Partia
`diagnostics/9c570ca7f32027236002be03/` zawiera poprawne po 2 przykłady BTC/ETH;
manifest, CSV i metadane zweryfikowano istniejącym czytnikiem. Niczego nie usunięto.

Odtworzono WinError 32 na rzeczywistym Windows: uchwyt `CreateFileW` z GENERIC_READ
i bez FILE_SHARE_DELETE pozwalał przenieść dziecko `batch`, ale blokował usunięcie
pustego rodzica. `TemporaryDirectory.__exit__` rzucał błąd po kompletnej publikacji.
Nie ustalono procesu powodującego pierwotną blokadę. Przejrzane funkcje zapisu
i odczytu CSV/JSON zamykają uchwyty przed publikacją; nie znaleziono ich wycieku.

## Poprawka

Nowy `data_processing/staging.py` udostępnia `publication_workspace`. Tworzy własny
unikalny katalog mkdtemp, sprawdza jego położenie i sprząta wyłącznie ten katalog.
Nie szuka i nie usuwa starych pozostałości ani istniejących partii.

Blokady dostępu Windows 5/32/33 i EACCES/EPERM mają 4 próby sprzątania z przerwami
0,05 / 0,15 / 0,30 s. Po pomyślnym zakończeniu publikacji wyczerpana blokada daje
ostrzeżenie loggera z dokładną ścieżką, bez błędnego statusu operacji. Nie ma
finalizera TemporaryDirectory, który mógłby później ponownie zgłosić ten błąd.

Jeśli ciało operacji rzuci wyjątek, pozostaje on głównym wyjątkiem także przy
drugim błędzie sprzątania. Innych błędów sprzątania po sukcesie, np. EIO,
nie ignorujemy. Logger nie jest filtrem warnings, więc `-W error` nie zmienia
ostrzeżenia o sprzątaniu w niepowodzenie opublikowanej partii.

Ciała wszystkich trzech kontekstów kończą się dopiero po atomowym rename lub
hard linku. Weryfikacja CSV przed publikacją, atomowość i odmowa nadpisywania
pozostają. Analogiczny problem po os.link profilu i rename porównania naprawiono
tym samym pomocnikiem. Matematyki, seedów, formatów i profili nie zmieniono.

## Pliki i testy

Nowe pliki: `data_processing/staging.py`, `tests/integration/test_staging_cleanup.py`
i ten dokument. Zmiany: `pipelines/synthetic.py`, `pipelines/compare_synthetic.py`,
`synthetic/calibration.py`, `docs/ARCHITECTURE.md`, `docs/SYNTHETIC_V2_POWERSHELL.md`
oraz `.ai/CURRENT_STATE.md`.

Przed poprawką 96 testów OK; po poprawce **106 testów OK**. Dziesięć nowych testów
obejmuje przejściowe/trwałe blokady, rzeczywisty uchwyt Windows, błąd generatora,
rename i zapisu, inne błędy sprzątania, zachowanie pierwotnego wyjątku oraz udane
publikacje partii, profili i porównań. Sprawdzono też odmowę nadpisania.

Windows PowerShell i zainstalowany CLI przeszły dry-run oraz próbę 2 BTC + 2 ETH
w nowym systemowym katalogu tymczasowym z istniejącymi profilami v2: kod 0,
kompletna partia, brak pozostałości. Bez ponownej kalibracji i dużych eksperymentów.
SHA-256 wszystkich 381 wcześniejszych plików processed/ i synthetic/ bez zmian.

## Ponowienie w nowym output — PowerShell

Z katalogu głównego projektu:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
$retryOutput = 'data/synthetic/v2-smoke-20261105-cleanup-fixed'
if (Test-Path -LiteralPath $retryOutput) {
    throw 'Output już istnieje. Wybierz nową nazwę; nie usuwaj wcześniejszych wyników.'
}
.\.venv\Scripts\market-levels-generate-synthetic.exe `
    --generator-version v2 --v2-variant full --diagnostic `
    --count 2 --symbols BTCUSDT ETHUSDT --seed 20261107 `
    --profile BTCUSDT=data/synthetic/calibration/v2/BTCUSDT_train_2020_2023_v2_unapproved.json `
    --profile ETHUSDT=data/synthetic/calibration/v2/ETHUSDT_train_2020_2023_v2_unapproved.json `
    --output $retryOutput
if ($LASTEXITCODE -ne 0) { throw 'Generowanie zakończyło się błędem; sprawdź komunikat CLI.' }
```

Opcjonalne `--dry-run` nie utworzy outputu. Nowy katalog nie narusza poprzedniej
partii; jej identyfikator może pozostać taki sam, bo output nie zmienia symulacji.
Starego `.synthetic-4terleld` nie usuwamy automatycznie. Jego sprzątanie nie jest
wymagane do użycia nowego outputu.
