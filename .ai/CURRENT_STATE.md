# Aktualny stan projektu

Aktualizacja: 2026-11-09. To opis stanu, nie zakaz realizacji kolejnych zleceń.
Przed rozpoczęciem pracy sprawdź, czy kod i konfiguracja nadal mu odpowiadają.

Etap 4.1, część 1: autor zlecił audyt i lokalny pilot VLM. Potwierdzono RTX 3060 Ti
8 GB, Windows 10/19045, CC 8.6 i natywne BF16 w rzeczywistym forward/backward
PyTorch. WSL2 ma tylko docker-desktop; Ubuntu nie instalowano. Osobny Python
3.12.12 i stos torch 2.10.0+cu128 / Transformers 5.3.0 są pod D:/ml-envs,
wagi poza repo w D:/ml-cache/market-levels/hub. Projektowego .venv nie zmieniano.
Oba przypięte checkpointy Qwen3-VL-2B-Instruct i Qwen3.5-2B wykonały po osiem
validation przy 1024x768/768 tokenów i 704x512/352 tokenów. Wszystkie odpowiedzi
S/R otaczają JSON Markdownem: 0/8 poprawnych w każdym wariancie, bez naprawiania.
To pilot, nie pełna walidacja. Qwen3-VL wykonał jeden krok QLoRA na czterech train:
skończone loss/gradienty, aktualizacja adaptera, obraz uczestniczy w obliczeniach.
Globalny peak 7923/8192 MiB wymaga dalszej kontroli pamięci; pełny trening nie
jest potwierdzony. Treningu Qwen3.5 nie wykonano. Rekomendacja kandydata A jest
warunkowa, bez ostatecznego wyboru. Nie użyto testu ani zewnętrznej inferencji.
317 testów projektu i 3 osobne testy maskowania OK. Wszystkie 12 771 historycznych
plików, w tym 3212 plików zbioru produkcyjnego, mają niezmienione SHA-256 i liczbę.
[Raport](../docs/vlm/RAPORT_4_1_WYBOR_MODELU_CZ1.md),
[PowerShell](../docs/vlm/INSTRUKCJA_POWERSHELL_4_1.md).

Refaktoryzację src wraz z końcową kontrolą zapisano i wypchnięto jako 4483906.
Konfiguracja ma teraz punkt wejścia experiment.json (51 linii) i pięć fragmentów
w configs/data, synthetic i datasets. Shared.configuration składa te same wartości,
zachowuje pełne JSON-y i samodzielne snapshoty; integralność uwzględnia fragmenty.
Algorytmy, ustawienia badawcze i renderer pozostają bez zmian.
Kontrola podziału: 300 testów OK bez pominięć; zachowano 286 wcześniejszych
testów i 971 asercji. Złożony JSON ma identyczne 6183 bajty jak przed podziałem;
30 porównań generowania/renderowania zgodnych. Istniejące 800 przykładów
zweryfikowano z kontrolą źródeł, 440 odtworzonymi syntetykami i 800 identycznymi PNG.
[Zasady konfiguracji](../configs/README.md),
[raport podziału](../docs/refactoring/RAPORT_REFAKTORYZACJI_CONFIGS.md).

Zakończono reorganizację src: core/shared oraz powtarzalne domain, workflows,
io, reporting i config. Runner refinement jest w experiments/refinement;
CLI i parametry badawcze zachowano. Wewnętrzne ścieżki dawnych modułów zmieniły
się; mapę podaje dokumentacja. Graf importów, również lokalnych, jest bez cykli.
286 testów OK, bez pominięć; 28 przypadków generatorów zgodnych ze starym kodem,
identyczne 32 PNG pilotażu i 32 nakładki, pełne odtworzenie 800 PNG/etykiet
i 440 syntetyków bez różnic, ze sprawdzeniem źródeł. Wszystkie 12 771 plików
w data/results mają ten sam inwentarz i SHA-256. Archiwum stycznia 2020
porównano offline na kopiach: CSV, raporty i manifest zgodne. Bez nowego
eksperymentu rynku, treningu i inferencji.
[Architektura](../docs/ARCHITECTURE.md),
[raport i ograniczenia kontroli](../docs/refactoring/RAPORT_REFAKTORYZACJI_SRC.md).
Poniższe opisy wcześniejszych etapów zachowują kontekst historyczny.

