# Raport wdrożenia generatora OHLC

Data: 2026-11-03. Środowisko weryfikacji: Windows, CPython 3.13.15.

## Zakres i wynik

Wdrożono generator w istniejącym pakiecie `market_levels`, wraz z osobną
kalibracją, walidacją, diagnostyką, konfiguracją, pipeline i CLI.
Nie dodano zależności uruchomieniowych. Nie utworzono commita.
Nie wykonano kalibracji na historii 2020–2026 ani docelowej generacji danych.

Powstaje niezależna seria 120 świec 4h, każda z 12 wewnętrznych kroków.
Cena jest wykładnikiem losowego procesu logarytmicznego: dryf dzielimy przez 12,
sigma przez sqrt(12), a szum ma rozkład standardowy normalny. Trendy mają
odpowiedni znak dryfu, konsolidacja dodaje płynny powrót do lokalnego środka,
wybicie po konsolidacji jest krótsze i ma silniejszy dryf oraz większą zmienność.
Ważone sekwencje spełniają limity długości i przejść. High/Low wynikają wyłącznie
z wewnętrznej ścieżki; Open kolejnej świecy jest poprzednim Close.

Użyto wspólnego modelu `Candle`, `Decimal`, UTC, odstępu 4h, walidatorów cen,
OHLC i czasu oraz `check_series()`, `write_candles_csv()`, `write_json()`.
Do wspólnego storage dodano odczyt istniejącego formatu CSV.
Nie zmieniono istniejących funkcji zapisu, walidacji, pobierania ani starego CLI.

## Nowe i zmienione pliki

`+` oznacza nowy plik, `~` zmodyfikowany.

```text
~ .ai/CURRENT_STATE.md
~ .ai/WORKFLOW.md
~ README.md
~ configs/experiment.json
~ pyproject.toml
docs/
  ~ ARCHITECTURE.md
  ~ DECYZJE_3_3.md
  ~ LICENCJA_DANYCH.md
  + SYNTHETIC_GENERATOR.md
  + SYNTHETIC_IMPLEMENTATION_REPORT.md
src/market_levels/
  cli/
    + generate_synthetic.py
  data_processing/
    ~ storage.py
    pipelines/
      + synthetic.py
    synthetic/
      ~ README.md
      + __init__.py
      + settings.py
      + regimes.py
      + generator.py
      + calibration.py
      + quality.py
tests/
  unit/
    + test_synthetic.py
  integration/
    + test_synthetic_pipeline.py
```

## Status parametrów i ochrona przed przeciekiem

| Grupa | Status |
| --- | --- |
| BTC/ETH, 4h, 120 świec, 12 kroków, 1–3 fazy | zatwierdzone założenia autora |
| Siły trendu/wybicia, mnożniki zmienności, rewersja, długości i wagi faz | jawne parametry projektowe, wymagające sprawdzenia |
| Sigma BTC 0,012 / ETH 0,016 i zakresy cen BTC 20–70 tys. / ETH 1–4 tys. | wyłącznie ręczna diagnostyka |
| Sigma próbki zwrotów 4h i kwantyle 5%/95% Close | implementacja estymacji gotowa; brak końcowego profilu empirycznego |
| Seed 20261103 i 5 przykładów na instrument | robocze ustawienia kontroli działania |
| Cel 800 wykresów, 55% syntetycznych, roboczo 440 | zachowany cel eksperymentu; nie jest automatycznie generowany |

