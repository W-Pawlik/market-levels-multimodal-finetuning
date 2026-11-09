# Refaktoryzacja src — wykonanie i kontrola zgodności

Data: 2026-11-08. Wykonano plan zlecony przez autora. Zmiany dotyczą organizacji
kodu, współdzielenia zgodnych operacji technicznych, testów i dokumentacji.
Nie zmieniono parametrów eksperymentu, wersji algorytmów, protokołu ani rendererów.

**W wykonanych kontrolach nie wykryto zmiany wyników algorytmów ani renderowania.**
Istniejące dane i wyniki zachowały identyczny inwentarz oraz bajty.

## Zmiany

- Wydzielono core: OHLC, walidację, tożsamość cen, czas, liczby, statystyki i ATR.
- Wydzielono shared: SHA plików, SourceLedger, ścieżki, publikację, manifesty i JSON.
- W obszarach zastosowano domain / workflows / io / reporting / config,
  zgodnie z rzeczywistymi odpowiedzialnościami.
- Rozdzielono generowanie, profile, cele i wykonanie kalibracji/refinement.
  Zlikwidowano cykle importów, również zależności przez importy lokalne.
- Rozdzielono metryki, odczyt pilotażu, renderer, nakładki i etykietowanie.
- Rozdzielono planowanie, produkcję, próby, odtworzenie i audyt zbiorów.
- Ewaluacja korzysta z jawnych modułów wejściowych, matching/scoring i raportów,
  bez technicznych zależności od dawnych packaging/pilot/diversity.
- Runner trafił do experiments/refinement. Jego CLI ma tylko parser i delegację.
- Testy pogrupowano według obszarów; wspólne konstruktory są w tests/support.
  Oryginalne testy nie importują już innych plików test_*.py jako bibliotek fixture.

Kod ma 156 plików Python, w tym 47 inicjalizatorów i 109 modułów z implementacją;
wcześniej 67, w tym 13 inicjalizatorów. Źródła mają 7297 linii wobec 6689.
Więcej małych modułów oznacza również dodatkowe importy i inicjalizatory.
Największy plik ma 255 linii wobec wcześniejszych 545. Nie wprowadzono frameworka
ani nowych zależności aplikacji. Pyproject i konfiguracje badawcze są niezmienione.

[Aktualna architektura](../ARCHITECTURE.md),
[mapa przeniesionych definicji](SYMBOL_MAP.json),
[wyniki kontroli w JSON](VALIDATION.json).

## Kontrola zachowania

Punkt odniesienia stanowiła kopia źródeł sprzed pierwszego przeniesienia,
z rewizji 092059aa5dd49e260b762cc6ccc0c660acebc166. Źródła i inwentarz danych
zabezpieczono poza katalogami danych. Porównania starego i nowego kodu uruchamiano
w osobnych procesach z kontrolą pochodzenia importowanego pakietu.

| Kontrola | Faktyczny wynik |
| --- | --- |
| Testy | **286 OK, 0 błędów, 0 pominięć**, 137.150 s. Zachowano wszystkie 277 dotychczasowych przypadków, dodano 9. Pełne zestawy przechodziły też po kolejnych etapach przenosin. |
| Macierz generatorów | **28 identycznych przypadków**: BTC/ETH, dwa master seedy, v1 i sześć wariantów v2. Dokładne OHLC, metadane, etykiety, diagnostyka, metryki, CSV, PNG i nakładki. Bez tolerancji liczbowej i normalizacji obrazów. |
| Kalibracja/refinement | Pełne wyniki małej sztucznej referencji identyczne ze starą implementacją: profile, próby, cechy, cele, parametry i audyty. Osobno identyczna selekcja okien. Bez kalibracji rynku. |
| Serializacja | **56 identycznych linii JSONL** diagnostyki i produkcji ze starym kodem, z zachowaniem liczbowego JSON etykiety i nowych linii. |
| Historyczny pilotaż | **32 oryginalne PNG i 32 nakładki** odtworzone z identycznym SHA; etykiety, diagnostyka i pochodzenie zgodne. |
| Produkcyjny zbiór | **800 PNG i etykiet oraz 440 syntetyków odtworzone**, 0 różnic renderera. Liczebności 698/36/66; źródłowe CSV i przypięte źródła sprawdzone. Weryfikacja istniejącego zbioru, bez ponownej produkcji. |
| Pobieranie offline | Prawdziwy ZIP stycznia 2020 i CHECKSUM skopiowano do dwóch katalogów tymczasowych. CSV bajtowo zgodny, komplet pól raportów i manifestu zgodny, stdout/stderr identyczne. Normalizowano tylko ścieżkę output i created_at_utc. |
| CLI | **10 identycznych kontraktów --help**; parser i wydzielona obsługa cyklu runnera zgodne strukturalnie z oryginałem. Wszystkie entry pointy zachowane. |
| Ochrona danych | **12 771 plików przed i po**, brak dodanych, usuniętych i zmienionych plików w data/results; identyczne SHA-256. |
| Zależności | Brak cykli importów, także lokalnych; testy granic core/shared/domain/CLI oraz importu algorytmów bez Matplotlib przechodzą. |
| Pakiet | Wheel zbudowany z osobnej kopii źródeł i zainstalowany w świeżym venv bez Matplotlib. Działają importy algorytmów i **9 zainstalowanych poleceń --help**. |

