# Renderer MVP i audyt istniejących danych

Moduły `charts/diversity.py`, `charts/renderer.py`, `charts/pilot.py` oraz
`cli/audit_charts.py` implementują etap diagnostyczny. Nie zmieniają V1, V2,
konfiguracji eksperymentu ani czterech profili refined. Nie generują OHLC.

## Obraz

Matplotlib Agg rysuje 120 korpusów i 120 pionowych knotów w PNG 1024 × 768,
100 DPI. Oś X to pozycja 1–120, oś Y to oryginalna liniowa cena USDT.
Granice Y wynikają wyłącznie z ekstremów okna z marginesem 5%; dla płaskich
danych margines wynika z 0.1% ceny. Ta sama reguła obejmuje real i synthetic.
Nie normalizuje cen ani nie korzysta ze świec poza oknem. Nie ma gridu,
wskaźników, poziomów S/R ani metadanych pochodzenia na obrazie, także w PNG info.
Renderer przyjmuje wyłącznie świece i ścieżkę wyjściową. Czas i source_archive
nie są wejściem warstwy rysującej. Traci się jedynie dokładność pikselową
typową dla obrazu; źródłowe Decimal pozostają w przenośnych CSV.

Matplotlib jest opcjonalnym dodatkiem `[charts]`; pobieranie danych nadal nie
wymaga zewnętrznych bibliotek. MVP nie używa mplfinance, ponieważ narysowanie
prostych korpusów i knotów nie wymaga dodatkowej zależności Pandas.

## Audyt i wybór

Audyt odczytuje opublikowane manifesty, odrzuca staging, wybiera największą partię
full/refined na seed, sprawdza cały schemat profilu i istniejący audyt refinement.
Weryfikuje tożsamość przykładów, OHLC, udziały reżimów i hashe. Metryki
przelicza z cen, nie kopiuje deklaracji reżimu jako klasy całego obrazu.

Progi zmienności to tercyle std z 72 rozłącznych rzeczywistych okien na symbol,
od początku każdego ciągłego fragmentu treningu. Pozostałe progi: treningowe
q95 zakresów świec i q99 bezwzględnych log-zwrotów. Wszystkie wzory są w audycie.
To jawna diagnostyka, bez poszukiwania parametrów na validation/test.

Pilotaż ma po 8 przykładów z każdej z czterech grup. Zachłanny dobór pokrywa
tagi rzeczywistego ruchu, zmienności, proxy wybicia/odwrócenia oraz osobno
deklarowanych reżimów i seedów. Seed 20261106 rozstrzyga remisy po stabilnym
sortowaniu; wersja algorytmu `coverage_seeded_tiebreak_v1` jest w manifestach.
Nie używa wag generatora ani nie zmienia docelowego doboru danych treningowych.
Kandydackie realne okna mają krok 60 i mogą się nakładać; nie jest to końcowy
podział zbioru. Braki pokrycia są jawne w `pilot.coverage`.

Każdy PNG ma boczny JSON z symbolem, źródłem, wariantem, profilem i jego hashem
kanonicznego JSON oraz osobnym hashem bajtów profilu, seedem głównym i seeda
przykładu, ID, czasem rzeczywistym, ścieżką i hashem CSV, indeksem okna,
hashem OHLC, wersją renderera/Matplotlib, parametrami obrazu i SHA PNG.
Osadzone w pierwotnych metadanych profile pozostają w źródłach; pilotaż wskazuje
je ścieżką i hashem. Eksport CSV zawiera dokładne świece każdego obrazu, dlatego
można sprawdzić i ponownie wyrenderować pilotaż bez dużych lokalnych danych.

## Wyniki i ograniczenia

Przeanalizowano 300 BTC i 300 ETH ze wszystkich pięciu seedów, bez błędów
wejść i bez duplikatów OHLC. Zapisano 32 PNG: 16 realnych i 16 syntetycznych.
Wszystkie cztery grupy mają ruchy w górę/w dół, niską kierunkowość i pasma
low/medium/high; oba syntetyczne podzbiory obejmują wszystkie pięć seedów.
Fazy złożone są obecne. Dokładne ID i liczniki są w audycie oraz manifestach.

Konsolidacje zajmują 50.9% świec BTC i 50.4% ETH; breakout tylko 3.64% i 3.13%.
Sekwencja consolidation → breakout → trend: odpowiednio 19 i 17 okien.
Znak ruchu nie zgadza się z deklaracją w 32 segmentach trendu BTC i 35 ETH.
Próg kierunkowości dodatkowo odróżnia zgodny znak od wyraźnego ruchu.
Proxy wybicia reaguje na 292/300 BTC i 291/300 ETH: jest mało selektywne,
nie jest wiarygodną etykietą rynku. Nie implementowano etykiet S/R.

Std zmienności pomiędzy oknami wynosi 51.5% referencji BTC i 56.9% ETH.
To inna referencja (72 okna na stałej siatce) niż wcześniejsze porównanie
48%/37%; nie oznacza poprawy generatora. Maksymalne std syntetycznych okien
to 0.0226 BTC i 0.0298 ETH wobec 0.0393 i 0.0443 referencji. Skrajnie zmienne
okna pozostają słabo odwzorowane. Raport nie uzasadnia akceptacji generatora.

Obejrzano reprezentatywne PNG, sprawdzono czytelną skalę i brak ujawnienia
pochodzenia przez tytuły lub daty; automatyczna kontrola obejmuje komplet pilotażu.
Nie zastępuje to wspólnej oceny wzrokowej wszystkich przypadków przez autora.
Deterministyczność bajtowa jest potwierdzana w tym samym środowisku Windows;
nie deklaruje zgodności wszystkich wersji Matplotlib i platform.

Zapis odbywa się w nowym katalogu poza `data/`, z wyłącznym tworzeniem PNG,
kontrolą MAX_PATH i atomową publikacją kompletnej partii przez istniejący
moduł staging z ponowieniami blokad Windows. Istniejące źródła są hashowane
przed i po. Raport o brakach może zakończyć się sukcesem procesu, dlatego
status diagnostyczny nie jest statusem jakościowym ani zatwierdzeniem.
