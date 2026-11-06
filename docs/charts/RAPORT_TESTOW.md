# Testy audytu i renderera — 2026-11-06

Wykonano natywnie na Windows, CPython 3.13.15, Matplotlib 3.11.2, backend Agg.
Nie deklaruje się wykonania na innych wersjach Pythona, platformach ani fontach.

## Wyniki

| Sprawdzenie | Wynik |
|---|---|
| Stan przed zmianą: `python -m unittest discover -s tests` | 151 testów OK, 78.031 s |
| Nowe testy: `python -m unittest discover -s tests -p 'test_chart*.py' -v` | 18 testów OK, 10.701 s |
| Pełny końcowy zestaw: `python -m unittest discover -s tests -v` | **169 testów OK, 94.797 s** |
| `scripts/run_chart_audit.ps1 -OutputDirectory results/diagnostics/dc-20261106-c` | 600 istniejących syntetyków, 32 PNG, 0 błędów, 0 duplikatów |
| `scripts/verify_chart_pilot.py .../pilot --re-render` | Wszystkie 32 PNG: 1024 × 768, SHA i JSON zgodne; odtworzone bajty identyczne |
| Dwa niezależne wykonania końcowego pilotażu z tym samym seedem | Wszystkie 32 pliki PNG identyczne |
| Ponowna instalacja editable i `market-levels-audit-charts.exe --help` | OK, nowy entry point dostępny |
| CLI pobierania `--start 2020-01 --end 2020-01 --dry-run` | OK, plan 2 archiwów, bez pobierania i zapisu danych |

## Zakres nowych testów

- Dokładnie 120 świec, UTC i kolejność, odrzucenie duplikatów czasu i luk.
- Odrzucenie niepoprawnego OHLC, NaN, Infinity, cen niedodatnich i błędnych czasów.
- PNG 1024 × 768; oryginalne współrzędne cen i kolejność 120 korpusów/knotów.
- Brak linii S/R i siatki; teksty obrazu ograniczone do generycznych osi i liczb.
- Zmiana source_archive i dat symulacji nie zmienia pikseli; brak ID także w PNG info.
- Powtarzalność bajtowa renderowania oraz odmowa nadpisania bez zmiany starego pliku.
- Metryki policzone na ręcznie zdefiniowanej ścieżce, proporcje korpusów/knotów,
  przypadek całkowicie płaski, rozkłady długości, przejścia i udziały świec.
- Wybór deterministyczny niezależnie od kolejności wejść, zależny od zapisanego
  seeda; odrzucenie powtórzonych OHLC w puli selekcji.
- Czytanie treningu kończy się przed konwersją OHLC po treningu (wartości
  `NO_ACCESS`/`FORBIDDEN` po granicy); rzeczywiste okna nie przecinają luk.
- Seed, wariant, hash profilu/OHLC, reżimy, status i brakujące pliki w manifestach.
  Test jednostkowy tożsamości izoluje walidator profilu; jego pełne reguły są
  objęte istniejącą regresją refinement, a natywny audyt używa prawdziwego walidatora.
- Brakujące syntetyki: integracyjny audyt na sztucznym treningu opisuje brak
  pięciu seedów i mniejszy pilotaż, bez wywołania generatorów. Metadane i kopie
  120 świec pozwalają powiązać każdy obraz z oknem, a źródło pozostaje bez zmian.
- Kolizje katalogów, MAX_PATH i ochronę katalogu danych sprawdza nowy zestaw;
  rzeczywiste blokady i ponowienia publikacji Windows obejmuje istniejący zestaw
  staging. Nie tworzono nowej implementacji obsługi blokad.

## Ochrona źródeł i ograniczenia

Audyt kontroluje SHA-256 1259 odczytanych wejść przed/po i potwierdza brak zmian.
Dodatkowa migawka obejmuje wszystkie 8915 istniejących plików `data/`, w tym
cztery profile refined: **0 zmienionych/usuniętych i 0 nowych plików w data/**.
Jej wynik jest dołączony jako
`source-baseline-verification.json`; bazowa mapa hashy jako
`audit-source-baseline.json`. Kontrola bajtowa pełnych CSV nie jest analizą
validation/test; konwersja OHLC, progi i dobór okien dotyczą wyłącznie treningu.

Pełny log wykonania jest lokalnie w
`results/diagnostics/charts-full-tests.log`, a w handoffie w `evidence/`.
Ostateczny komplet raportów i obrazów:
`results/diagnostics/dc-20261106-c/`. Wcześniejsze katalogi `-a` i `-b` pozostawiono;
nie są źródłami końcowego audytu ani zawartością paczki.

Obejrzano 4 reprezentatywne obrazy (obie grupy i oba symbole). Integralność
i powtarzalność sprawdzono dla wszystkich 32. Nie wykonano oceny przez model
ani końcowej akceptacji wzrokowej przez autora. Nie pobierano danych, nie
kalibrowano rynku, nie uruchamiano dużej generacji ani treningu AI.
