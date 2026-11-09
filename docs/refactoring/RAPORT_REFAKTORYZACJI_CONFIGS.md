# Refaktoryzacja configs bez zmiany parametrów i algorytmów

Data kontroli: 2026-11-09T20:47:11+01:00. Referencja: commit
`4483906bcdde8982ced7d929cf56774b81cd4bac` — zakończona reorganizacja src wraz
z raportem niezależnej kontroli. Ten commit wypchnięto na origin/main; stan
zdalnej gałęzi potwierdzono przez git ls-remote. Przed podziałem konfiguracji
drzewo robocze było czyste. Podział configs pozostaje osobnym zestawem zmian.

## Wynik

**Nie wykryto zmiany wyników algorytmów, etykietowania, ewaluacji ani renderowania
w wykonanych kontrolach.** Parametry, ich typy i kolejność pozostały identyczne.
Nie modyfikowano produkcyjnych danych, profili, etykiet i manifestów.

Plik wejściowy configs/experiment.json ma **51 linii zamiast 276**. Rozbudowane
sekcje są w pięciu plikach:

```text
configs/
  experiment.json
  data/chronological_split.json
  synthetic/generation.json
  synthetic/calibration.json
  synthetic/refinement.json
  datasets/build.json
```

V1 i V2 korzystają z jednego pliku generation.json. Schemat rekordu zbioru
dataset_example.schema.json pozostał na swoim miejscu. Szczegóły i wskazanie
aktywnych oraz historycznych pól: [configs/README.md](../../configs/README.md).

## Zachowane kontrakty

Shared.configuration składa wyłącznie jawne odwołania pól głównych $file/$section.
Nie dodano dziedziczenia, rekurencyjnego scalania, nadpisywania środowiskiem,
automatycznego wyszukiwania plików ani zależności zewnętrznych.

- --config, domyślna ścieżka oraz pierwszeństwo jawnych argumentów CLI pozostały.
- Wyłącznie $file jest względny wobec pliku wejściowego. Output, profile i historia
  pozostają względne wobec CWD. Nie przeliczano ich względem fragmentów.
- Pełne JSON-y, UTF-8-sig, kolejność pól/list i typy liczb pozostały obsługiwane.
  Dla pełnego pliku snapshot zachowuje oryginalne bajty, również BOM i CRLF.
- Walidacja pozostaje przy właściwych konsumentach; pobieranie nie zaczęło
  walidować ustawień generatora. Nie zmieniono wartości domyślnych dataclass.
- Snapshot nowego zbioru zawiera pełny config.json bez zależności od fragmentów.
  SourceLedger i preflight runnera przypinają wszystkie pliki konfiguracji,
  w tym wspólny generation.json tylko raz. Zmiana fragmentu unieważnia nowy plan.
- Zaktualizowano czytniki obszarów, skrypt create_dataset_handoff i 8 odczytów
  konfiguracji w konstrukcji testowych wejść. Oczekiwań i fixture nie osłabiono.
- Zaktualizowano trzy przykłady PowerShell, które wcześniej czytały root JSON
  przez Get-Content/ConvertFrom-Json. Teraz używają tego samego czytnika co CLI.

Po złożeniu aktualny dokument oraz jego pełny zapis są **bajtowo identyczne
z konfiguracją sprzed podziału: 6183 bajty**, SHA-256:
`73df3d1e0a00947f476d1597e803c830baf0cf19c2593b7f403be5f7752c7a5a`.
To kontrola wszystkich pól, również historycznych; nie ograniczono jej do
wybranych parametrów generatora. Nie aktywowano dotychczas nieużywanych pól.

## Historyczny hash konfiguracji

Pierwsza kontrola istniejącej produkcji wykryła przewidywalną zależność:
plan przypinał SHA starego pełnego configs/experiment.json. Zastąpienie go
odwołaniami zmienia surowe bajty pliku wejściowego. Pozostawienie wyłącznie
starego sprawdzania hashy zablokowałoby verify --check-sources mimo tych samych
wartości parametrów. Nie zmieniono w odpowiedzi manifestu, źródłowego zbioru ani hashy.

