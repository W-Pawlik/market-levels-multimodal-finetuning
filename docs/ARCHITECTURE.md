# Architektura Market Levels

Stan po reorganizacji z 2026-11-08. Jest to jeden pakiet badawczy market_levels
w układzie src. Działają dane, generatory, wykresy, etykietowanie, zbiory
oraz ewaluacja zapisanych odpowiedzi. Modeling, trening i inferencja są planowane.

[Raport refaktoryzacji](refactoring/RAPORT_REFAKTORYZACJI_SRC.md),
[pierwotny plan](PLAN_REFAKTORYZACJI_SRC.md),
[mapa przeniesionych symboli](refactoring/SYMBOL_MAP.json).

## Jak odnaleźć kod

| Obszar | Odpowiedzialność | Mapa plików |
| --- | --- | --- |
| core/ | Model OHLC, walidacja, czas, statystyki i ATR. | [README](../src/market_levels/core/README.md) |
| shared/ | Integralność, ścieżki, manifesty, JSON i publikacja. | [README](../src/market_levels/shared/README.md) |
| data_processing/real/ | Binance: HTTP, archiwa, parser i pobieranie. | [README](../src/market_levels/data_processing/README.md) |
| data_processing/windows/ | Okna, odrębne selekcje i treningowy czytnik CSV. | [README](../src/market_levels/data_processing/windows/README.md) |
| data_processing/synthetic/ | Generowanie v1/v2, profile, kalibracja i porównania. | [README](../src/market_levels/data_processing/synthetic/README.md) |
| charts/ | Metryki, dobór pilotażu, renderer i odczyt pilotażu. | [README](../src/market_levels/charts/README.md) |
| labeling/ | Algorytm S/R, modele wyniku, nakładki i pilotaż. | [README](../src/market_levels/labeling/README.md) |
| datasets/ | Approval, plan, produkcja, próba, audyt i odtworzenie. | [README](../src/market_levels/datasets/README.md) |
| evaluation/ | Ścisły JSON, matching, metryki i sparowane raporty. | [README](../src/market_levels/evaluation/README.md) |
| experiments/refinement/ | Istniejący runner, preflight, checkpointy i wznowienie. | [README](../src/market_levels/experiments/README.md) |
| cli/ | Dotychczasowe polecenia, argumenty, komunikaty i błędy. | [Entry pointy](../pyproject.toml) |

W obszarach powtarzają się role:

- domain/: modele, algorytmy, deterministyczne transformacje i walidacja;
- workflows/: koordynacja konkretnego przypadku użycia;
- io/: odczyt i zapis formatów właściwych obszarowi;
- reporting/: prezentacja gotowych wyników;
- config/ lub config.py: rzeczywiste ustawienia i ich walidacja.

Katalogi grupują istniejące odpowiedzialności. Nie tworzymy pustych warstw,
klas Service/Repository/Factory ani globalnego katalogu zmiennych i utils.py.
Małe spójne moduły, np. evaluation/protocol.py, pozostają osobnymi plikami.

## Zależności

CLI wywołuje workflow. Workflow składa konfigurację, algorytmy, I/O i raporty.
Domain nie importuje workflow, adapterów I/O ani CLI. Core i shared zależą
od własnych modułów i biblioteki standardowej. Graf importów, także importów
wewnątrz funkcji, nie zawiera cykli. Granice sprawdzają
[testy architektury](../tests/unit/architecture/test_boundaries.py).

Pozostają jawne zależności między obszarami: datasets używa generatora,
renderera i etykietowania, a evaluation wspólnego ATR i formatu przykładu.
Funkcje techniczne nie wymagają importowania procesów pilotażowych.
Obliczenia można importować bez Matplotlib; renderer ładuje tę bibliotekę lokalnie.

Pakiet labeling eksportuje LabelResult i label_window; data_processing.windows
udostępnia Window, candidates, coverage, validate_selection i select_training.
Inicjalizatory pakietów nie zawierają algorytmów. Importy wewnętrzne są względne,
bez modyfikowania sys.path.

