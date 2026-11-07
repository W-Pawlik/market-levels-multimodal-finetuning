# Etap 3.5, część 2 — zatwierdzenie profili i produkcyjny zbiór 800 przykładów

Wykonanie: 2026-11-07, na podstawie jawnej decyzji autora pracy z tego dnia.
**Powstał kompletny zbiór 800 przykładów i przeszedł pełną kontrolę po zapisie.**
Nie rozpoczęto treningu, nie wybrano VLM, nie uruchomiono eksperymentu 1600,
nie pobierano danych, nie ponawiano kalibracji ani kosztownych dawnych audytów.
Nie publikowano zmian na GitHubie i nie edytowano tekstu pracy.

## Wynik i lokalizacje

| Artefakt | Katalog / plik |
|---|---|
| Pełny zbiór lokalny | `data/datasets/ds35-800-20261107-a/` |
| Nowe zatwierdzone profile i ślad decyzji | `data/synthetic/approved-ds35-20261107/` |
| Preflight po zatwierdzeniu | `results/diagnostics/ds35-prod-pre-20261107-a/` |
| Testy, kontrola historii, ponowna weryfikacja i podobieństwo | `results/diagnostics/ds35p-20261107-a/` |
| 16 oddzielnych przykładów do przeglądu | `results/diagnostics/ds35-review-20261107-a/` |
| Handoff kodu i próbek | `handoff/etap-3-5-cz2-20261107.zip` |
| Osobna pełna paczka danych | `handoff/dane-800-20261107.zip` |

Identyfikator przebiegu: `0bffc45d-ca0a-44bf-b551-bae7bf8d8719`.
SHA-256 manifestu gotowego zbioru:
`0f9093fbdcbd39243fcf802bfdd723cb913b15838aa4a3cc469787d5e7e462d0`.
Pełny zbiór zajmuje około 48,6 MB przed kompresją.

## 1–2. Zatwierdzenie profili bez zmiany parametrów

Oba pierwotne profile wczytano aktualnym walidatorem v2. Potwierdzono symbol,
`estimation_kind=training`, wariant `full`, metodę `volatility_refinement_v1`,
komplet parametrów, konfigurację reżimów, zamrożone pola i pełny audyt celu.
Hash źródłowego CSV jest zgodny z lokalnymi pełnymi danymi, a kalibracja
i refinement obejmują wyłącznie zatwierdzony trening 2020–2023.
Granice i dokument `chronological_v1` są zgodne z konfiguracją.

Potwierdzono powiązanie obu profili z istniejącym audytem 600 serii:
po 300 rekordów BTC/ETH ma dokładnie identyfikator odpowiedniego pierwotnego
profilu. Nie generowano tych serii ponownie. Historyczny audyt raportował
ograniczoną dyspersję zmienności, słabą reprezentację skrajnych okien,
niewielki udział breakout i nie zawsze zgodny znak deklarowanego trendu.
Zatwierdzenie przez autora nie usuwa tych ograniczeń.

Utworzono nowe pliki `BTCUSDT_full_refined_approved.json` i
`ETHUSDT_full_refined_approved.json`; oryginały `unapproved` pozostały identyczne
bajtowo. Wspólną procedurę `approve_profile` zastosowano do empirycznej części
schematu, następnie przywrócono wersję 2 i zwalidowano cały profil v2.
Porównanie wszystkich pól po wyłączeniu `status` i `approval` jest dokładne.
Zachowano również historyczny status `unapproved` wewnątrz audytu kalibracji.

Approval zawiera `reviewed_by: autor pracy`, `split_id: chronological_v1`,
datę decyzji 2026-11-07, zakres pierwszego zbioru 800 przykładów,
`training_start: 2020-01-01T00:00:00+00:00`,
`training_end: 2023-12-31T20:00:00+00:00` i hashe oryginału.

| Symbol | Oryginalny profil ID, początek | Nowy profil ID, początek | phi / std |
|---|---|---|---|
| BTCUSDT | `d1db93b0929189da` | `acd7bd9018497822` | 0,65 / 0,65 |
| ETHUSDT | `9f8f7fb90e4b2e8b` | `dec8b59b55a47e0f` | 0,65 / 0,55 |

