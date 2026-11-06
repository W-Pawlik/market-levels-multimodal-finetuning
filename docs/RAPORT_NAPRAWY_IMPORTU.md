# Naprawa importu i procedura porównania refinement

Odtworzono dokładnie `ModuleNotFoundError: No module named
'market_levels.data_processing.synthetic'`. W lokalnym projekcie brakowało
całego `src/market_levels/data_processing/synthetic/`, w tym `__init__.py`.
`find_spec()` zwracał None. Interpreter `.venv/Scripts/python.exe` ładował
`market_levels` z właściwego `src/market_levels/__init__.py`, a metadane editable
wskazywały ten projekt. Przyczyną był brak źródeł, nie katalog roboczy skryptu.
Nie ma dowodu, kto i kiedy usunął katalog ani czy przyczyną było kopiowanie.

Przywrócono wyłącznie 18 brakujących plików pakietu z ostatniej kompletnej
migawki `market-levels-handoff-2026-11-05-refinement-audit-portability-fix.zip`.
Sprawdzono CRC ZIP i SHA-256 każdego pliku według FILES_SHA256.txt. Nie zastąpiono
żadnego istniejącego pliku. Zachowano refinement i porównywanie audytu z tolerancją.
Nie cofano kodu do starszego HEAD. To jednorazowe odzyskanie brakujących źródeł,
nie używanie historycznych paczek jako bieżącego źródła projektu.

Po przywróceniu działają importy i `--help` obu istniejących CLI, także ich
launchery `.exe`. Instalacja editable była prawidłowa. Setuptools udostępnia
zarazem dist-info w środowisku i lokalny src/*.egg-info; nie jest to druga
instalacja. Preflight odrzuca obce pochodzenie importów i dodatkowe instalacje.

## Oficjalny skrypt

`scripts/run_refinement_comparison.ps1` wyznacza projekt przez PSScriptRoot,
wybiera jego interpreter `.venv` i wywołuje
`python -I -X utf8 -m market_levels.cli.refinement_comparison`.
Nie dopisuje niczego do sys.path/PYTHONPATH. -I wyłącza wpływ katalogu terminala
i zmiennych Pythona; instalacja editable jest wymagana. -X utf8 ustala kodowanie
logów również na Windows; samo PYTHONIOENCODING nie działa przy -I.

Moduł koordynujący korzysta z dotychczasowych CLI generowania i porównania
przez ich oficjalne odpowiedniki `python -m`. Do kontroli wyników wykorzystuje
istniejące walidatory, selekcję, build_comparison i agregator. Nie implementuje
ponownie statystyki OHLC ani generatora. Stary, roboczy skrypt autora pozostawiono
bez zmian; do kolejnych uruchomień używać wyłącznie oficjalnego skryptu.

CheckOnly czyta wszystkie wejścia, importy i wersje, sprawdza chronological_v1,
cztery profile, ich źródła/SHA/warianty/statusy i reżimy oraz 12 historycznych
raportów z trzech seedów. Sprawdza hashe raportów, duplikaty, profile źródłowe,
referencję 60 okien i ponawia wyłącznie deterministyczną selekcję tych okien.
Nie generuje danych i nie tworzy katalogu eksperymentu.

SmokeTest generuje tylko dwa nowe warianty, po 2 BTC i 2 ETH, seed 20261107:
8 serii, dwa manifesty i cztery raporty. Nie tworzy zbiorczej tabeli ze starymi
count=60, bo liczności i okna byłyby nieporównywalne.

RunFull jest wyłącznie gotowy do osobnego uruchomienia przez autora. Powstanie
720 nowych serii: 2 warianty × 3 seedy × 2 symbole × 60. Wszystkie stare raporty
V1/full-original są ponownie używane. Zbiorcze tabele mają cztery grupy,
rozróżniane przez metadane i hashe, nie nazwy folderów.

## Wznowienie i bezpieczeństwo

Nowy przebieg wymaga nieistniejącego katalogu; domyślna nazwa zawiera UUID.
run.json przypina wejścia, SHA konfiguracji, kodu, profili, raportów i CSV oraz
interpreter. Wznowienie wymaga jawnego katalogu i identycznego trybu/pochodzenia.
completed/*.json indeksuje pliki i ich SHA po zweryfikowaniu etapu.
Blokada systemowa running.lock wyklucza równoczesne wznowienie i jest zwalniana
przez system po zakończeniu lub zabiciu procesu; obecność pliku nie oznacza blokady.

Opublikowana partia bez checkpointu jest odzyskiwana po sprawdzeniu pełnej
konfiguracji, seedów, liczności, profili, manifestu i wszystkich CSV/metadanych.
Poprawne partie nie są generowane ponownie. Raporty są porównywane z wynikiem
istniejącego build_comparison. JSON i Markdown muszą istnieć razem. Niezgodność,
częściowy katalog bez manifestu albo uszkodzony checkpoint zatrzymują procedurę;
nic nie jest automatycznie usuwane ani nadpisywane. W takim przypadku zachować
wyniki i zbadać przyczynę, ewentualnie rozpocząć osobny nowy przebieg.

Każda próba CLI ma nowy log z pełnym stdout/stderr, zapisywany podczas działania.
Błąd koordynatora ma osobny error-*.log; preflight — log stderr w katalogu temp,
którego ścieżkę wskazuje PowerShell. PowerShell 5.1 nie przerywa przechwytywania
tracebacku na pierwszym NativeCommandError. Kod zakończenia jest zawsze sprawdzany.

Nie zmieniano kalibracji, matematyki, profili, podziału ani historycznych raportów.
Wyniki testów i kontroli ochrony danych są w RAPORT_TESTOW.md i logach handoffu.
