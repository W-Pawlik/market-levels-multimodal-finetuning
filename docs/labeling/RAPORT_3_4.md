# Raport etapu 3.4 — etykietowanie poziomów S/R

Wykonanie: 2026-11-06, Windows, Python 3.13.15, Matplotlib 3.11.2.
Zaimplementowano i uruchomiono etykietowanie wszystkich **32 istniejących wykresów**
etapu 3.3 (16 rzeczywistych i 16 syntetycznych). Wyniki zapisano wyłącznie w nowym
katalogu `results/diagnostics/sr-20261106-a/`. Ocena autora i decyzja o zamknięciu
3.4 pozostają otwarte. Nie rozpoczęto 3.5.

## Implementacja

- `labeling/algorithm.py`: jawne, niemutowalne modele `Extremum`, `Group`,
  `LabelResult`, walidacja istniejącymi funkcjami projektu, TR i Wilder ATR,
  ekstrema, grupy, reakcje, klasyfikacja, ranking i serializacja.
- `labeling/pilot.py`: sprawdzenie manifestu i sidecarów oryginalnego pilotażu,
  SHA-256 CSV/PNG i kanonicznego OHLC, obliczenia, oddzielne obrazy i raporty,
  sprawdzenie wejść po wykonaniu, atomowa publikacja wspólnym mechanizmem projektu.
- `cli/label_pilot.py` oraz entry point `market-levels-label-pilot`: uruchomienie
  i kontrola wyników. CLI wymaga całego 32-elementowego pilotażu.
- Nowe testy, instrukcja PowerShell i skrypt przygotowania handoff z SHA-256.

Nie dodano zależności. Matplotlib pozostaje istniejącym dodatkiem `[charts]`.
Algorytm korzysta wyłącznie ze 120 świec, bez wcześniejszej/przyszłej historii
i bez metadanych generatora. Dane źródłowe, seed, symbol i profil są kopiowane
do diagnostyki, ale nie trafiają do funkcji wyznaczającej poziomy.

## Zastosowana matematyka i reakcje

Ekstrema są ścisłe, z trzema sąsiadami z każdej strony. Indeksy 0–2 i 117–119
są pomijane. TR pierwszej świecy to H−L, inicjalizacja ATR to średnia TR[0:14],
następnie rekurencja Wildera. Grupowanie używa połowy końcowego ATR.
Posortowane H/L tworzą wspólne zachłanne grupy o całej rozpiętości ≤ delta,
bez łączenia łańcuchowego. Poziom jest medianą wszystkich ekstremów grupy.

W grupie najpierw wybieramy najsilniejsze ekstremum: dla H siła to cena−mediana,
dla L mediana−cena. Dla samych H oznacza to wybór najwyższego, dla samych L
najniższego. Po jego zachowaniu odrzucamy ekstrema oddalone o mniej niż pięć
świec. Następnie wybieramy najsilniejsze z pozostałych i powtarzamy. Remis siły
wygrywa późniejsza świeca, pełny remis H przed L. Diagnostyka porządkuje zachowane
reakcje chronologicznie i wskazuje dla odrzuconych blokującą reakcję.

Przykład A (H10=100, H14=103, H18=101) daje **jedną reakcję: 14**.
Przykład B (H10=103, H14=100, H18=101) daje **dwie: 10 i 18**.
To celowo nie jest maksymalizacja liczby reakcji. Oba przykłady sprawdzono także
na poprawnych oknach 120 świec OHLC. Mediana nie jest ponownie liczona po filtrze.

Grupa z mniej niż dwiema reakcjami odpada. Poziomy odległe od ostatniego Close
o ≤ delta odpadają. Pozostałe klasyfikujemy względem Close i porządkujemy osobno
dla wsparć i oporów według liczby reakcji, ostatniej reakcji, odległości, ceny i ID.
Zostaje maksymalnie 3+3. Każda pominięta grupa ma przyczynę w diagnostyce.

Obliczenia używają stałego kontekstu Decimal z 50 cyframi znaczącymi.
Wartości ATR i delta nie są zaokrąglane do centów. Zwykła rekurencja Decimal
ma skończoną precyzję, co jawnie odnotowano w diagnostyce; nie jest obliczeniem
na dokładnych ułamkach. JSON VLM powstaje bez konwersji do float, z ROUND_HALF_UP
do dwóch miejsc. Diagnostyka przechowuje wszystkie uzyskane cyfry jako tekst.

Kolizje po zaokrągleniu obsłużono również między wsparciem a oporem. Wygrywa
silniejszy kandydat według tego samego rankingu; duplikat jest pomijany przed
limitem trzech, z ID obu grup w `collisions`. Kolejność w obrębie każdej strony
pozostaje zgodna z rankingiem. W tym pilotażu nie wystąpiła żadna kolizja.

## Wyniki wszystkich 32 wykresów

Pełna tabela odpowiedzi dla każdego pliku, symbolu i źródła oraz liczniki
ekstremów/reakcji są w [raporcie przebiegu](../../results/diagnostics/sr-20261106-a/RAPORT.md).
Każdy rekord ma pliki o numerze `000`–`031`: `labels/`, `diagnostics/`, `overlays/`.
Identyfikatory źródłowe i hashe łączą je z oryginałami w `dc-20261106-c/pilot`.

| Liczba poziomów na wykres | Liczba wykresów — wsparcia | Liczba wykresów — opory |
|---|---:|---:|
| 0 | 9 | 6 |
| 1 | 5 | 2 |
| 2 | 2 | 3 |
| 3 | 16 | 21 |