Najnowsze wykonanie: etap 3.5, część 2. Dwa nowe profile full-refined approved,
bez zmiany parametrów i oryginałów; lokalny kompletny zbiór
`data/datasets/ds35-800-20261107-a`, dokładnie 800 przykładów (698/36/66),
360 realnych i 440 syntetycznych, validation/test tylko realne.
Pełne odtworzenie 800 PNG/etykiet i 440 syntetyków przeszło przed i po publikacji.
233 testy OK, 0 pominiętych i błędów; 9029 historycznych plików bez zmian.
16 próbek z oddzielnymi overlays w `results/diagnostics/ds35-review-20261107-a`.
Produkcję i zatwierdzenie autor jawnie zlecił 2026-11-07; stare ograniczenie
części 1 do małej próby dotyczyło tamtej iteracji. Nie rozpoczęto treningu.
[Aktualny raport](../docs/datasets/RAPORT_3_5_CZ2.md).

Etap 3.6 część 1: działa `evaluation/` i CLI `market-levels-evaluate`
(evaluate/compare/verify), protokół sr-eval-v1. Główne micro-F1 przy 0.5 ATR,
pomocnicze 0.25 i 1.0 ATR; dopasowanie max TP/min błąd/remisy indeksów.
Domyślnie validation; test wyłącznie jawnie, train odrzucany. Surowy JSON
nie jest naprawiany, ID muszą być kompletne. Demo ev36-20261107-a to wyłącznie
ręczne fixture A/B, nie rzeczywisty VLM. Read-only adapter sprawdzono na
36 produkcyjnych referencjach validation, bez predykcji. 277 testów OK,
0 pominiętych/błędów; 3245 chronionych plików bez zmian. Nie wykonywano
inferencji, wyboru modelu ani treningu. [Protokół](../docs/evaluation/PROTOKOL_3_6.md),
[raport](../docs/evaluation/RAPORT_3_6_CZ1.md).

## Działa

- Pozyskiwanie rzeczywistych archiwów Binance Vision spot 4h, SHA-256 i CHECKSUM.
- Parsowanie ZIP, walidacja OHLC i szeregów, CSV, raporty JSON i manifest.
- CLI market-levels-download oraz python -m market_levels.cli.download.
- Aktywna konfiguracja JSON: zakres miesięcy, symbole oraz download.output, offline, strict_gaps i daily_fallback.
- Walidacja obsługiwanego źródła, rynku, interwału i symboli; błędy konfiguracji kończą wykonanie przed zapisem.
- Generator niezależnych syntetycznych serii 120 świec / 12 kroków, 1–3 fazy,
  osobne seedy, kalibracja z jawnym okresem, diagnostyka i atomowy zapis partii.
- CLI market-levels-generate-synthetic i sekcja synthetic; domyślnie brak profili
  blokuje wykonanie. Tryb roboczy wymaga --diagnostic. Zatwierdzanie profilu
  wymaga jawnych granic treningu i decyzji autora. Podział chronological_v1 jest
  zatwierdzony w konfiguracji; historyczne profile pozostają niezatwierdzone,
  a nowe kopie dwóch full-refined zatwierdzono do pierwszego zbioru 800.
- CLI market-levels-calibrate i market-levels-compare-synthetic: kontrola okresu
  treningu, niezatwierdzone profile, rozłączne okna diagnostyczne bez luk,
  sprawdzanie manifestów oraz raport JSON/Markdown. Szczegóły i polecenia:
  [instrukcja](../docs/SYNTHETIC_CALIBRATION_COMPARISON.md).
- Jawny generator v2 (2.0.0): most Browna, normalizowana mieszanka Close 4h,
  stacjonarna log-zmienność, pięć wariantów i osobne strumienie RNG/profil v2.
  Domyślnie pozostaje v1. Ograniczona kalibracja pełnego modelu na kilku seedach,
  bez automatycznego zatwierdzenia. Tryb --reports zestawia warianty z identyczną
  referencją. [Opis v2](../docs/SYNTHETIC_GENERATOR_V2.md).
- Testy jednostkowe i integracyjne offline: historyczny zestaw 151 testów OK
  (106 po poprawce sprzątania Windows, 10 refinement, 5 przenośności audytu, 9 skryptu porównań, 6 MAX_PATH, 5 świeżych seedów i 10 publikacji;
  w tym rzeczywista blokada Windows).
  [Bieżący raport](../docs/SYNTHETIC_V2_IMPLEMENTATION_REPORT.md);
  [wcześniejsze wdrożenie generatora](../docs/SYNTHETIC_IMPLEMENTATION_REPORT.md).

## Ważne decyzje organizacyjne

Stare moduły src.download_data i src.validate_data zostały usunięte na prośbę
autora. Stare polecenie nie jest już obowiązującym interfejsem.
Kod przeniesiono z market_levels/data do market_levels/data_processing.
Nie przywracaj dawnego układu na podstawie starszych raportów lub załączników.
configs/experiment.json steruje pobieraniem; wcześniejsze opisy „JSON jest tylko
zapisem ustaleń” są nieaktualne.