Pełne zakresy wszystkich parametrów opisano w
[SYNTHETIC_GENERATOR.md](SYNTHETIC_GENERATOR.md#parametry-i-ich-status).

Kalibracja wymaga jawnych granic UTC i wyznacza statystyki tylko wewnątrz nich.
Nie łączy zwrotów przez luki. Profile są domyślnie niezatwierdzone. Do generowania
kandydatów wymagany jest profil z jawnym zatwierdzeniem i identyfikatorem podziału
treningowego. Tryb diagnostyczny używa tego samego generatora, zapisuje ostrzeżenie
i status diagnostyczny. Brak profilu bez `--diagnostic` zatrzymuje wykonanie.

## Wykonane sprawdzenia

- Punkt odniesienia przed zmianami: **30 testów OK**.
- Pełny zestaw po implementacji: **59 testów OK**: 30 dotychczasowych + 29 nowych.
- Testy są offline i używają sztucznych świec oraz katalogów tymczasowych.
- Zweryfikowano odtwarzanie i niezależność RNG, seedy, dokładnie 1440 losowań
  kroków na przykład, ekstrema ścieżki, kierunki trendów i rewersję konsolidacji.
- Sprawdzono kilkaset planów reżimów, wpływ konfiguracji i błędne parametry.
- Sprawdzono jawne granice kalibracji, brak wpływu cen spoza nich, pomijanie luk,
  zapis/odczyt profili, błędy zapisu i blokadę niezatwierdzonych kandydatów.
- Integracja weryfikuje round-trip CSV, odmowę nadpisywania, kolizje seedów,
  duplikaty OHLC, brak częściowych przykładów po błędzie oraz CLI/dry-run.
- Wykonano `pip install -e .` i uruchomiono zainstalowany nowy entry point.
- Wykonano dry-run starego entry pointu dla stycznia 2020: poprawny plan dwóch
  archiwów. Nie uruchamiano rzeczywistego pobierania z Internetu.
- `git diff --check`: bez błędów białych znaków.

W objętym testami zakresie nie stwierdzono regresji Binance. Dotychczasowe testy
obejmują porównanie wyników z zachowanym kontraktem oryginalnej implementacji.
SHA-256 wszystkich siedmiu istniejących plików processed/ (w tym `.gitkeep`)
pozostały bez zmian.

Odczyt dwóch pełnych historycznych CSV potwierdził po 14 975 świec,
zakres od 2020-01-01 00:00 do 2026-10-31 20:00 UTC i jedną lukę:
2020-02-19 12:00 UTC. Była to kontrola liczby/ciągłości, bez kalibracji cen.
Liczbę 82 pobranych archiwów na symbol podał autor zadania; w tym wdrożeniu
nie wykonywano ponownego audytu wszystkich źródłowych ZIP.

## Wykonana próbka diagnostyczna

Zapisano 5 BTC i 5 ETH, seed główny 20261103, łącznie 1200 świec i 14 400 kroków:

```text
data/synthetic/diagnostics/d8e42ba17ee731c070a50d6d/
  BTCUSDT/     5 CSV + 5 JSON
  ETHUSDT/     5 CSV + 5 JSON
  manifest.json
```

| Wynik | BTCUSDT | ETHUSDT |
| --- | --- | --- |
| Przyjęte serie | 5 | 5 |
| Świece w każdej serii | 120 | 120 |
| Średnia z odchyleń zwrotów close-close poszczególnych serii | 0,00985756 | 0,01268429 |
| Średnia z przeciętnych zakresów (High−Low)/Open poszczególnych serii | 0,01313181 | 0,01611151 |
| Liczby faz: wzrost / spadek / konsolidacja / wybicie | 2 / 1 / 3 / 2 | 3 / 3 / 6 / 0 |

Cała partia: 10 unikalnych seedów i hashy OHLC, zero odrzuconych przykładów,
zero błędów technicznych. Brak wybicia w małej próbce ETH jest dopuszczalnym
wynikiem losowania; testy pokrywają wszystkie fazy.

Powtórne wygenerowanie do katalogu tymczasowego dało **10/10 CSV identycznych
bajtowo**. Metadane były identyczne po usunięciu samej ścieżki wyjściowej.
Nie są to wyniki porównania z rzeczywistym rynkiem ani końcowe wyniki eksperymentu.

## Polecenia PowerShell

Z katalogu głównego projektu:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\market-levels-generate-synthetic.exe --diagnostic --count 5 --symbols BTCUSDT ETHUSDT --seed 20261103 --dry-run
.\.venv\Scripts\market-levels-generate-synthetic.exe --diagnostic --count 5 --symbols BTCUSDT ETHUSDT --seed 20261103 --output data/synthetic
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Powyższa partia już istnieje: ponowne uruchomienie generowania odmówi nadpisania.
Nowa, niewielka próbka z innym seedem:

```powershell
.\.venv\Scripts\market-levels-generate-synthetic.exe --diagnostic --count 5 --symbols BTCUSDT ETHUSDT --seed 20261104 --output data/synthetic
```

Alternatywnie ten sam interfejs przez
`.\.venv\Scripts\python.exe -m market_levels.cli.generate_synthetic`.

## Ograniczenia i następne decyzje

Przed docelową generacją należy zatwierdzić podział chronologiczny, skalibrować
oddzielnie BTC/ETH wyłącznie na treningu, sprawdzić statystyki i ręczne parametry
faz, obejrzeć reprezentatywne wykresy po wdrożeniu renderera, a następnie jawnie
zatwierdzić profile i liczebność zbioru.

Kontrola wizualna pozostaje niewykonana. Dwanaście kroków może zmieniać ekstrema
i proporcje knotów; normalny szum nie zapewnia grubych ogonów ani klastrów
zmienności. Nie narzucono automatycznych progów podobieństwa. Sprawdzono Windows
i Python 3.13.15, bez gwarancji zgodności między dowolnymi wersjami Pythona.
Atomowy zapis profili wymaga systemu plików obsługującego hard links.
Zapis do jednego output należy uruchamiać sekwencyjnie. Awaria zasilania może
pozostawić nieopublikowany katalog roboczy; obsługiwane wyjątki są sprzątane.

Ograniczenia publikacji danych pochodnych od Binance zachowano.
Nie opublikowano danych, nie utworzono obrazów, etykiet ani modeli.
