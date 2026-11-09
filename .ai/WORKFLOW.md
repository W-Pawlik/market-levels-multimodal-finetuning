# Sposób pracy i weryfikacji

## Przed zmianą

1. Przeczytaj AGENTS.md, instrukcje .ai i aktualne zadanie autora.
2. Sprawdź katalog roboczy, istniejące zmiany, właściwe źródła oraz dokumenty dotyczące zadania. Nie nadpisuj pracy autora.
3. Odróżnij stan działający od planowanego. Sprawdź konfigurację i faktycznie używane interfejsy.
4. Dla refaktoryzacji logiki zapisz punkt odniesienia: testy oraz deterministyczne wyniki. Jeśli dotykasz operacji na danych, zapisz SHA-256 istniejących plików poza katalogiem danych.
5. Zaplanuj najmniejszą spójną zmianę. Jeśli zadanie jest już jednoznacznie zlecone, realizuj je bez dodatkowej rundy potwierdzeń.

## Środowisko — Windows PowerShell

Polecenia wykonuj z głównego katalogu projektu. Jeśli środowisko już istnieje
i działa, korzystaj z niego zamiast tworzyć kolejne.

Jednorazowe przygotowanie:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Podstawowe sprawdzenie:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\market-levels-download.exe --start 2020-01 --end 2020-01 --dry-run
```

Równoważny CLI:

```powershell
.\.venv\Scripts\python.exe -m market_levels.cli.download --start 2020-01 --end 2020-01 --dry-run
```

Dry-run wczytuje konfigurację i pokazuje plan; nie pobiera ani nie zapisuje danych.
Nie potwierdza rzeczywistej dostępności serwera. Uruchomienie bez ograniczenia dat
i bez dry-run może pobrać cały zakres z JSON.

Generator syntetyczny (osobny proces, bez pobierania i automatycznej kalibracji):

```powershell
.\.venv\Scripts\market-levels-generate-synthetic.exe --diagnostic --count 5 --symbols BTCUSDT ETHUSDT --seed 20261103 --dry-run
.\.venv\Scripts\market-levels-generate-synthetic.exe --diagnostic --count 5 --symbols BTCUSDT ETHUSDT --seed 20261103 --output data/synthetic
```

`count` oznacza liczbę na instrument. Identyczne uruchomienie odmawia nadpisania;
do nowej próbki zmień seed, do odtworzenia wybierz nowy output. Nie zapisuj
syntetyków w processed/. Kalibracja wymaga jawnych granic, a kandydaci profilu
zatwierdzonego względem treningu. Szczegóły w
[SYNTHETIC_GENERATOR.md](../docs/SYNTHETIC_GENERATOR.md).

Podział `chronological_v1` jest zatwierdzony w `configs/experiment.json`.
Nowe CLI `market-levels-calibrate` i `market-levels-compare-synthetic` wymagają
jawnego okresu zawartego w treningu. Nie używaj walidacji/testu do dopasowania
generatora. Profile pozostają `unapproved`; porównanie jest opisowe z treningiem.
Pełna procedura PowerShell, w tym przechwycenie automatycznego run_id:
[SYNTHETIC_CALIBRATION_COMPARISON.md](../docs/SYNTHETIC_CALIBRATION_COMPARISON.md).

V1 pozostaje domyślny. V2 wymaga `--generator-version v2` i osobnego profilu
schematu 2; wariant wybiera `--v2-variant`. Kalibracja v2 też jest jawna, zawsze
treningowa i bez automatycznego approved. Nie używaj końcowych seedów diagnostyki
do przeszukiwania parametrów. `--reports` tworzy tabelę V1/V2, sprawdzając
identyczność rzeczywistych okien. Pełna procedura:
[SYNTHETIC_V2_POWERSHELL.md](../docs/SYNTHETIC_V2_POWERSHELL.md).

## W trakcie i po zmianie

Konfigurację czytaj przez shared.configuration.read_configuration, także przy
tworzeniu zmodyfikowanego pełnego JSON-a do testów. Bezpośredni json.loads wejścia
nie rozwija $file/$section. Pełne historyczne config.json nadal są obsługiwane.
Zmiana fragmentu unieważnia związany z nim preflight/checkpoint; nie aktualizuj
historycznych hashy. [Mapa konfiguracji](../configs/README.md).

Po reorganizacji src testy są pogrupowane według obszarów, a konstruktorów
fixture szukaj w tests/support. Podstawowe unittest discover nadal zbiera cały
zestaw. Granice importów sprawdza test_boundaries.py, a wzorzec sprzed zmian
test_behavior.py i test_rendering.py. Referencje wiążą się z wersjami środowiska;
pominięcia trzeba jawnie raportować. Nie aktualizuj automatycznie oczekiwań
w tests/fixtures/refactor_behavior.json w reakcji na regresję.
Wspólna publikacja jest w shared/publication.py, integralność w shared/integrity.py,
a weryfikacja zbioru w datasets/workflows/verification.py. Polecenia CLI są te same.
[Raport refaktoryzacji](../docs/refactoring/RAPORT_REFAKTORYZACJI_SRC.md).

Publikacja partii i raportów korzysta ze wspólnego publish_directory:
krótkie ponowienia konfliktów Windows, bez ponownego generowania. Pozostałości
stagingu są niekompletnym etapem; zabezpiecz je ręcznie poza przebiegiem dopiero
po sprawdzeniu ścieżek, nie usuwaj poprawnych danych i checkpointów.
Nie powtarzaj ukończonego SmokeTestu autora. [Raport](../docs/WINDOWS_PUBLICATION_RETRY_FIX.md).

Oddzielna próba 20261201/20261211 ma skrypt
`scripts/run_refinement_fresh_seeds.ps1` (CheckOnly/SmokeTest/RunFull/ResumeDirectory).
RunFull generuje cztery grupy na dwóch seedach, 960 nowych serii; jest do
osobnego uruchomienia przez autora. Nie łącz raportów automatycznie z trzema
starymi seedami i nie ponawiaj kalibracji. [Polecenia](../docs/FRESH_SEEDS_POWERSHELL.md).

Nowe przebiegi porównania mają krótką nazwę rc-<12 hex>, pełny UUID w run.json
i kontrolę długości plików Windows przed generowaniem. Do kontroli innej
lokalizacji użyj `-CheckOnly -OutputDirectory <nowa-krótka-ścieżka>`.
Szczegóły: [MAX_PATH](../docs/WINDOWS_REFINEMENT_PATH_FIX.md).

Do porównań po wykonanej kalibracji używaj oficjalnego
`scripts/run_refinement_comparison.ps1 -CheckOnly`, następnie `-SmokeTest`.
`-RunFull` jest dużym eksperymentem do osobnego świadomego uruchomienia autora.
`-ResumeDirectory` wznawia ten sam tryb po kontroli tożsamości i plików.
[Pełna procedura](../docs/INSTRUKCJA_POWERSHELL.md). Nie ponawiaj kalibracji
gotowych profili i nie używaj roboczego skryptu run_refinement_known_seeds.ps1.

Dostrojenie wyłącznie zmienności v2 ma osobny entry point
`market-levels-refine-v2-volatility` i sekcję konfiguracji
`volatility_refinement_v1`. Nie ponawiaj starej kalibracji w jej miejsce.
Profile źródłowe i wyniki pozostają bez zmian. Cztery kandydatury autora,
ponowne użycie raportów i rozdzielenie znanych/nowych seedów opisuje
[INSTRUKCJA_REFINEMENT_POWERSHELL.md](../docs/INSTRUKCJA_REFINEMENT_POWERSHELL.md).
Duże obliczenia tej iteracji są przeznaczone do osobnego uruchomienia przez autora.

- Zmieniaj źródła, nie kopie w build/ ani stary ZIP.
- Zachowuj pierwotne sześć przypadków testowych; importy można dostosowywać do świadomie zmienionej architektury.
- Dla zmiany logiki uruchom właściwe testy; przy zmianie pobierania, parsera, konfiguracji lub CLI uruchom pełny istniejący zestaw i odpowiedni dry-run.
- Dodawaj testy istotnych nowych zachowań i ryzyk regresji. Nie twórz testów odtwarzających wyłącznie implementację.
- Dla samych instrukcji i dokumentacji sprawdź poprawność treści, ścieżek, odnośników i zgodność z kodem; nie dodawaj testów aplikacji tylko z powodu edycji Markdown.
- Próbę prawdziwych archiwów wykonuj offline na kopiach w osobnym katalogu tymczasowym; katalog output musi zawierać własne raw/. Nie używaj oryginalnego data/ jako poligonu.
- Porównuj pełne CSV, raporty i manifesty. Normalizuj tylko rzeczywiście zmienne pola, np. czas utworzenia i ścieżkę katalogu tymczasowego.
- Gdy zadanie dotyczy ochrony danych, porównaj ich SHA-256 przed i po pracy.
- Nie naprawiaj cichym sposobem niepowiązanych problemów. Opisz je oddzielnie.

## Zamknięcie zadania

Ewaluator 3.6: `python -m market_levels.cli.evaluate evaluate|compare|verify`.
Główna metryka i konwencje są zamrożone w sr-eval-v1. W części 1 uruchomiono
wyłącznie ręczne fixture; nie twórz fikcyjnych predykcji dla produkcyjnego testu.
CLI domyślnie validation, jawny `--split test`; nie przyjmuje train.
Brakujące/nieznane/powtórzone ID blokują kompletny raport, odpowiedzi modelu
nie są naprawiane. Wyniki zapisuj do nowego results/evaluation lub diagnostics.
Nie uruchamiaj inferencji lub treningu na podstawie samego wdrożenia ewaluatora.
[Procedura](../docs/evaluation/INSTRUKCJA_POWERSHELL.md).

Aktualna produkcja 3.5 część 2: autor jawnie zatwierdził 800 przykładów i nowe
kopie profili 2026-11-07. `build_dataset approve/preflight/build/verify` rozdziela
decyzję, plan, produkcję i kontrolę. Gotowy zbiór jest pod
`data/datasets/ds35-800-20261107-a`; nowe approved pod
`data/synthetic/approved-ds35-20261107`. Nie ponawiaj budowy z tym samym seedem;
nowy preflight wykrywa zarezerwowany master seed także w data/datasets.
Do odtwarzania istniejącego zbioru użyj `verify --output <zbiór>`
(opcjonalnie `--check-sources`). Nie zmieniaj parametrów w reakcji na audyt.
Nie rozpoczynaj treningu, wyboru VLM ani rozszerzenia do 1600 bez nowego zlecenia.
[Aktualna instrukcja](../docs/datasets/INSTRUKCJA_POWERSHELL.md).

Etap 3.5, część 1: `python -m market_levels.cli.build_dataset preflight|smoke|verify`
z wymaganym `--output`. Wyłącznie nowe katalogi `results/diagnostics`.
`smoke` korzysta z pilotażu 3.3, nie generuje OHLC i zapisuje `split: null`.
Nie uruchamiaj produkcji 800 wykresów na podstawie ukończenia tej części.
Oba profile nadal `unapproved`. Liczebności są w `dataset_build.targets`.
Po testach `scripts/verify_dataset_stage.py` kontroluje źródła, małą próbę
i wcześniejsze 32 PNG/etykiety. [Pełna instrukcja](../docs/datasets/INSTRUKCJA_POWERSHELL.md).

Etykietowanie istniejącego pilotażu (3.4; nowy output wyłącznie pod results/diagnostics):

```powershell
.\.venv\Scripts\python.exe -m market_levels.cli.label_pilot --pilot results/diagnostics/dc-20261106-c/pilot --output results/diagnostics/sr-NOWY
.\.venv\Scripts\python.exe -m market_levels.cli.label_pilot --pilot results/diagnostics/dc-20261106-c/pilot --output results/diagnostics/sr-NOWY --verify --re-render
```

Nie uruchamia audytu ani generowania OHLC. Wyniki istniejące nie są nadpisywane.
Obrazy z liniami nie mogą być wejściem VLM. Pełna procedura i przenośna kontrola:
[etykietowanie PowerShell](../docs/labeling/INSTRUKCJA_POWERSHELL.md).

Audyt i pilotaż (bez generowania OHLC, nowy katalog diagnostyczny):

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[charts]"
.\scripts\run_chart_audit.ps1
.\.venv\Scripts\python.exe scripts/verify_chart_pilot.py results/diagnostics/<run>/pilot --re-render
```

Wyjście jest chronione przed nadpisaniem; ponowne odtworzenie wymaga nowego
katalogu. Skrypt nie uruchamia kalibracji ani generacji. Szczegóły i zakres
odczytu treningu: [instrukcja](../docs/charts/INSTRUKCJA_POWERSHELL.md).

Zaktualizuj CURRENT_STATE.md, README i architekturę tylko tam, gdzie zmienił się
faktyczny stan lub sposób użycia. Nie zmieniaj historycznych wyników testów tak,
jakby były nowymi wykonaniami.

W raporcie podaj: co zmieniono, dlaczego, co faktycznie sprawdzono, wynik i istotne
ograniczenia. Nie opisuj całej chronologii narzędzi. Wskazuj nowe polecenia,
jeśli zmieniono interfejs.

Paczki do innych sesji twórz na zlecenie. Dołączaj AGENTS.md, .ai/, kod, konfigurację,
testy i dokumentację; pomijaj lokalne dane, raporty, wagi, .venv, cache, build
i egg-info. Istniejący ZIP jest migawką i nie odświeża się sam.