## Parametry i dane

Aktualne wartości sprawdzaj w [experiment.json](../configs/experiment.json).
Zatwierdzono Binance Vision spot, BTCUSDT i ETHUSDT, 4h i zakres
2020-01–2026-10. Autor potwierdził pobranie pełnej historii (82 archiwa/symbol).
Odczyt lokalnych CSV potwierdził po 14 975 świec i jedną lukę w obu instrumentach:
2020-02-19 12:00 UTC. Nie interpolowano. SHA-256 wszystkich siedmiu plików
w processed/ pozostały bez zmian podczas wdrożenia generatora.

Parametry przyszłego eksperymentu to 120 świec/wykres, przesunięcia 60 dla treningu
i 120 dla walidacji/testu, zatwierdzone 800 wykresów, 45% rzeczywistych i 55%
syntetycznych, 1024 × 768 px. Nie są używane przez pobieranie, lecz przez budowę zbioru.
Model oraz hiperparametry treningu nie zostały zatwierdzone.
Podział chronologiczny jest zatwierdzony: trening 2020–2023, walidacja 2024,
test 2025–2026-10. Dokładne granice otwarcia świec UTC włącznie są w konfiguracji.
Potwierdzono po 8765/2196/4014 świec dla obu instrumentów, razem po 14 975.
Trening ma maksymalnie 72 rozłączne okna 120 świec; sprawdzono selekcję 60.
Podczas implementacji v1 wykonano 5 diagnostycznych serii BTC i 5 ETH, seed 20261103, bez danych
rynkowych w kalibracji. Nie wygenerowano docelowego zbioru; kontrola wizualna czeka
na renderer. Parametry projektowe i diagnostyczne opisuje
[SYNTHETIC_GENERATOR.md](../docs/SYNTHETIC_GENERATOR.md).
Autor wykonał kalibrację v1 i pełną diagnostykę 60+60 BTC/ETH. Lokalne raporty
0c2d0b24557f20945757af65 i 0fa65cfe0c52f41cca3c7f51 potwierdzają problemy
proporcji świec, ogonów i zróżnicowania zmienności. Nie modyfikowano tych wyników.
V2 sprawdzono podczas wdrożenia na sztucznej referencji. Później autor wykonał
kalibrację v2 i małą próbę 2 BTC + 2 ETH; opublikowana partia jest poprawna,
mimo pierwotnego WinError 32 przy sprzątaniu pustego `.synthetic-4terleld`.
Naprawiono to wspólnym kontekstem publikacji: ponowienia blokad, ostrzeżenie
po sukcesie, zachowanie pierwotnego błędu przed publikacją. Bez zmian matematyki
i istniejących wyników. [Poprawka Windows](../docs/WINDOWS_STAGING_CLEANUP_FIX.md).
W tej sesji nie ponawiano kalibracji ani pełnej oceny wariantów.
Porównanie z treningiem nie stanowi niezależnej walidacji. Raport narzędzi v1:
[CALIBRATION_COMPARISON_REPORT.md](../docs/CALIBRATION_COMPARISON_REPORT.md).
Najnowsze wdrożenie i wykonane testy:
[SYNTHETIC_V2_IMPLEMENTATION_REPORT.md](../docs/SYNTHETIC_V2_IMPLEMENTATION_REPORT.md).

Aktualizacja 2026-11-05, po powyższych etapach: autor wykonał również serię
2160 diagnostyk V1 i pięciu wariantów V2 na trzech seedach. Nie zmieniano tych
wyników. Dodano `bridge_volatility` oraz osobne CLI
`market-levels-refine-v2-volatility`, zmieniające tylko phi i stacjonarne std.
Audyt zamraża profil źródłowy i wiąże nowy profil z wariantem. Raporty rozróżniają
full-original/full-refined/bridge_volatility-refined. W tej iteracji wykonano
116 testów i natywną małą ścieżkę PowerShell na sztucznych danych obu symboli;
nie uruchamiano kalibracji rynku ani oceny 60 przykładów. Cztery empiryczne
profile i decyzja o akceptacji pozostają do wykonania przez autora.
[Bieżący raport](../docs/RAPORT_REFINEMENT_V2.md),
[procedura PowerShell](../docs/INSTRUKCJA_REFINEMENT_POWERSHELL.md).

