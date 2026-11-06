# Oddzielna kontrola stabilności OHLC — 2026-11-06

Przygotowano `scripts/run_refinement_fresh_seeds.ps1` dla seedów **20261201,
20261211**. Przed rozpoczęciem pracy nie występowały w lokalnych manifestach.
Poprzednia ocena 20261105/20261115/20261125 jest według autora zakończona.
V2-full-refined jest wstępnym faworytem autora, nie modelem zatwierdzonym przez kod.

## Zaplanowane obliczenia

| Grupa | Generator | Wariant mechanizmów | Profil |
| --- | --- | --- | --- |
| V1 | v1 | historyczny v1 | istniejący v1 |
| V2-full-original | v2 | full | istniejący pierwotny v2 |
| V2-full-refined | v2 | full | istniejący full refinement |
| V2-bridge_volatility-refined | v2 | bridge_volatility | istniejący osobno dostrojony refinement |

RunFull ma osiem partii: cztery grupy × dwa seedy. Każda zawiera 60 BTC i 60 ETH,
łącznie **960 nowych serii**. Selekcja rzeczywista jest identyczna jak poprzednio:
60 rozłącznych okien po 120 świec, selection_seed=20261106, trening chronological_v1.
Granice pochodzą z konfiguracji. Nie używamy validation ani test.

SmokeTest wykonuje osiem małych partii po 2 BTC + 2 ETH: **32 serie**, 16 raportów
indywidualnych i dwa podsumowania, po jednym na instrument. To kontrola techniczna.
RunFull nie został uruchomiony w tym zadaniu. Nie ponowiono kalibracji rynku.

## Implementacja i bezpieczeństwo

Nowy skrypt jest cienkim wejściem do wspólnego skryptu PowerShell/koordynatora
`refinement_comparison.py`. Nie duplikuje zapisu danych ani matematyki.
Nowa flaga wewnętrzna `--fresh-seeds` wybiera jawny plan z dwoma stałymi seedami,
czterema grupami, osobnym identyfikatorem eksperymentu i domyślnym katalogiem
`data/synthetic/rf-<12 hex>`. Pełny UUID jest w run.json.

CheckOnly nadal sprawdza importy, CLI, chronological_v1, rzeczywiste CSV,
refinement i 12 historycznych raportów V1/full-original. Dodatkowo wczytuje
cztery bazowe pliki v1/original i porównuje ich pełną zawartość z profilami
w zamrożonych raportach. Wymaga ośmiu profili unapproved i zgodnych źródeł SHA.
Nie tworzy profili przez wyciąganie ich z raportów. Nowe seedy nie mogą być
seedami kalibracji tych profili. Stare raporty służą wyłącznie do kontroli
pochodzenia i referencji; **nie są wejściami agregacji nowej próby**.

Zachowano odmowę nadpisania, kontrolę SHA konfiguracji/kodu/wejść, krótkie
ścieżki z kontrolą MAX_PATH obu wariantów, logi UTF-8 i systemową blokadę przebiegu.
Checkpointy są zapisywane po sprawdzeniu manifestów, CSV i raportów.
Po przerwaniu opublikowana partia bez checkpointu jest odczytywana i walidowana,
a nie generowana ponownie. Zmiana pliku lub tożsamości przebiegu zatrzymuje pracę.
Wznowienie działa tylko dla tego samego trybu i niezmienionych wejść/kodu.

Dotychczasowy skrypt i plan trzech znanych seedów pozostają obsługiwane:
RunFull tego wcześniejszego planu nadal generuje 720 serii dwóch grup.
Zmiana nie dotyka generatora, matematyki, parametrów, profili ani poprzednich raportów.

## Odczyt wyniku

W nowym katalogu przebiegu powstają:

- `comparisons/`: raporty indywidualne każdej grupy/seeda/instrumentu;
- `summary/BTCUSDT/` i `summary/ETHUSDT/`: JSON i Markdown standardowego agregatora;
- w każdym z tych katalogów `STABILITY.md`: tabela priorytetowych metryk;
- `run.json`, `completed/`, `logs/`: tożsamość, integralność i logi etapów.

Agregator sprawdza cztery grupy, zgodne profile/pochodzenie, te same seedy
i liczności. Dodatkowa kontrola nowej próby wymaga dokładnie ośmiu raportów
na instrument, dwóch powtórzeń każdej grupy i wyłącznie 20261201/20261211.
Nie dołącza automatycznie poprzednich trzech seedów.

STABILITY.md prezentuje **abs_ac1, window_std_mean, window_std_std, abs_q99,
body_fraction i relative_range_mean**: wartość realną, średnią syntetyczną,
średni błąd bezwzględny i odchylenie między seedami, osobno dla każdej grupy.
Pełny JSON/Markdown zachowuje pozostałe metryki, tolerancje i opis ablacji.
Wykorzystuje wyniki istniejącego agregatora, bez nowej definicji statystyk.

To stabilność symulacji na tych samych danych treningowych, **nie niezależny
test na nowym rynku**. Dwa seedy dają ograniczony obraz rozrzutu.
Kod nie wybiera zwycięzcy ani nie zatwierdza generatora. Decyzja pozostaje autorowi.