Dodano wąski adapter odczytu w datasets/workflows/verification.py::_check_sources:
przy weryfikacji istniejącego zbioru rozdzielona konfiguracja może zastąpić dawny
plik tylko wtedy, gdy zapisany historyczny config.json ma przypięty SHA i da się
odtworzyć **dokładnie jego bajty** przez złożenie obecnej konfiguracji.
Nie wystarcza przybliżenie float, porównanie wybranych pól ani równość arytmetyczna
1 i 1.0. Błąd odczytu lub inny wynik nadal kończy się pierwotnym błędem źródła.

Pozostałe źródła nadal wymagają dokładnego SHA surowych bajtów. Fragmenty
przypięte przez nowe plany również pozostają bajtowo ścisłe: nawet dodatkowy
newline unieważnia ich hash. Budowa z nieaktualnego preflightu nie korzysta
z tego adaptera. Historycznych checkpointów ani ochrony SHA kodu nie migrowano.
Jest to dostosowanie reprezentacji konfiguracji, nie zmiana matematyki lub
formatu danych. Pokrywają je testy poprawnego odczytu i odrzucania zmian.

## Kontrole faktycznie wykonane

Windows, CPython **3.13.15**, Matplotlib **3.11.2**. Dwie osobne kopie kodu
i instalacje editable w dwóch venv; głównego środowiska projektu nie zmieniono.

| Kontrola | Wynik |
| --- | --- |
| Pełny końcowy zestaw | **300/300 OK**, 0 pominiętych, 0 błędów, 148.581 s |
| Zachowanie testów | **286/286** wcześniejszych metod i **971** dotychczasowych wywołań self.assert* bez zmian AST asercji |
| Fixture regresyjne | Wszystkie wcześniejsze pliki fixtures bajtowo niezmienione |
| Nowe testy | 14: 8 formatu/odczytu, 2 integralności, 3 integracji zbioru i 1 preflightu runnera |
| Domyślny CLI | Download i generate_synthetic --dry-run przed/po: identyczne kody, stdout i stderr |
| PowerShell | Trzy poprawione bloki odczytu z dokumentacji wykonane natywnie, zgodne granice UTC, bez błędów |
| Algorytmy w źródłach | Wszystkie pliki domain, core, evaluation oraz renderer i overlays pozostają bajtowo niezmienione |

Zmiany istniejącego src obejmują wyłącznie 12 plików czytników i koordynacji
konfiguracji/integralności oraz dodany shared/configuration.py. Kod testowanej
kopii src porównano z końcowym lokalnym src: identyczny. Po pełnych testach
zmieniono tylko dokumentację wyników.

Nowe kontrole obejmują przeniesienie snapshotu bez fragmentów, CWD, BOM/CRLF,
typy i kolejność, brakujące/błędne odwołania, brak dodatkowej walidacji innego
obszaru, unieważnianie planu po zmianie fragmentu, przenośny mały zbiór,
zgodność źródła historycznego po podziale i wykrycie zmiany wartości/typu,
oraz nadal ścisłe SHA nowych fragmentów i pozostałych plików.
Dotychczasowe testy Windows, retry, blokad, wznowienia i -I też nie były pomijane.

## Porównanie przed/po

W osobnych procesach załadowano pełną konfigurację referencyjną i bieżącą
konfigurację z fragmentami. Porównano kompletne ustawienia pobierania,
generatorów, kalibracji, refinementu, chronologii i budowy zbioru.

Wykonano **30 przypadków**: oba instrumenty, V1 i sześć wariantów V2 na seedach
15485863/67867967 oraz po jednym V2-full-refined z istniejących zatwierdzonych
profili. Zgodne są surowe OHLC i daty, pełne metadane, etykiety, diagnostyka,
metryki, CSV, PNG 1024×768, osobne nakładki i JSONL.

Porównano też pełny read-only plan budowy, wszystkie wybrane okna/ID i parametry.
Aktywny master seed jest już zarezerwowany w historii, więc oryginalny kod
prawidłowo odrzucił próbę ponownego planu. Do porównania planów przygotowano
wyłącznie tymczasowe kopie konfiguracji z tym samym wolnym testowym seedem
3141592653. Aktywnej konfiguracji i danych nie zmieniano; planu nie publikowano
i nie budowano z niego zbioru.