Hashe bajtów plików (różne od kanonicznego ID profilu):

| Plik | SHA-256 |
|---|---|
| BTC oryginalny | `771e67eef848dd7776342b4cc02e377f653cbb710ca2cd72328ff5e1ed3946ec` |
| BTC approved | `0969090924ab120340be56c6db111cfc0f167d00fe46c4dfd7f7bc020a1fa336` |
| ETH oryginalny | `f4ab56a0654f79f67addc295cc6c80189bd87554eebb1e0e9c71b136fd75a5b0` |
| ETH approved | `24c878e67b63c5f0d13787654ba75dd9dbd21ea7cf09cba4500511de22e7da33` |

`approval.json` zapisuje pełne ID, źródła, wcześniejszy plan i podstawę kontroli;
manifest wiąże hashe nowych plików. Konfiguracja wskazuje nowe kopie.
`require_production_ready()` przeszło z `diagnostic=False`.

Wykryta przeszkoda techniczna: dotychczasowy `validate_refinement_audit` wymagał
zewnętrznego `status=unapproved`, więc odrzucałby również formalnie zatwierdzoną
kopię. Dodano obsługę `approved` z kontrolą istniejącego schematu approval
i dokładnego splitu/granic. Nie zmieniono matematyki ani historycznego audytu.
Produkcja na `unapproved` nadal jest blokowana; potwierdzają to nowe testy.

## 3–6. Faktyczne liczebności, chronologia i brak przecieku

Liczby potwierdzono na zapisanych metadanych i osobnych plikach JSONL:

| Split | BTC real | ETH real | BTC synthetic | ETH synthetic | Razem |
|---|---:|---:|---:|---:|---:|
| Train | 129 | 129 | 220 | 220 | 698 |
| Validation | 18 | 18 | 0 | 0 | 36 |
| Test | 33 | 33 | 0 | 0 | 66 |
| Razem | 180 | 180 | 220 | 220 | 800 |

360 realnych / 440 syntetycznych to 45% / 55% całego zbioru. W samym train
syntetyki stanowią **63,04%** (440/698), a realne 36,96%. Każdy instrument
ma 400 przykładów. Jedynym sterownikiem liczebności jest `dataset_build.targets`.

Po zatwierdzeniu wykonano nowy preflight, przypinający nowe ID profili i SHA
konfiguracji. Pełne CSV dają na instrument 143/18/33 kandydatów oraz wybór
129/18/33. Zachowano `chronological_equal_count_strata_seeded_v1`,
`selection_seed=20261107`, kroki 60/120/120 i 120 świec.
Master seed **2027013501** nie kolidował z 54 historycznymi partiami
(618 unikalnych seedów przykładów), konfiguracją i profilami. Dodatkowy manifest
zatwierdzenia nie jest partią generującą seedy. Seedy 440 syntetyków wyznaczono
dotychczasowym `example_seed(master_seed,symbol,index)` bez zmian i ponowień.

Znana luka 2020-02-19 12:00 UTC pozostała w obu źródłach. Siatkę restartowano
po luce; żadne wybrane okno nie zawiera luki ani nie przekracza granicy splitu.
Nie interpolowano. Końcówki za krótkie na pełne okno opisuje nowy `plan.json`.

Rozkład rzeczywistych okien według roku pierwszej świecy, na instrument:

| Rok | Train | Validation | Test |
|---|---:|---:|---:|
| 2020 | 32 | 0 | 0 |
| 2021 | 33 | 0 | 0 |
| 2022 | 33 | 0 | 0 |
| 2023 | 31 | 0 | 0 |
| 2024 | 0 | 18 | 0 |
| 2025 | 0 | 0 | 19 |
| 2026 | 0 | 0 | 14 |

