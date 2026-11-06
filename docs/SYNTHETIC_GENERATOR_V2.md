# Generator OHLC v2 i kontrolowana ocena wariantów

V2 poprawia narzędzia modelowania kształtu świec, ogonów i zmienności. Nie jest
jeszcze zatwierdzonym generatorem docelowego zbioru. Domyślne CLI nadal wybiera v1.
Obowiązują BTCUSDT/ETHUSDT, 4h, 120 świec, 12 kroków i 1–3 dotychczasowe fazy.
Podział `chronological_v1` i wszystkie wcześniejsze ustalenia eksperymentu pozostają.

## Punkt odniesienia

W lokalnych raportach `0c2d0b24557f20945757af65` (BTC) i
`0fa65cfe0c52f41cca3c7f51` (ETH) rzeczywiste/syntetyczne v1 wartości wynoszą:

| Metryka | BTC rzeczywiste / v1 | ETH rzeczywiste / v1 |
| --- | --- | --- |
| Std zwrotów 4h | 0,014268 / 0,012925 | 0,017518 / 0,015817 |
| Średni (High−Low)/Open | 0,019730 / 0,015723 | 0,024977 / 0,019406 |
| Średni udział korpusu | 0,4047 / 0,5708 | 0,4129 / 0,5682 |
| Q99 abs(r) | 0,05149 / 0,03873 | 0,06425 / 0,04680 |
| Std zmienności między oknami | 0,005915 / 0,002802 | 0,006771 / 0,003077 |
| Korelacja abs(r), lag 1 | 0,2301 / 0,1659 | 0,2406 / 0,1312 |

W v1 końcowy zwrot jest sumą dwunastu normalnych przyrostów, a High/Low pochodzą
z rzadko próbkowanej ścieżki. Samo pomnożenie sigma nie rozwiązałoby jednocześnie
proporcji korpusu, ogonów i trwałości zmienności. V2 rozdziela te zadania.

## Matematyka

Pracujemy w log-cenach. Dla świecy t:

```text
d_t = mu_regime - kappa_regime * (X_open - center_regime)
sigma_t = sigma_regime * L_t
X_close = X_open + d_t + sigma_t * Z_t
```

Mu i sigma nadal mają jednostkę jednej świecy 4h. Rewersję w v2 wyznaczamy na
początku świecy (krok Eulera 4h). Plan faz, jego wagi, zakresy dryfu, zmienności
i siły rewersji są współdzielone z v1. Nie wymuszamy idealnych poziomów.

### Mieszanka na poziomie Close

```text
epsilon ~ N(0,1), U ~ Uniform(0,1), niezależnie
s = 1 / sqrt((1-p) + p*k^2)
Z = s * epsilon * (k if U < p else 1)
```

E[Z]=0, E[Z²]=1. Parametry p i k zmieniają ogony, nie wariancję teoretyczną
zaburzenia. Losujemy jedno Z na świecę 4h, nie dwanaście niezależnych mieszanek.
Wyłączenie ogonów daje Z=epsilon. Symetria mieszanki jest uproszczeniem;
asymetria rzeczywistych wzrostów i spadków nie jest odtwarzana automatycznie.

### Stacjonarna zmienność

```text
v = stationary_std^2
h_0 ~ N(0,v)
h_t = phi*h_(t-1) + stationary_std*sqrt(1-phi^2)*epsilon_h
L_t = exp(h_t - v)
```

Stan aktualizujemy raz na świecę i zachowujemy przez granice faz. Dla 0<=phi<1
mamy Var(h)=v. Z tożsamości E[exp(a*h)]=exp(a²*v/2) wynika
E[L²]=exp(-2*v)*exp(2*v)=1. Korekta wynosi **v**, a nie v/2: normalizujemy
oczekiwany kwadrat sigma, nie średnią samej sigma. Niezależność Z i h zapewnia
E[(L*Z)²]=1. To normalizacja części losowej, nie gwarancja, że całkowite zwroty
z dryfem, rewersją i mnożnikami faz będą miały dokładnie empiryczne sigma.

