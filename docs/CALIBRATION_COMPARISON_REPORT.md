# Raport wdrożenia kalibracji CLI i porównania z treningiem

Weryfikacja: Windows, CPython 3.13.15. Przed zmianami: **59 testów OK**.
Po zmianach: **77 testów OK** (59 dotychczasowych + 18 nowych).

## Wykonane

Zapisano zatwierdzony podział `chronological_v1` w konfiguracji. Trening
2020–2023, walidacja 2024, test 2025–2026-10; granice otwarcia świec UTC włącznie.
Loader sprawdza status, format, UTC, granice 4h oraz rozłączność i kolejność
okresów. Daty wykonawcze są wyłącznie w JSON, a nie w kilku modułach kodu.
Nie zmieniono zatwierdzonych liczebności, udziałów ani przesunięć eksperymentu.

Dodano entry pointy `market-levels-calibrate` i `market-levels-compare-synthetic`.
Kalibracja wymaga jawnych granic wewnątrz treningu, korzysta z `calibrate_csv`
i `save_profile`, nie zatwierdza profilu i odmawia nadpisania. Porównanie czyta
faktyczne CSV z manifestu, sprawdza pochodzenie, hash, techniczną walidację
i zgodność statystyk z metadanymi, a potem tworzy raport JSON i tabelę Markdown.
Zapis obu raportów jest atomowy na poziomie katalogu, bez nadpisania.

## Pliki

`+` nowy, `~` zmieniony w tym zadaniu (względem stanu po generatorze).

```text
~ .ai/CURRENT_STATE.md
~ .ai/WORKFLOW.md
~ README.md
~ configs/experiment.json
~ pyproject.toml
docs/
  ~ ARCHITECTURE.md
  ~ DECYZJE_3_3.md
  ~ SYNTHETIC_GENERATOR.md
  ~ SYNTHETIC_IMPLEMENTATION_REPORT.md   uwaga o późniejszym zatwierdzeniu podziału
  + SYNTHETIC_CALIBRATION_COMPARISON.md
  + CALIBRATION_COMPARISON_REPORT.md
src/market_levels/
  cli/
    + calibrate_synthetic.py
    + compare_synthetic.py
  data_processing/
    pipelines/
      + compare_synthetic.py
    synthetic/
      ~ quality.py
      ~ README.md
      + training_period.py
      + selection.py
      + comparison.py
tests/
  unit/
    + test_synthetic_comparison.py
  integration/
    + test_synthetic_diagnostics.py
```

## Wykorzystane komponenty i poprawność obliczeń

Nie przepisano kalibracji: wykorzystano istniejące `calibrate_csv`,
`validate_period`, `save_profile`, `validate_profile` i `profile_hash`.
Użyto `read_candles_csv`, `write_json`, `validate_values`, `validate_synthetic`,
`canonical_hash`, `series_statistics` i `distribution`.

Jedyna techniczna zmiana dotychczasowych obliczeń w quality.py to udostępnienie
surowych obserwacji przez `series_observations`. Starsza funkcja statystyk używa
tego samego wspólnego kodu. Wzory i jej format wynikowy nie uległy zmianie.
Pozwala to agregować faktyczne obserwacje bez duplikowania definicji i bez
uśredniania kwantyli. Na starych dziesięciu lokalnych przykładach potwierdzono
identyczność ponownie obliczonych statystyk z zapisanymi wcześniej metadanymi.

Selekcja przecina trening przy lukach, oblicza pojemność odcinków i losuje
wykonalny przydział liczby okien. Następnie losuje rozłączne pozycje w odcinkach
z osobnym seedem. Jest deterministyczna, niezależna od etykiet, obejmuje cały
dozwolony okres i nie ma problemu przypadkowej porażki wyboru zachłannego.
Nie jest jednostajnym losowaniem wszystkich zestawów okien; dokładny algorytm
i jego ograniczenia są opisane w instrukcji procesu.

Raport odróżnia połączone obserwacje wewnątrz okien od rozkładów parametrów całych
okien. Zwroty i pary korelacyjne nie przechodzą między oknami ani przez luki.
Korelacja lag 1 abs(r) używa Pearsona na dozwolonych parach; niedostateczna
liczba par i zerowa wariancja dają null z przyczyną. Nie ma sztucznych zer.