Wybrane zakresy UTC: train 2020-01-01 00:00 – 2023-12-30 12:00;
validation 2024-01-01 00:00 – 2024-12-25 20:00;
test 2025-01-01 00:00 – 2026-10-22 20:00. To pokrycie okien,
nie zmiana zatwierdzonych końców okresów w konfiguracji.

Validation/test są rozłączne w obrębie instrumentu i zawierają wyłącznie realne
dane. Train celowo ma częściowo nakładające się okna. BTC i ETH z tych samych
okresów są powiązane rynkowo; nie nazywamy ich niezależnymi obserwacjami.
Selekcja train i parametry generatora nie używają cech ani etykiet validation/test.
Późniejszy audyt jest opisowy i nie zmienił danych.

## 7. Integralność 800 obrazów, OHLC i etykiet

Każdy przykład ma 120 poprawnych, kolejnych świec 4h; etykietowanie analizuje
te same świece co renderer. W każdym JSONL są tylko `id`, `split`, `image`,
jedna instrukcja `pl-sr-v1` i obiekt `answer`. Ceny zapisano z dwoma miejscami
po przecinku bez pośredniego float przy serializacji. Algorytm S/R zachował
pełny 50-cyfrowy kontekst Decimal, ranking i limit 3+3; puste listy są dozwolone.

Dane modelu są w `splits/train.jsonl`, `splits/validation.jsonl`,
`splits/test.jsonl`. Nie ma wspólnego produkcyjnego JSONL do przypadkowego
wczytania wszystkich splitów jako treningu. Ścieżki obrazów są względne wobec
głównego katalogu zbioru. Symbol, źródło, profil, seed, reżimy, parametry,
indeksy, daty i hashe są oddzielnie w metadanych.

Wszystkie PNG mają 1024 × 768 i pochodzą z niezmienionego renderera bez poziomów
S/R. Produkcyjny weryfikator czyta zapisane OHLC, odtwarza każdy oryginalny PNG
i porównuje SHA bajtów. Tym samym wykluczono użycie overlays z 3.4.
Ponownie oblicza każdą etykietę i sprawdza jej dokładną serializację, JSONL,
metadane, ID, wszystkie hashe oraz pełny inwentarz bez dodatkowych plików.
Regeneruje również **wszystkie 440 syntetycznych OHLC** z approved i seedów,
porównując ceny, daty indeksu i metadane. Sprawdza realne indeksy i źródłowe CSV.

Taką pełną kontrolę wykonano przed atomowym rename, a następnie osobno
**po opublikowaniu**. Wynik `verification-postpublish.json`: 800/800 poprawnych,
800 odtworzonych PNG, 440 odtworzonych syntetyków, zero różnic renderera.
SHA manifestu zgadza się z wartością podaną wyżej. Awaria przed publikacją
nie pozostawia katalogu udającego gotowy zbiór; nadpisanie jest odrzucane.

Sprawdzono SHA-256 **9029 plików historycznych** z istniejących processed,
synthetic i diagnostics przed i po pracy: zero zmienionych lub brakujących.
Wyjściowy status Git i diff zachowano w katalogu kontrolnym; niezwiązanych
zmian autora nie cofano. Celową zmianą jest bieżąca konfiguracja i dokumentacja.

## 8. Duplikaty i podobieństwo

Nie ma identycznych kanonicznych OHLC ani identycznych PNG w 800 przykładach.
Nie ma kolizji seedów. 130 grup (323 przykłady) ma zbliżone zagregowane cechy:
ten sam split/źródło/symbol, zaokrąglone std, opis ruchu i liczby poziomów.
Występuje 35 takich grup w train real, 90 w train synthetic, 0 w validation,
5 w test. ID zapisano w `similar-characteristics.json`. To podobne statystyki,
nie dowód identyczności trajektorii.

Dodatkowo porównano **159 600 par tego samego instrumentu**, stosując korelację
120 log-Close po osobnym centrowaniu i normalizacji. Przy jawnym progu
Pearsona >= 0,995 znaleziono **0 par**. Wynik: `trajectory-similarity.json`.
Test nie porównuje knotów i ignoruje bezwzględną skalę cen; nie dowodzi
braku wszelkich rodzajów podobieństwa. Nie użyto go do selekcji ani regeneracji.