## Dane rzeczywiste i publikacja

Adapter real/binance_vision zachowuje client / archives / parsing.
Koordynator jest w real/workflows/download.py; configuration.py nadal ładuje
konfigurację pobierania. Przepływ: konfiguracja i CLI → archiwa i CHECKSUM
→ parser ZIP → walidacja okresu i OHLC → CSV → raport → manifest.
Strict-gaps nadal przerywa po CSV i raporcie, przed nowym manifestem.
Fallback dzienny zachowuje poprzednie warunki i ostatni zakończony miesiąc.
Nie interpolujemy luk.

Candle zachowuje Decimal, UTC, 4h i wymagane source_archive. CSV ma nagłówek
open_time_utc,open,high,low,close. Osobny czytnik treningowy kończy na pierwszym
późniejszym znaczniku czasu, bez analizowania OHLC validation/test.
SHA źródła może obejmować cały plik.

shared/publication.py zachowuje atomowy rename, cztery próby konfliktów dostępu
oraz opóźnienia 0.05/0.15/0.30 s. Nie powtarza generowania zawartości.
Sprzątanie nie zastępuje pierwotnego błędu; po sukcesie wyczerpana blokada jest
ostrzeżeniem. Zachowano logger market_levels.data_processing.staging.
Zapis profilu nadal używa hard linku bez nadpisywania.

shared/manifests.py obsługuje istniejący format zapieczętowanego katalogu.
Manifesty pobierania, generatora i pilotażu zachowują odrębne formaty.
Hash pliku, kanoniczny hash cen, hash profilu i fingerprint ewaluacji mają
różne wejścia i kodowania. Podobnie osobne pozostają JSON raportów, etykiet,
kanonizacja profilu i ścisły Decimal JSON protokołu ewaluacji.

## Generowanie i okna

synthetic/domain/generation zawiera niezależne v1/v2, fazy, procesy
stochastyczne, seedy i dispatch. Wersje, strumienie RNG i kolejność losowania
pozostają niezmienione. Domyślny jest v1. V2 ma base, bridge, tails,
volatility, full i bridge_volatility.

Profile są w domain/profiles. Walidacja profilu i audytu jest oddzielona od
uruchamiania symulacji. Ustawienia wyszukiwania są w config, cechy i cele
w domain, a wykonanie kalibracji/refinement w workflows. Audyt odtwarza cel
bez generatora. Kalibracja jest jawna, treningowa i nie zatwierdza profilu.
Partia zachowuje kontrolę seedów, duplikatów i round-trip CSV oraz atomową
publikację; bez cichego ponawiania losowania. data/processed jest chronione
również przy uruchomieniu z innego katalogu.

Trzy reguły selekcji pozostają odrębne:

- diagnostyka generatora: pojemności ciągłych odcinków i rozłączne pozycje;
- produkcja: kandydaci chronologiczni, warstwy train, prefiks validation/test;
- pilotaż: pokrycie kategorii z deterministycznym rozstrzyganiem remisów.

Statystyki szeregu i metryki wykresu zachowują różnice konwersji Decimal/float
oraz traktowania świec o zerowym zakresie. Nie zastępujemy jednego drugim.
Matematyka: [v1](SYNTHETIC_GENERATOR.md), [v2](SYNTHETIC_GENERATOR_V2.md),
[refinement](RAPORT_REFINEMENT_V2.md).

## Wykresy i etykietowanie

charts/io/rendering.py zachowuje Agg, 1024 × 768, fonty, kolory, kolejność
rysowania i metadane PNG. Domain zawiera metryki i selekcję, io/pilot.py
czyta istniejący pilotaż 32 okien. labeling/io/overlays.py rysuje osobne
nakładki diagnostyczne; obrazy z liniami nie są wejściem modelu.