Łącznie: **57 wsparć i 71 oporów**, 128 wybranych poziomów.
Bez wsparć: **9**, bez oporów: **6**, bez obu rodzajów jednocześnie: **0**.
Ekstrema przed filtrowaniem: **739**, zachowane niezależne reakcje: **708**,
odrzucone bliskie reakcje: **31**. Liczba 708 obejmuje wszystkie grupy,
także później pominięte jako poziomy. Odrzucone grupy: 165 z powodu mniej niż
dwóch reakcji, 15 z powodu bliskości Close, 64 przez limit rankingu.
Przyczyny są przypisywane w tej kolejności; grupa z jedną reakcją i blisko Close
ma zapisaną pierwszą przyczynę. Statystyki maszynowe: `summary.json`.

## Weryfikacja

Przed zmianami: **169 testów zaliczonych, 0 niezaliczonych**.
Po zmianach: **199 testów zaliczonych, 0 niezaliczonych**, czas 91,666 s.
To 169 dotychczasowych i 30 nowych testów (25 jednostkowych, 5 integracyjnych).
Zapis wykonania: [WYNIK_TESTOW.txt](WYNIK_TESTOW.txt).
Nowe testy obejmują ręczne przykłady TR i inicjalizacji/rekurencji ATR,
ekstrema i brzegi, remisy cen, rozpiętość grup, grupy mieszane i mediany,
regułę A/B i odstępy 4/5, siłę kierunkową i remisy, granicę Close po obu
stronach, ranking i limit, kolizje między stronami, ROUND_HALF_UP, puste
wyniki, zerową zmienność, powtarzalność i niezależność od metadanych/kontekstu,
błędy OHLC/czasu/liczby/typu, pełny pipeline, hashe, niezmienność wejść,
odmowę nadpisania i niepublikowanie częściowego wyniku po błędzie renderera.

Faktycznie wykonano na lokalnych danych:

1. Etykietowanie wszystkich 32 okien i kontrolę wejść przed/po (97 plików:
   manifest oraz po 32 CSV/PNG/JSON).
2. `--verify --re-render`: ponowne obliczenie etykiet i pełnej diagnostyki,
   kontrola kompletu plików oraz SHA, identyczne bajty 32 nowych PNG.
3. `verify_chart_pilot.py --re-render`: 32 oryginalne PNG nadal mają identyczne
   hashe i można je odtworzyć; zachowano ich oryginalne bajty.
4. Instalację edytowalną i `market-levels-label-pilot.exe --help`.
   Pierwsza próba bez izolacji budowania wykazała brak lokalnego setuptools;
   standardowa instalacja z izolacją powiodła się. Nie zmieniano zależności projektu.
5. Kontrolę wyglądu przykładowego obrazu `013.png`: dwa style linii, legenda,
   rozdzielone etykiety cen i zachowane osie. To kontrola czytelności obrazu,
   nie niezależna ekspercka ocena poprawności poziomów.

## Przykłady do ręcznej oceny i ograniczenia

- [000.png](../../results/diagnostics/sr-20261106-a/overlays/000.png): trzy opory,
  brak wsparć; istotny przykład, że algorytm nie wypełnia list na siłę.
- [013.png](../../results/diagnostics/sr-20261106-a/overlays/013.png): pełne 3+3,
  bliskie linie wsparcia; sprawdź rozdzielenie napisów i dobór według rankingu.
- [017.png](../../results/diagnostics/sr-20261106-a/overlays/017.png): największa
  redukcja bliskich reakcji; sprawdź `suppressed` w `diagnostics/017.json`.
- [012.png](../../results/diagnostics/sr-20261106-a/overlays/012.png): najwięcej
  wspólnych grup H/L; porównaj mediany i reakcje w `diagnostics/012.json`.

Pilotaż pokrywa wybrane sytuacje, a nie częstości całego rynku. Ścisłe ekstrema
pomijają płaskie szczyty/dołki, a reguła odległości od końcowego Close może
usunąć bliski poziom. Są to skutki zatwierdzonej definicji, nie błędy korygowane
przez dopasowanie parametrów. Ręczna kontrola wszystkich 32 wykresów pozostaje
do wykonania przez autora. Nie deklarujemy niezależnej oceny eksperckiej.
Nie zmieniano istniejących znanych ograniczeń pobierania ani innych etapów.

Oryginalne PNG nie zawierają poziomów. Nowe obrazy z liniami są **wyłącznie
diagnostyczne i wykluczone z przyszłych wejść VLM**. Profile nadal `unapproved`.
Nie wykonywano kalibracji, generowania OHLC/800 wykresów, audytu 600 serii,
eksperymentu 960 serii, pobierania Binance, podziału datasetu, wyboru/treningu
modelu, edycji pracy ani publikacji na GitHubie.

## Uruchamianie i handoff

[Instrukcja PowerShell](INSTRUKCJA_POWERSHELL.md) zawiera pełne polecenia.
Paczka `handoff/labeling-3-4-20261106.zip` zawiera aktualny kod, konfigurację,
testy, dokumentację i instrukcje AI, źródłowy mały pilotaż oraz wyniki 3.4.
Nie zawiera `.venv`, cache, build, egg-info ani dużych danych historycznych.
Wewnątrz: `HANDOFF_SHA256.json`, obok: plik `.zip.sha256`.
