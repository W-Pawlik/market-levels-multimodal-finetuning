# Aktualny stan projektu

Aktualizacja: 2026-11-03. To opis stanu, nie zakaz realizacji kolejnych zleceń.
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
- Testy jednostkowe i integracyjne offline: ostatni pełny zestaw 77 testów OK.
  [Bieżący raport](../docs/CALIBRATION_COMPARISON_REPORT.md);
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
Wykonano tylko 5 diagnostycznych serii BTC i 5 ETH, seed 20261103, bez danych
rynkowych w kalibracji. Nie wygenerowano docelowego zbioru; kontrola wizualna czeka
na renderer. Parametry projektowe i diagnostyczne opisuje
[SYNTHETIC_GENERATOR.md](../docs/SYNTHETIC_GENERATOR.md).
Narzędzia kalibracji/porównania sprawdzono na danych sztucznych; nie uruchomiono
nowej kalibracji rynku ani pełnej próbki 60+60. Właściwe uruchomienie wykona autor.
Porównanie z treningiem nie stanowi niezależnej walidacji. Bieżący raport:
[CALIBRATION_COMPARISON_REPORT.md](../docs/CALIBRATION_COMPARISON_REPORT.md).

## Dopiero planowane

data_processing/windows, charts, labeling, datasets,
modeling, training, inference, evaluation i experiments zawierają przestrzeń
organizacyjną z README. Nie implementują jeszcze tych etapów.
Szczegółowe reguły planowanego etykietowania są w
[ARCHITECTURE.md](../docs/ARCHITECTURE.md); ustalenia autora w
[DECYZJE_3_3.md](../docs/DECYZJE_3_3.md).

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