Metryki: zwroty logarytmiczne i ich moduły, względne zakresy świec, korpusy,
proporcje korpusu oraz obu knotów, zmienność między oknami, zmiana Open→Close
całego okna, jego względna rozpiętość, korelacja abs(r) lag 1, wystąpienia i udział
świec reżimów oraz liczba faz na syntetyczny przykład. Każdy rozkład ma średnią,
próbne std, min/max i kwantyle 1/5/50/95/99%. Różnice to signed S−R, bez
mylących procentów i automatycznej decyzji o akceptacji generatora.

## Weryfikacja

- Pełne `unittest discover -s tests -v`: 77 testów OK; wszystkie 59 wcześniejszych zachowano.
- Nowe testy pokrywają oba symbole i CLI, granice treningu, UTC, odrzucanie
  walidacji/testu, status unapproved, dry-run, kolizje i wpływ cen spoza treningu.
- Testy selekcji sprawdzają 120 świec, luki, rozłączność, maksymalną pojemność,
  reprodukcję, różne seedy, ograniczenie do treningu oraz wybór 60 na sztucznym
  szeregu długości odpowiadającej rzeczywistemu treningowi.
- Statystyki sprawdzono na znanych przykładach: kwantyle z obserwacji, zwroty
  bez przejść między oknami, knoty, korelacje ±1 i przypadki nieokreślone.
- Raport sprawdzono pod kątem reprodukcji, zgodności JSON, pochodzenia, profilu,
  błędnego symbolu/liczby przykładów, uszkodzonych manifestów/metadanych,
  brakujących plików, ścieżek poza partią i błędów zapisu.
- Wykonano `pip install -e .` i pełny przebieg **udokumentowanych poleceń
  PowerShell** przez zainstalowane entry pointy na danych sztucznych: dry-runy,
  dwa profile, generowanie 2 BTC + 2 ETH, dwa porównania, przechwycenie ścieżek.
  Sprawdzono także kompatybilność tabeli terminalowej z kodowaniem cp1250.
- Lokalna kontrola historycznych CSV potwierdziła po **8765/2196/4014** świec,
  razem 14 975 dla BTC i ETH. Sama selekcja treningu wybrała po **60** ciągłych,
  rozłącznych okien; maksimum **72**. Luka została poprawnie rozpoznana.

Nie zmieniono plików generator.py, regimes.py, istniejącego pipeline generowania
ani CLI pobierania i generowania. Potwierdzono SHA-256 tych plików oraz wszystkich
wcześniejszych plików processed/ i synthetic/ względem początku zadania.
Nie pobierano danych z sieci, nie modyfikowano próbek ani danych historycznych.
Brak stwierdzonej regresji w objętym testami zakresie. Nie utworzono commita.

## Uruchomienie i ograniczenia

Kompletna instrukcja PowerShell, z dry-run przed zapisem, kalibracją obu symboli,
generowaniem 60+60 ze seedem 20261105, wyborem okien ze seedem 20261106,
przechwyceniem automatycznej ścieżki manifestu i odszukaniem raportów:
[SYNTHETIC_CALIBRATION_COMPARISON.md](SYNTHETIC_CALIBRATION_COMPARISON.md#powershell-kompletny-przebieg).

Profile powstaną w `data/synthetic/calibration/*_train_2020_2023_unapproved.json`.
Próbka: `data/synthetic/diagnostics/<run_id>/`. Porównania:
`data/synthetic/comparisons/<comparison_id>/<symbol>_comparison.json` oraz
`<symbol>_summary.md`. Do dalszej oceny wystarczą początkowo dwa JSON i dwa Markdown.

**Nie uruchomiono rzeczywistej kalibracji ani pełnego generowania 60+60**;
to właściwe uruchomienie pozostawiono autorowi zgodnie z zadaniem. Nie ma nowych
empirycznych profili ani wyników porównania rynku do zatwierdzenia w tej sesji.
Trening jest referencją użytą także do kalibracji, więc proces nie stanowi
niezależnej walidacji na niewidzianych danych. Nie dostrajano parametrów generatora.

Nadal wymagane są: uruchomienie procesu przez autora, analiza różnic, ocena
parametrów projektowych, późniejsza kontrola wizualna po wdrożeniu renderera
i osobna decyzja o zatwierdzeniu profili. Podział jest już zatwierdzony.
Nie wygenerowano docelowych 440 przykładów. Zachowano ograniczenia licencyjne.
Weryfikacja dotyczy Windows i Pythona 3.13.15. Ścisłe porównanie zapisanych
statystyk nie gwarantuje zgodności między dowolnymi platformami i wersjami Pythona.
