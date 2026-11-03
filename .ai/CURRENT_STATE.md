# Aktualny stan projektu

Aktualizacja: 2026-11-03. To opis stanu, nie zakaz realizacji kolejnych zleceń.
Przed rozpoczęciem pracy sprawdź, czy kod i konfiguracja nadal mu odpowiadają.

## Działa

- Pozyskiwanie rzeczywistych archiwów Binance Vision spot 4h, SHA-256 i CHECKSUM.
- Parsowanie ZIP, walidacja OHLC i szeregów, CSV, raporty JSON i manifest.
- CLI market-levels-download oraz python -m market_levels.cli.download.
- Aktywna konfiguracja JSON: zakres miesięcy, symbole oraz download.output, offline, strict_gaps i daily_fallback.
- Walidacja obsługiwanego źródła, rynku, interwału i symboli; błędy konfiguracji kończą wykonanie przed zapisem.
- Testy jednostkowe i integracyjne offline. Ostatni wykonany pełny zestaw: 30 testów OK. Liczba jest informacyjna, nie limitem rozwoju.

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
2020-01–2026-10. Lokalnie potwierdzono jedynie styczeń 2020: po 186 świec dla
obu instrumentów, bez braków. Sprawdź stan dysku; nie zakładaj pobrania całej historii.

Parametry przyszłego eksperymentu to 120 świec/wykres, przesunięcia 60 dla treningu
i 120 dla walidacji/testu, roboczo 800 wykresów, 45% rzeczywistych i 55%
syntetycznych, początkowo 1024 × 768 px. Nie są obecnie używane przez pobieranie.
Model oraz hiperparametry treningu nie zostały zatwierdzone.

## Dopiero planowane

data_processing/synthetic, data_processing/windows, charts, labeling, datasets,
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