Poprawka przenośności audytu: ponownie obliczone floaty wyników celu mają
rel_tol=1e-12 i abs_tol=1e-18; struktura i typy wyników pozostają dokładne.
Bez zmian matematyki, konfiguracji i formatów. Cztery istniejące profile
refinement BTC/ETH wczytano poprawnie bez zmiany bajtów ani hashów.
Nie ponawiano kalibracji. [Opis poprawki](../docs/REFINEMENT_AUDIT_PORTABILITY_FIX.md).

Naprawiono odtworzony błąd importu spowodowany brakiem całego katalogu synthetic:
odzyskano 18 brakujących plików z ostatniej kompletnej migawki z kontrolą SHA.
Obecnie są dostępne cztery empiryczne profile refinement i 12 historycznych
raportów V1/full-original. Oficjalny skrypt scripts/run_refinement_comparison.ps1
kontroluje zależności, wykonuje małą próbę lub jawny RunFull, zapisuje etapy
i obsługuje wznowienie. CheckOnly, smoke 8 serii i wznowienie sprawdzono na
istniejących profilach z wyjściem w temp. Nie uruchamiano pełnych 720 serii.
Nie ponawiaj kalibracji. [Procedura](../docs/INSTRUKCJA_POWERSHELL.md),
[diagnoza](../docs/RAPORT_NAPRAWY_IMPORTU.md), [testy](../docs/RAPORT_TESTOW.md).

Domyślna nazwa przebiegu porównania została skrócona do rc-<12 hex> z pełnym
UUID w run.json. Przed generowaniem sprawdzane są długości ścieżek Windows obu
wariantów, stagingu i opublikowanych plików. Limit: <260 jednostek UTF-16.
136 testów i mały smoke/wznowienie w temp przeszły; bez pełnego eksperymentu.
[Poprawka długości ścieżek](../docs/WINDOWS_REFINEMENT_PATH_FIX.md).

Autor potwierdził ukończenie porównania na trzech znanych seedach. Przygotowano
osobny run_refinement_fresh_seeds.ps1 na 20261201/20261211. Generuje wszystkie
cztery grupy, używa istniejących ośmiu profili, a stare raporty tylko w preflight.
Wykonano jedynie smoke 32 serie i wznowienie w temp; 141 testów OK.
Pełne 960 serii pozostaje do świadomego uruchomienia autora. Tabele BTC/ETH
nowej próby nie łączą starych seedów. To stabilność symulacji na treningu,
bez akceptacji wariantu i bez nowej kalibracji. [Procedura](../docs/FRESH_SEEDS_POWERSHELL.md).

Autor ukończył SmokeTest świeżych seedów (32 serie) po ręcznym zabezpieczeniu
etapu, którego publikację przerwał WinError 5. Gotowych wyników nie zmieniano.
Wspólne publish_directory ponawia teraz atomowy rename partii i raportów:
4 próby, 0.05/0.15/0.30 s, wyłącznie konflikty dostępu, bez regeneracji.
Wznowienie nie przyjmuje manifestów/raportów z pozostałości stagingu.
151 testów OK i mała osobna próba w temp; pełnych 960 serii nie uruchamiano.
[Raport i polecenia](../docs/WINDOWS_PUBLICATION_RETRY_FIX.md).

## Dopiero planowane

modeling, training i inference obsługują ograniczoną diagnostykę 4.1 opisaną
powyżej; pełny trening pozostaje planowany. Experiments/refinement zawiera obecnie
istniejący koordynator przeniesiony z CLI, bez nowego frameworka eksperymentów.
Szczegółowe reguły etykietowania są w
[ARCHITECTURE.md](../docs/ARCHITECTURE.md); ustalenia autora w
[DECYZJE_3_3.md](../docs/DECYZJE_3_3.md).

## Audyt i renderer MVP (2026-11-06)

- Działa nowy audyt read-only i renderer `charts/` (CLI `market-levels-audit-charts`),
  z opcjonalnym Matplotlib `[charts]`. Pilotaż jest diagnostyczny i niezatwierdzony.
  Analiza obejmuje pięć istniejących pełnych partii V2-full-refined, 600 serii;
  wyniki i procedura: [renderer](../docs/charts/RAPORT_RENDERERA.md),
  [PowerShell](../docs/charts/INSTRUKCJA_POWERSHELL.md).
  Autor wskazał V2-full-refined jako kandydata; nie zmieniano matematyki ani profili.
  Potwierdził ukończenie porównania na pięciu seedach; starsze opisy oczekiwania
  na pełne wykonania poniżej i powyżej są zapisami wcześniejszych etapów.
  Realny parser kończy na pierwszym znaczniku czasu po treningu; SHA bezpieczeństwa
  obejmuje całe pliki źródłowe. Nie analizuje OHLC validation/test.
  Wybicia są wyłącznie proxy diagnostycznym; nie stanowią etykiet modelu ani S/R.