## 9. Różnorodność i jakość referencji

Łącznie zapisano **1581 wsparć i 1507 oporów**. Rozkłady liczby poziomów:

| Grupa | Liczba | Wsparcia 0 / 1 / 2 / 3 | Opory 0 / 1 / 2 / 3 |
|---|---:|---|---|
| Train real | 258 | 43 / 30 / 29 / 156 | 69 / 41 / 38 / 110 |
| Train synthetic | 440 | 117 / 55 / 46 / 222 | 107 / 40 / 51 / 242 |
| Validation real | 36 | 7 / 5 / 4 / 20 | 7 / 4 / 5 / 20 |
| Test real | 66 | 14 / 4 / 9 / 39 | 18 / 9 / 8 / 31 |

| Grupa | Brak wsparć | Brak oporów | Limit 3 wsparć | Limit 3 oporów | Ruch netto w górę / w dół |
|---|---:|---:|---:|---:|---|
| Train real | 16,67% | 26,74% | 60,47% | 42,64% | 143 / 115 |
| Train synthetic | 26,59% | 24,32% | 50,45% | 55,00% | 216 / 224 |
| Validation real | 19,44% | 19,44% | 55,56% | 55,56% | 24 / 12 |
| Test real | 21,21% | 27,27% | 59,09% | 46,97% | 28 / 38 |

W 158 oknach (19,75%) co najmniej dwie ceny odpowiedzi są odległe o nie więcej
niż końcowy ATR/2. Są jawnie wskazane w `audit.json`. Grupowanie skrajnych
ekstremów i ranking nie gwarantują minimalnej odległości między wszystkimi
końcowymi poziomami. Nie zmieniano zatwierdzonego algorytmu ani etykiet.

Zmienność oznacza próbne std 119 log-zwrotów Close–Close w oknie.
Poniżej średnia tej zmienności i jej próbne std między oknami:

| Grupa | Średnia std okna | Std między oknami |
|---|---:|---:|
| Train real | 0,014746 | 0,007156 |
| Train synthetic | 0,013812 | 0,004160 |
| Validation real | 0,012043 | 0,003010 |
| Test real | 0,011191 | 0,003860 |

Osobno dla treningu:

| Instrument / źródło | Średnia std okna | Std między oknami |
|---|---:|---:|
| BTC real | 0,012968 | 0,006105 |
| BTC synthetic | 0,012138 | 0,003578 |
| ETH real | 0,016523 | 0,007694 |
| ETH synthetic | 0,015486 | 0,004032 |

Dyspersja zmienności syntetyków wynosi około **58,6% BTC / 52,4% ETH**
dyspersji wybranego realnego treningu. To inne próbki i inna siatka niż dawne
raporty; nie należy traktować zmiany procentów jako poprawy generatora.
Train synthetic ma też więcej pustych list wsparć i bardziej symetryczny ruch
netto. Raport nie zmienił parametrów w odpowiedzi na te obserwacje.

Syntetyki: 127 okien z jedną fazą, 159 z dwiema, 154 z trzema.
Wystąpienia faz: consolidation 396, uptrend 186, downtrend 194, breakout 131.
Świece: consolidation 27 459 (52,01%), uptrend 11 444 (21,67%),
downtrend 11 831 (22,41%), breakout 2066 (3,91%). Pełne przejścia, rozkłady
ruchu i metryki osobno BTC/ETH są w `audit.json`.

## 10. Przegląd i ograniczenia

Przygotowano 16 oryginałów i 16 oddzielnych overlays z pełną diagnostyką
algorytmu: osobno instrument × cztery grupy split/źródło, przypadek medianowej
i maksymalnej zmienności. Kryterium stosowano dopiero po zbudowaniu zbioru.
To zestaw przeglądowy, nie losowa reprezentatywna próbka do estymacji rynku.
Obejrzano wstępnie dwa overlays (realny BTC i syntetyczny ETH); sprawdzono
czytelność i rozmieszczenie podpisów. Nie jest to niezależna ocena ekspercka
wszystkich 800 referencji. PNG z liniami są poza produkcyjnym katalogiem modelu.

