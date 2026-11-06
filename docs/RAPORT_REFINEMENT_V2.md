# Dostrojenie zmienności OHLC v2 — implementacja 2026-11-05

Dodano `bridge_volatility`: most Browna i stacjonarny AR(1), bez mieszanki
ciężkoogonowej. Jawna mapa `VARIANT_MECHANISMS` określa wszystkie sześć wariantów.
Pięć dawnych wariantów zachowuje dotychczasowe aktywacje, równania, seedy,
strumienie RNG, OHLC i metadane. V1 pozostaje domyślny.

## Osobna kalibracja

Nowe CLI `market-levels-refine-v2-volatility` uruchamia
`volatility_refinement_v1`. Zmienia wyłącznie `volatility_phi` oraz
`volatility_stationary_std`. Źródłowy profil v2 jest odczytywany bez zapisu.
Gamma mostu, p i k mieszanki, sigma, zakres cen, statystyki i konfiguracja
reżimów pozostają zamrożone. Każdy symbol i wariant są dostrajane osobno;
procedura autora wytworzy cztery profile. Nie utworzono ich na danych rynku.

Sekcja `volatility_refinement_v1` w `configs/experiment.json` definiuje siatkę
7 × 5, trzy seedy 73001/73002/73003 oraz po 12 przykładów na seed.
Selekcja referencji daje 36 rozłącznych okien po 120 świec, bez przejść przez
luki. Ziarno selekcji 73004. Źródłem granic jest zatwierdzony podział konfiguracji.
Walidacja odmawia użycia validation/test. Wszystkie kandydatury korzystają
z tych samych seedów przykładów i sześciu osobnych strumieni RNG.

Pierwszy kandydat to oryginalne parametry zmienności, także jeśli leżą poza
nową siatką; potem unikalne punkty siatki. Najwyżej 36 kandydatów domyślnie,
1296 symulowanych okien na profil. Limity konfiguracji: 64 kandydatów,
2304 okna. Budżet jest sprawdzany przed symulacją. Nie ma wczesnego zatrzymania
ani automatycznego rozszerzania siatki. Remisy zachowują wcześniejszy punkt,
w szczególności baseline. `--dry-run` wykonuje obliczenia, lecz nie zapisuje.

## Kryterium, ustalone przed diagnostyką

Dla każdej metryki e = |syntetyczna − referencyjna| / skala tolerancji.
Dla błędów względnych skala = tolerancja × max(|referencja|, 1e-8).
Wagi priorytetów `abs_ac1`, `window_std_mean`, `window_std_std` wynoszą 3;
kontroli `abs_q95`, `abs_q99`, `range_mean`, body i obu knotów — 1.
Podstawowy błąd seeda to suma ważonych e² podzielona przez sumę wag.

Dodatkowa kara wynosi 4 × średnia po kontrolach
max(0, e − max(1, e_baseline))². Chroni przed dalszym pogorszeniem kontroli
poza tolerancję albo poza już zły wynik baseline. Nie jest twardym warunkiem
wyboru ani akceptacji. Wynik kandydata = 0.75 × średni błąd trzech seedów
+ 0.25 × najgorszy błąd seeda. Ocena każdego seeda używa wspólnej referencji
36 okien i własnej syntetycznej próbki 12 okien. Pooled features wszystkich
36 syntetyków są dodatkowymi informacjami, nie zastępują oceny po seedach.
Nieokreślona lub niefinitywna metryka przerywa kalibrację.

Cele diagnostyczne: AC1 0.05 bezwzględnie; średnia std okien 10%, rozrzut std
okien 20%, q95 i q99 15%, średni zakres 10%, body i knoty 0.03 bezwzględnie.
Są konfigurowalne i zapisane w audycie. Nie dopasowano ich do validation/test.

## Pochodzenie i bezpieczeństwo

Profile mają version=2, generator_version=2.0.0, status=unapproved,
wiążący wariant, pełne parametry, siatkę, wagi, selekcję, wyniki wszystkich
kandydatów i przyczynę wyboru. Audyt przechowuje kopię źródłowego profilu,
jego kanoniczny hash JSON oraz odrębny SHA-256 bajtów pliku. Opcjonalny
`--source-sha256` przypina hash pliku. CSV musi odpowiadać SHA źródła
oryginalnego profilu. Odczyt całego pliku na potrzeby identyfikacji nie
wprowadza jego przyszłych świec do statystyk; obliczenia filtrują trening.

Walidator ponownie oblicza funkcję celu z zapisanych cech, sprawdza cały grid,
baseline, wybór minimum, pochodzenie, zamrożone pola, okres i rozłączne okna.
Faza `evaluation` jest jawnym, wewnętrznym typem kandydatury; standardowy
odczyt i zapis jej odmawiają. Nie podmieniamy audytu na `not_calibrated`.
Zapis korzysta z istniejącej atomowej publikacji i poprawki Windows, bez
nadpisywania. Rzeczywiste błędy nie są zastępowane błędami sprzątania.

## Raporty i zgodność

Istniejące CLI kalibracji, generowania i porównania oraz stare formaty profili
pozostają obsługiwane. Generowanie otrzymało dodatkowy wariant; nowy profil
refinement wymaga dokładnie wariantu zapisanego w audycie.

`experiments.py` bez nowych profili zachowuje stare etykiety. Gdy pojawi się
refinement, wymaga grup V1, V2-full-original, V2-full-refined oraz
V2-bridge_volatility-refined, wspólnego źródła profili i identycznych seedów,
liczności oraz referencji. Odmawia uśrednienia różnych hashów profili.
Może wczytać istniejące raporty; stare manifesty można porównać bez generowania.
JSON i Markdown pokazują wartości realne i syntetyczne, średni błąd bezwzględny,
odchylenie standardowe między seedami, zmiany błędów, liczniki poprawy/pogorszenia
oraz przekroczenia tolerancji po seedach i dla średniego błędu.

Praktyczna równoważność to zmiana błędu do 10% danej tolerancji. Ablacja
mieszanki ma opis dla każdej metryki; obejmuje także osobne dostrojenie AR(1),
więc nie izoluje przyczynowo samej mieszanki. Nie wybieramy zwycięzcy.
Zaproponowane nowe seedy 20261205 i 20261215 nie występują w 28 lokalnych
manifestach sprawdzonych przed pracą. Ich użycie będzie kontrolą stabilności
na treningu, a nie niezależnym testem rynku.

## Pliki tej iteracji

- `synthetic/refinement.py`, nowe CLI i entry point w `pyproject.toml`.
- `v2_parameters.py`, `generator_v2.py`, `profile_v2.py`: wariant i audyt.
- `pipelines/synthetic.py`, `synthetic/comparison.py`: wiązanie wariantu profilu.
- `synthetic/experiments.py`: identyfikacja profili i diagnostyka porównań.
- `cli/generate_synthetic.py`, konfiguracja, dokumentacja i instrukcje `.ai`.
- Nowe testy jednostkowe/integracyjne, fixture regresji dawnych wariantów v2;
  dwa istniejące testy rozszerzono o szósty wariant.

Stan roboczy zawiera również wcześniejszą implementację v2 i poprawkę Windows,
nieobecne jeszcze w HEAD; handoff zawiera aktualne źródła, także te pliki.
Nie wykonywano commitu ani push w tej iteracji.