Końcowe wykonanie: `results/diagnostics/dc-20261106-c/`, 32 PNG i pełny audyt.
169 testów OK natywnie na Windows (18 nowych); komplet 32 obrazów odtworzono
z identycznymi SHA. Szczegóły: [testy](../docs/charts/RAPORT_TESTOW.md).

## Etykietowanie poziomów (3.4)

Etap 3.4 (2026-11-06): działa `labeling/` oraz CLI `market-levels-label-pilot`.
Etykietowano wszystkie 32 istniejące okna w `results/diagnostics/sr-20261106-a/`;
57 wsparć i 71 oporów, 739 ekstremów → 708 reakcji. Brak wsparć w 9 oknach,
brak oporów w 6, brak obu list w 0; bez kolizji zaokrągleń. SHA-256 źródeł
bez zmian, 32 oryginalne i 32 nowe PNG odtworzono z identycznymi hashami.
Algorytm wybiera najbardziej skrajne ekstremum najpierw; nie maksymalizuje
liczby reakcji. Nie wykorzystuje metadanych generatora. Osobne PNG z liniami
są tylko diagnostyczne. Profile pozostają unapproved, nie wykonano 3.5;
zamknięcie 3.4 wymaga decyzji autora po ręcznej ocenie.
Pełne testy: 199 OK, 0 niezaliczonych (169 istniejących + 30 nowych).
[Raport](../docs/labeling/RAPORT_3_4.md), [PowerShell](../docs/labeling/INSTRUKCJA_POWERSHELL.md).

## Etap 3.5 — część 1

Etap 3.5, część 1 (2026-11-07): działają `data_processing/windows`,
`datasets` i CLI `build_dataset` preflight/smoke/verify. Pełne CSV dają po
143/18/33 kandydatów i wybrano w planie po 129/18/33. Selekcja train:
chronologiczne warstwy, jeden indeks na warstwę, seed 20261107. Liczebności
sterowane wyłącznie przez `dataset_build.targets`; historyczne pola sumy
i udziałów opisują założenie. Profile full-refined sprawdzono, bez zmian:
oba `unapproved`, produkcja nadal zablokowana. Master seed planu 2027013501
bez kolizji z 54 lokalnymi manifestami. Zapisano tylko 8 diagnostycznych
przykładów ze starego pilotażu, `split: null`, bez nowych OHLC.
221 testów OK, 0 błędów; wcześniejsze 32 PNG i wyniki 3.4 zweryfikowane
z odtworzeniem. Nie zbudowano finalnych 800 obrazów; wymagane decyzja autora
o profilach i osobne polecenie produkcji. [Raport](../docs/datasets/RAPORT_3_5_CZ1.md),
[PowerShell](../docs/datasets/INSTRUKCJA_POWERSHELL.md).

## Znane ograniczenia

- Lokalny CHECKSUM jest używany ponownie bez odświeżania z serwera.
- iter_months wykorzystuje assert; uruchomienie z -O może zmienić walidację.
- Fallback zależy od lokalnej daty komputera.
- Ponowny rzeczywisty run nadpisuje CSV i raporty.
- Strict-gaps zapisuje CSV i raport, potem przerywa przed nowym manifestem; wcześniejszy manifest może pozostać.
- Konfiguracja obsługuje obecnie tylko Binance Vision spot 4h i dwa wskazane symbole.
- Podczas refaktoryzacji nie testowano rzeczywistego pobierania i fallbacku na serwerze; HTTP testowano z mockami.
- Weryfikacja wykonana na Windows i Pythonie 3.13.15. Minimalna deklaracja to Python 3.10; nie oznacza wykonania testów na wszystkich wersjach.
- Stan repozytorium Git i zdalnej gałęzi sprawdzaj przed operacjami publikacji.

handoff/ zawiera historyczne paczki do przekazania, a nie aktywne źródła projektu.
Zmiana kodu lub instrukcji nie aktualizuje automatycznie istniejącego ZIP.

## Publikacja i licencja

Autor zlecił utworzenie publicznego repozytorium GitHub
W-Pawlik/market-levels-multimodal-finetuning oraz publikację kodu na MIT.
Tekst licencji jest w LICENSE. Zastrzeżenia dotyczące danych pozostają
w docs/LICENCJA_DANYCH.md. Dane, lokalne raporty, handoff, środowiska i artefakty
budowania są wykluczone z publikacji. Potwierdzenie zdalnego stanu wymaga
sprawdzenia GitHub i git status; sam ten zapis nie jest dowodem udanego push.