Nie dodano osobnego losowego mnożnika całego przykładu. Stacjonarny stan startowy
i jego trwałość już dają różnice między niezależnymi seriami; ich wystarczalność
trzeba ocenić z raportów zamiast podwójnie mnożyć wariancję.

### Jedna ścieżka wewnętrzna

```text
W_0=0; W_k=W_(k-1)+N(0,1)/sqrt(12)
B_k=W_k-(k/12)*W_12
X_k=X_open+(k/12)*(X_close-X_open)+gamma*sigma_t*B_k
```

Są dokładnie 13 punktów i 12 kroków. Pierwszy i ostatni punkt ustawiamy dokładnie
na zadane końce. Ceny to exp(X_k); High/Low to ich ekstrema. Nie ma niezależnego
losowania knotów. Poprzednie Close jest dokładnym następnym Open po konwersji
`Decimal(str(float))`, bez kwantyzacji wewnętrznych kroków.

Gamma zmienia wnętrze ścieżki bez zmiany Close, jego RNG ani stanu zmienności.
W neutralnym modelu gamma=1. Oznacza to brak dodatkowej korekty zakresu, a nie
brak losowej ścieżki. Przy neutralnych mechanizmach jest to dyskretny warunkowy
model normalny; nie jest bitowym ani matematycznie dokładnym odtworzeniem v1,
m.in. przez inną dyskretyzację rewersji.

## Warianty i RNG

| Wariant | Gamma | Z | L |
| --- | --- | --- | --- |
| V1 | stara ścieżka | stary mechanizm | stare mnożniki faz |
| V2-base | 1 | normalny | 1 |
| V2-bridge | z profilu | normalny | 1 |
| V2-tails | 1 | mieszanka | 1 |
| V2-volatility | 1 | normalny | AR(1) |
| V2-full | z profilu | mieszanka | AR(1) |

V2 ma strumienie `regimes`, `close`, `tail_selector`, `intracandle`, `volatility`
i `example`, z seedami SHA-256 `ohlc-v2:<seed_przykładu>:<nazwa>`. Dodatkowy
strumień selektora mieszanki pozwala zachować te same normalne epsilon po
włączeniu ogonów. Mechanizmy nie przesuwają sobie losowań. Włączenie ogonów lub
zmienności zmienia ceny i centra późniejszych faz w uzasadniony sposób.

Historyczny `example_seed(master,symbol,index)` nie zmienił się. Funkcja v1
w `generator.py` pozostaje dostępna; pipeline wybiera wersję przez `dispatch.py`.
Domyślne ustawienia v1 usuwają nowe klucze z historycznej reprezentacji
konfiguracji, więc jej metadane, hashe OHLC i identyfikatory partii są zachowane.
Testy golden dotyczą CPython 3.13.15; nie obiecujemy identyczności na dowolnym
Pythonie/platformie. W v2 zapisujemy wersję 2.0.0, wariant, identyfikator
eksperymentu, seedy strumieni, parametry z profilu i faktycznie aktywne wartości,
przebieg h/sigma, profil v2, jego hash i środowisko.

## Profile i konfiguracja

Profil v1 ma schemat 1. V2 wymaga schematu 2 i generator_version=2.0.0;
nie ma automatycznej migracji v1 do kompletnej kalibracji v2. Historyczny
`validate_profile` nadal sprawdza wyłącznie v1. Nowy `validate_generator_profile`
wybiera walidator; `load_profile` i atomowy `save_profile` obsługują obie wersje.
V2 współdzieli walidację podstawowych statystyk przez widok pól zgodnych z v1.

Profil v2 przechowuje dodatkowo `estimation_kind`, `v2_parameters`, niezmienioną
konfigurację faz, pochodzenie parametrów oraz pełny audyt kalibracji. Treningowy
profil ma identyfikator/granice podziału w `source.chronological_split` i hash CSV.
Nowe profile mają status **unapproved**. Ręczny profil diagnostyczny też ma ten
status, ale `estimation_kind=diagnostic`; nie udaje empirycznej kalibracji i nie
jest dopuszczony do porównania z rynkiem. Kandydaci wymagają osobnego zatwierdzenia.
Nie dodano automatycznego zatwierdzania ani modyfikacji profili v1.

W konfiguracji:

- `synthetic.generator_version`: domyślnie v1; argument CLI ma pierwszeństwo.
- `synthetic_v2`: wariant, experiment_id, osobna mapa profiles i ręczne parameters.
- `synthetic_v2_calibration`: siatki, seedy, liczba przykładów i rundy kalibracji.

Przy wskazaniu profilu v2 parametry **profilu** są źródłem matematyki; parametry
w konfiguracji służą diagnostyce bez profilu oraz jako punkt startowy kalibracji.
Zmiana reżimów względem zapisanych w profilu jest odrzucana. Do sprawdzenia innej
gamma w API należy jawnie utworzyć nowy niezatwierdzony profil, zachowując
pochodzenie zmiany; edycja dopasowanego profilu wymaga zgodnego audytu.

### Status i obsługiwane zakresy

| Parametr | Diagnostyczny start | Obsługiwany zakres | Pochodzenie po kalibracji |
| --- | --- | --- | --- |
| sigma_4h | BTC 0,012 / ETH 0,016 bez pliku | >0, skończone | std zwrotów treningu |
| initial_price_range | stare ręczne zakresy bez pliku | dodatni zakres | kwantyle 5/95% treningu |
| bridge_gamma | 1,5 | 0<gamma<=5 | ograniczona kalibracja łącznego modelu |
| tail_probability | 0,05 | 0<=p<=0,25 | jak wyżej |
| tail_scale | 3 | 1<k<=10 | jak wyżej |
| volatility_phi | 0,95 | 0<=phi<=0,995 | jak wyżej |
| volatility_stationary_std | 0,35 | 0<=std<=1 | jak wyżej |
| Fazy i ich rozkłady | zgodne z v1 | dotychczasowe ograniczenia | projektowe, nie oszacowane |

Zakresy są jawnymi ograniczeniami obsługiwanej diagnostyki i numeryki, nie
empirycznymi przedziałami ufności ani kryteriami akceptacji. Nie obcinamy zwrotów
ani cen. Przepełnienie, zanik do zera lub niefinitywne wyniki odrzucają partię.

## Ograniczona kalibracja wspólnego modelu

CLI `market-levels-calibrate --generator-version v2` wymaga jawnego okresu
wewnątrz zatwierdzonego treningu z konfiguracji. Odczytuje cały CSV, a ceny
walidacji/testu nie biorą udziału w estymacji, selekcji ani celu numerycznym.
Nie łączymy zwrotów ani okien przez luki. Nie zmieniamy starych plików profili.

1. Istniejące `calibrate` wyznacza bazowe sigma, zakres cen i statystyki treningu.
2. Wybieramy rozłączne okna treningowe istniejącą metodą. Domyślnie 12 okien,
   seed 73004, odrębny od późniejszego porównania 20261106.
3. Symulujemy full na jawnych seedach 73001/73002/73003, po 4 niezależne okna.
   Te same losowania służą kandydatom. Nie używamy końcowej próbki 60 do strojenia.
4. Przechodzimy po siatkach grup (phi,std), (p,k), gamma przez 2 rundy. Każdy
   kandydat oceniany jest **w całym modelu full**, z pozostałymi aktualnymi
   parametrami; parametry po połączeniu są więc ponownie oceniane.

Domyślne siatki: gamma 1/1,4/1,8/2,2; p 0,02/0,05/0,1; k 2/3/4;
phi 0,8/0,95/0,99; std h 0/0,3/0,6. Aktualny punkt, również start diagnostyczny,
jest dodatkowym kandydatem. Remisy zachowują bieżący punkt. Są to wartości
projektowe, konfigurowalne; nie ukrywamy, że to ograniczone przeszukiwanie
współrzędnych, a nie globalny optymalizator czy identyfikacja modelu AR z ticków.
Referencja celu jest ograniczoną próbką okien treningowych, więc jej kwantyle
i dobór parametrów mogą być niestabilne. Pełne statystyki treningu pozostają
w profilu; przed zatwierdzeniem trzeba ocenić wrażliwość na tę próbkę i siatkę,
korzystając nadal wyłącznie z treningu.