Aktualne ograniczenia: uproszczone ścieżki śródswiecowe z 12 kroków, symetryczne
ogony, stacjonarna log-zmienność, ograniczona dyspersja, brak wspólnego procesu
BTC/ETH i luk cenowych syntetyków, zależność referencji od reguł ATR/ekstremów.
Statystyki porównawcze z treningiem nie są niezależną walidacją generatora.
Zgodność techniczna etykiet z regułami nie dowodzi eksperckiej poprawności
każdego poziomu. Oceny validation/test nie użyto do kalibracji lub selekcji train.

## 11. Testy i środowisko

Końcowy pełny przebieg: **233 testy zaliczone, 0 pominiętych, 0 błędów**,
122,016 s. Log: `tests-final.log`. Wcześniejszy przebieg 230 testów również
zakończył się sukcesem; po dodaniu trzech testów audytu uruchomiono pełny
zestaw ponownie. Nowa ścieżka ma 9 testów integracyjnych i 3 jednostkowe.

Testy obejmują zatwierdzenie i zachowanie pól, odrzucenie profilu diagnostycznego,
uszkodzony audyt/matematykę/approval, blokadę unapproved, małą pełną produkcję,
seedy i odtworzenie, liczebności i splity, nieaktualny plan, awarię renderera,
nadpisanie, uszkodzone PNG oraz JSONL nawet po ponownym hashowaniu.
Dotychczasowe testy granic, luk i duplikatów również przeszły.
Małe kalibracje w testach używają wyłącznie sztucznych fixture, nie rynku.

Windows 10 build 19045, CPython 3.13.15, Matplotlib 3.11.2,
renderer 1.0.0, etykietowanie `sr-extreme-first-1.0.0`, instrukcja `pl-sr-v1`.
Nie deklarujemy zgodności bajtowej innych wersji Matplotlib/fontów.
Weryfikator pozwala jawnie raportować takie różnice, zachowując kontrolę
etykiet i OHLC. SHA zapewnia integralność, a nie podpis autentyczności.

## 12–15. Dokumentacja, odtworzenie i następne decyzje

Uaktualniono README, opis generatora v1/v2, architekturę, format zbioru,
instrukcję PowerShell, README modułów datasets/charts/labeling i `.ai`.
Zachowano historyczne raporty części 1 i dawnych eksperymentów, bez nadawania
im wstecznie statusu produkcyjnego. Notatka w konfiguracji opisuje zatwierdzony
stan; parametry eksperymentu pozostają niezmienione.

[Dokładne polecenia PowerShell](INSTRUKCJA_POWERSHELL.md) rozdzielają approve,
preflight, build i verify. Ponowne wykonanie preflightu po publikacji zgłasza
oczekiwaną kolizję z zarezerwowanym master seedem. Nie zmieniono go; działanie
zabezpieczenia zapisano w `seed-reservation-check.json`. Odtwarzanie istniejącej
partii wykonuje `verify`, regenerując wszystkie przykłady bez publikacji nowego
eksperymentu. Katalogi wyników nie są nadpisywane.

Handoff kodu zawiera wszystkie manifesty/statystyki i 16 próbek. Osobny ZIP
danych zawiera kompletny lokalny zbiór. Oba mają inwentarz SHA i sumę obok;
nie zawierają `.venv`, cache, build, egg-info ani zbędnych historycznych danych.
Pełny zbiór można zweryfikować z kopii okien i profili bez oryginalnych dużych
CSV; flaga `--check-sources` dodatkowo porównuje oryginalne lokalne wejścia.

**Nie ma nierozwiązanego błędu technicznego blokującego niezależny audyt.**
Przed treningiem pozostają ocena raportu i zestawu przeglądowego, decyzja
o akceptacji ograniczeń referencji i generatora oraz osobny wybór VLM,
formatu adaptera i parametrów dostrajania. Żadnego z tych działań nie rozpoczęto.