Wzorzec 28 przypadków powstał ze starego kodu, a nie z nowej implementacji.
Jest zachowany w [refactor_behavior.json](../../tests/fixtures/refactor_behavior.json)
i chroniony testami. Oryginalnych fixture regresyjnych nie aktualizowano.
Osobny przegląd AST potwierdził zachowanie wszystkich 277 oryginalnych metod
testowych oraz ich asercji po uwzględnieniu zmienionych nazw importowanych modułów.

## Przegląd zmian w logice

Porównanie AST definicji po uwzględnieniu przeniesionych importów nie wykazało
nieobjaśnionych różnic. Funkcje generowania, RNG, procesów stochastycznych,
selekcji, obliczeń statystycznych, ATR, grupowania i rankingu, matchingu,
agregacji oraz budowy figury zachowały treść. Sprawdzono też wartości stałych.
Przeniesienie parsera i dalszej części main do workflow sprawdzono osobno:
ciąg instrukcji parsowania i ciąg instrukcji obsługi przebiegu pozostały te same.

Świadome zmiany techniczne objęły:

- Jedną strumieniową implementację SHA-256 pliku zamiast kilku kopii.
  Osobne hashe cen/profili/fingerprintów pozostały bez zmian.
- Jeden czytnik JSON dla dwóch identycznych dotychczasowych czytników obiektu
  z utf-8-sig. Pozostałe polityki JSON zachowano osobno.
- Jeden serializer JSONL; wrapper diagnostyczny podaje null zamiast splitu.
  Adnotacja split dopuszcza teraz jawne None; wynikowe bajty nie zmieniły się.
- Wspólną kontrolę potomka dla dwóch zgodnych funkcji ścieżek, z zachowaniem
  ich różnych komunikatów. Kontrola ścieżki partii ma inne reguły i pozostała osobna.
- Dostosowanie **dwóch** ochronnych odwołań do położenia źródła z parents[4]
  do parents[5], ponieważ profile I/O i porównania znalazły się poziom głębiej.
  Test z innym CWD sprawdza te same chronione katalogi i blokuje mkdir również
  w przypadku błędu testowanego zabezpieczenia.
- Zmianę nazwy modułu kontrolowanego przez preflight na aktualną ścieżkę refinement.
  Kontrola instalacji, źródeł i SHA pozostała aktywna.
- Jawny stary identyfikator loggera, aby przeniesienie pliku nie zmieniło logowania.

Nie scalono różnych algorytmów wyboru okien, różnych definicji proporcji świec
ani kodowań JSON. Nie zmieniono kolejności RNG, operacji float/Decimal,
zaokrągleń, remisów, granic okresów, progów, statusów profili, retry, warunków
fallbacku i strict-gaps. Nie ujednolicano tolerancji ani nie naprawiano przy okazji
znanych ograniczeń procesu danych.

Wewnętrzne ścieżki importów oraz __module__ i ścieżki tracebacków zmieniły się
zgodnie z nową strukturą. Projekt nie używa pickle do zapisu tych obiektów.
Nie pozostawiono kopii algorytmów pod starymi ścieżkami ani dawnych modułów src.*.
Małe świadome eksporty pakietów labeling i windows są zachowane.

## Środowisko i granice weryfikacji

Windows, CPython 3.13.15, Matplotlib 3.11.2. Nie oznacza to testów na wszystkich
wersjach od deklarowanego Pythona 3.10 ani na innych platformach.
Rzeczywiste HTTP i fallback na serwerze nie były uruchamiane; istniejące testy
tych scenariuszy używają mocków, a prawdziwe archiwum sprawdzono offline.

W roboczym venv brakowało backendu budowania. Zadeklarowany setuptools oraz
narzędzie wheel przygotowano w osobnym tymczasowym venv; właściwe budowanie
i instalację wheel wykonano z --no-index. Nie zmieniono roboczego środowiska
aplikacji ani jej zależności. Zastosowany backend: setuptools 84.2.1.

Historyczne checkpointy runnera nadal odrzucają wznowienie po zmianie SHA kodu.
Nie przepisywano ich, historycznych raportów, profili ani paczek handoff.
Nie wykonano nowego pełnego eksperymentu, pobierania historii, treningu lub inferencji.

## Odtworzenie podstawowych kontroli

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/verify_chart_pilot.py results/diagnostics/dc-20261106-c/pilot --re-render
.\.venv\Scripts\python.exe -m market_levels.cli.label_pilot --pilot results/diagnostics/dc-20261106-c/pilot --output results/diagnostics/sr-20261106-a --verify --re-render
.\.venv\Scripts\python.exe -m market_levels.cli.build_dataset verify --output data/datasets/ds35-800-20261107-a --check-sources
```

Ostatnie trzy polecenia wymagają istniejących lokalnych artefaktów i właściwego
środowiska renderera. Weryfikatory zapisują odtworzenie w katalogach tymczasowych.