labeling/domain/algorithm.py zachowuje ścisłe ekstrema 3+3, Wilder ATR(14),
grupowanie przy 0.5 ATR, medianę przed filtrowaniem i minimum dwie reakcje
oddalone o pięć świec. Najpierw wybiera najsilniejsze ekstremum i usuwa
bliskich sąsiadów. Ranking, remisy, klasyfikacja względem ostatniego Close
oraz limit trzech poziomów pozostają bez zmian. Kontekst Decimal ma 50 cyfr.
ROUND_HALF_UP do centów dotyczy serializacji; kolizje również między stronami
rozstrzyga ranking. Nie zastępujemy reguły maksymalizowaniem liczby reakcji.

## Zbiory i ewaluacja

datasets/workflows rozdziela approval, plan, smoke, produkcję, verify i review.
Domain/examples.py definiuje instrukcję, ID, metadane i dokładny liczbowy JSONL;
diagnostyka jawnie ma split: null. Liczebności pochodzą z dataset_build.targets.
Syntetyki trafiają tylko do train. Selekcja nie ocenia etykiet ani nie zmienia
parametrów; audyt jest opisowy. Weryfikator niezależnie kontroluje kompletność,
pochodzenie, hashe oraz odtwarza obrazy, etykiety i syntetyczne OHLC.

evaluation/protocol.py zachowuje sr-eval-v1, hash reguł i własny JSON z Decimal.
Parser odrzuca błędne odpowiedzi bez naprawy. Matching maksymalizuje TP,
minimalizuje sumę błędów i rozstrzyga remisy indeksami. Agregacja zachowuje
micro-P/R/F1, MAE i reguły pustych odpowiedzi. Domyślny jest validation,
test wymaga wskazania, a train jest odrzucany. Brakujące, nieznane i powtórzone
ID blokują raport. Porównanie wymaga tych samych referencji, modelu, instrukcji
i ustawień inferencji. Ewaluator nie uruchamia inferencji.

Instrukcje: [zbiory](datasets/INSTRUKCJA_POWERSHELL.md),
[format](datasets/FORMAT.md), [ewaluacja](evaluation/PROTOKOL_3_6.md).

## Runner, pakiet i rozwój

experiments/refinement zawiera istniejący preflight, plan, MAX_PATH, subprocess,
blokadę, checkpointy, wykonanie i raporty. CLI zachowuje ścieżkę i argumenty.
Stare i świeże seedy nie są automatycznie łączone. Wznowienie nadal wymaga
zgodności SHA kodu Python i wejść; historycznych run.json nie przepisujemy.
Kontrola środowiska sprawdza też importowalność istniejących CLI; nie jest to
zależność modułów algorytmicznych od warstwy CLI.

Setuptools odkrywa market_levels* w src. Entry pointy z pyproject.toml
oraz python -m market_levels.cli.* są zachowane. Zależności nie zmieniły się:
biblioteka standardowa i opcjonalne [charts]. Konfiguracja pozostaje
w configs/experiment.json i jawnie wskazanych fragmentach. Shared.configuration
składa pola główne przez $file/$section, bez dziedziczenia lub scalania ustawień.
Pełne JSON-y nadal działają. CLI ma pierwszeństwo; ścieżki danych pozostają
względem CWD, a wyłącznie $file względem pliku wejściowego.
Nowe snapshoty zbiorów są samodzielne, a SourceLedger i preflight runnera
przypinają wszystkie pliki konfiguracji. [Mapa sekcji](../configs/README.md).
Nie przywrócono usuniętych src.download_data, src.validate_data ani src/__init__.py.

data/ i results/ przechowują artefakty. Build, egg-info, cache i handoff nie są
źródłem aktywnej implementacji. Parametry i decyzje pozostają w
[konfiguracji](../configs/experiment.json) i [decyzjach autora](DECYZJE_3_3.md).
Model, trening i inferencja wymagają osobnych zleceń.