Z planów wyłączono wyłącznie jawnie wskazane rekordy ścieżek/SHA plików
konfiguracji oraz odpowiadający file_count: wejście ma teraz 6 plików zamiast 1.
Weryfikowano osobno ich rzeczywiste hashe. Pozostałe dane porównano dokładnie,
bez tolerancji liczbowej i normalizacji PNG. Cały wynikowy dokument porównawczy
ma w obu wersjach ten sam SHA:
`665d8809fc738beef70fa009b55604521e8b0915e50b8a99e8e970cc7c7c0485`.

## Istniejący zbiór produkcyjny

Wykonano aktualnym kodem z izolowanego venv, na oryginalnych danych wyłącznie
odczytowo, z własnym TEMP:

```powershell
python -B -m market_levels.cli.build_dataset verify --output data/datasets/ds35-800-20261107-a --check-sources
```

**800/800** przykładów, podział **698/36/66**, **440/440** syntetyków odtworzonych,
**800/800** PNG identycznych, 0 różnic renderera. Sprawdzono źródłowe CSV i
przypięte źródła, profile, etykiety, pochodzenie, JSONL, manifesty, chronologię
i reguły rozłączności. Nie użyto allow-renderer-difference.
SHA manifestu pozostał:
`0f9093fbdcbd39243fcf802bfdd723cb913b15838aa4a3cc469787d5e7e462d0`.

Nie wykonywano build/approve na rzeczywistych danych, kalibracji rynku,
pełnych eksperymentów, treningu ani inferencji. Małe produkcje w testach
wykorzystywały wyłącznie sztuczne fixture wewnątrz kopii tymczasowej.

## Integralność i sprzątanie

Przed zmianami zapisano inwentarz względnych ścieżek, rozmiarów i SHA-256
wszystkich **12 803 plików data/results/handoff**, w tym 12 779 plików danych
i wyników oraz 24 plików handoff. Przed sprzątaniem: 0 dodanych, usuniętych
i zmienionych plików. Aktywne zatwierdzone profile i stare manifesty pozostały nietknięte.

Wszystkie kopie, dwa środowiska, lokalne cache, porównawcze PNG/CSV/JSONL,
logi i inwentarze utworzono pod nowym oznaczonym katalogiem `C:\Users\wojte\AppData\Local\Temp\mlcfg-ztmers1q`.
Przed sprzątaniem zinwentaryzowano 11276 pozostałych plików, 371624257 bajtów;
fingerprint listy z wyłączeniem pliku własnego inwentarza: `c39de7e2af7c712b5de52ef43db564c2e9f1d8d66f0e7080df67f515454efbe5`.
Pliki TemporaryDirectory uprzątnięte wcześniej przez testy nie są doliczone.
Nie sprzątano wcześniejszych katalogów tymczasowych ani globalnych cache.

**Sprzątanie zakończone:** cały katalog bieżącej iteracji usunięto po sprawdzeniu pełnej ścieżki, OWNER.json i braku symlinków/junctionów. Dwa venv, cache i pliki porównań nie pozostały w projekcie.

Ponowna kontrola po sprzątaniu:

```json
{
  "before_files": 12803,
  "after_files": 12803,
  "added": [],
  "removed": [],
  "changed": []
}
```

Git HEAD nadal `4483906bcdde8982ced7d929cf56774b81cd4bac`. Zmiany configs są lokalnym, osobnym zestawem: 42 zmienionych/nowych plików źródeł, konfiguracji, testów i dokumentacji; nie utworzono drugiego commita ani nowej paczki danych. Wyniki testów nie dodały plików do data/results/handoff.

## Zakres i ograniczenia

Wyniki powyżej wykonano w tej iteracji. Poprzedni pełny audyt reorganizacji src
pozostaje historycznym [raportem](RAPORT_KONTROLI_PO_REFAKTORYZACJI.md).
Nie deklarujemy nowej niezależnej walidacji ekonomicznej generatora ani VLM.
Nie sprawdzano rzeczywistego HTTP, GPU, innych platform i wersji Pythona.
Nie rozszerzano tolerancji, nie zmieniano wzorców ani decyzji badawczych.
Podział zmienia fizyczne położenie parametrów i listę źródeł konfiguracji;
nie zmienia ustawień przekazywanych algorytmom.