Cel obejmuje std zwrotów, Q95/Q99 abs(r), średni i Q95 zakresu, udział korpusu
i obu knotów, średnią i std zmienności okien, korelację abs(r) lag 1, kurtozę
oraz częstości abs(r)>2/3 próbnego sigma. Średnią kwadratów składników liczymy:

- skale dodatnie: różnica / max(abs(referencja),1e-5);
- udziały i korelacja: różnica / 0,25;
- częstości przekroczeń: różnica / 0,05;
- kurtoza: 0,25 razy różnica log(1+kurtoza).

Wagi i skale celu są projektowe. Umiarkowany wpływ log-kurtozy ogranicza pogoń za
pojedynczym ekstremum. Brakujące wskaźniki są jawne i pomijane, a surowe wartości
pozostają w audycie. Nie ma progu automatycznej akceptacji. Audyt zawiera wszystkie
unikalne próby, wyniki łączne i osobno po seedach, składniki błędu, historię grup,
wybrane wartości, seedy i referencyjne okna. Ponadto raportujemy ruchome próbne
std z 24 zwrotów (25 kolejnych świec, krok 1), bez przechodzenia przez luki,
oraz korelację abs(r) na treningu. Są to dodatkowe opisy trwałości, nie twierdzenie,
że parametry phi/std zostały bezpośrednio zidentyfikowane z ruchomego std.

## Porównanie wariantów

Dotychczasowy `market-levels-compare-synthetic` czyta obie wersje manifestów.
Sprawdza zgodność wersji/profilu, parametrów, aktywnych mechanizmów i przebiegu
zmienności. Podstawowe metryki i wybór rzeczywistych okien nie zmieniły definicji.
Nowe opcjonalne metryki: kurtoza Pearsona m4/m2² (normalna=3, m2=0 daje null)
oraz częstości abs(r)>2*std i >3*std, ze std próbki danego połączonego rozkładu.
Nie ma zwrotów ani par korelacyjnych między niezależnymi oknami.

Nowy tryb `--reports ...` łączy raporty opisowe w tabelę Realne/V1/V2-*. Wymaga
identycznego hasha real-csv, podziału, zakresu i listy wybranych rzeczywistych
okien oraz wartości ich metryk. Sprawdza hash każdego raportu. Nie można podmienić
referencji jednego wariantu. Nie można powtarzać raportu, partii ani seedów
przykładów jako nowych niezależnych powtórzeń. W obrębie wariantu profil musi
pozostać ten sam. V1 jest wymaganym punktem odniesienia.

Dla wielu seedów zapisujemy średnią wartości metryki, próbne std między seedami,
różnicę średniej od referencji i **średni błąd bezwzględny po seedach**. Ten ostatni
nie ukrywa znoszących się błędów dodatnich i ujemnych. Pokazujemy zmianę błędu
względem V1 i kierunek decreased/increased/unchanged dla każdej metryki.
Nie wybieramy automatycznie full ani „najlepszego” generatora. Rozkłady faz
i liczby odrzuceń/duplikatów zachowujemy w źródłach raportu. Zera odnoszą się do
zaakceptowanych partii; nie są licznikiem wszystkich nieudanych poleceń fail-fast.

Starsze raporty v1 są obsługiwane bez nowych pól wersji/seedów. Jeśli nie zapisały
seeda głównego, nie zgadujemy go; pozostają identyfikatory i seedy przykładów.
Właściwa ocena powinna mieć co najmniej trzy niezależne seedy i stały profil.
Kalibracja full nie oznacza, że parametry są osobno optymalne dla każdej ablacji.

To nadal opisowe porównanie z treningiem użytym do kalibracji. Nie jest
niezależną walidacją ani dowodem poprawy przyszłego modelu AI. Kontrola wizualna
oczekuje na renderer. Normalna ścieżka mostu, symetryczne ogony i stacjonarne
Gaussowskie h są uproszczeniami; 12 punktów po Open nie odtwarza mikrostruktury
ani ekstremów ciągłego procesu. Poprawę realizmu trzeba zmierzyć osobno.

Uruchomienie: [PowerShell v2](SYNTHETIC_V2_POWERSHELL.md).
Wykonane testy i mała próba: [raport v2](SYNTHETIC_V2_IMPLEMENTATION_REPORT.md).
