# Aktualny stan projektu

Aktualizacja: 2026-11-06. To opis stanu, nie zakaz realizacji kolejnych zleceń.
Przed rozpoczęciem pracy sprawdź, czy kod i konfiguracja nadal mu odpowiadają.

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
  zatwierdzony w konfiguracji; parametry i profile nie zostały zatwierdzone.
- CLI market-levels-calibrate i market-levels-compare-synthetic: kontrola okresu
  treningu, niezatwierdzone profile, rozłączne okna diagnostyczne bez luk,
  sprawdzanie manifestów oraz raport JSON/Markdown. Szczegóły i polecenia:
  [instrukcja](../docs/SYNTHETIC_CALIBRATION_COMPARISON.md).
- Jawny generator v2 (2.0.0): most Browna, normalizowana mieszanka Close 4h,
  stacjonarna log-zmienność, pięć wariantów i osobne strumienie RNG/profil v2.
  Domyślnie pozostaje v1. Ograniczona kalibracja pełnego modelu na kilku seedach,
  bez automatycznego zatwierdzenia. Tryb --reports zestawia warianty z identyczną
  referencją. [Opis v2](../docs/SYNTHETIC_GENERATOR_V2.md).
- Testy jednostkowe i integracyjne offline: ostatni pełny zestaw 151 testów OK
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
i 120 dla walidacji/testu, roboczo 800 wykresów, 45% rzeczywistych i 55%
syntetycznych, początkowo 1024 × 768 px. Nie są obecnie używane przez pobieranie.
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

data_processing/windows, labeling, datasets,
modeling, training, inference, evaluation i experiments zawierają przestrzeń
organizacyjną z README. Nie implementują jeszcze tych etapów.
Szczegółowe reguły planowanego etykietowania są w
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
