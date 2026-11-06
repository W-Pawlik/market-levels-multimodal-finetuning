# Krótsze ścieżki przebiegów refinement na Windows

Stara domyślna nazwa `refinement-comparison-<32 hex>` przekraczała budżet
MAX_PATH po dołączeniu katalogów etapu i pełnego identyfikatora przykładu.
Zgłoszony plik JSON w staging miał 260 znaków. Po publikacji ścieżka jest
jeszcze dłuższa: `diagnostics/<24 hex>` zastępuje `.synthetic-<8 znaków>/batch`.
`bridge_volatility` dodaje kolejne 13 znaków względem `full`.

Zmiana obejmuje wyłącznie koordynator i opis opcji skryptu:

- Domyślny katalog to `data/synthetic/rc-<12 hex>`. Pełny UUID (32 hex) jest
  zapisany w `run.json` jako `run_id`; nie jest seedem ani hashem danych.
  Kolizja nazwy nadal kończy się odmową nadpisania.
- Przed utworzeniem katalogu i generowaniem sprawdzane są przewidywane ścieżki
  obu wariantów: pliki CSV/JSON w staging i po publikacji, manifesty, raporty
  JSON/Markdown, checkpointy i logi. Kontrola działa także przy wznowieniu
  i bezpośrednim wywołaniu execute(). Nie zaczynamy full, jeżeli późniejszy
  bridge_volatility nie zmieściłby się w limicie.
- Ścieżka musi mieć mniej niż 260 jednostek UTF-16 (maksymalnie 259 plus
  końcowy NUL). Kontrola nie polega na konfiguracji LongPathsEnabled hosta
  i obejmuje Unicode. Błąd podaje długość, przewidywaną ścieżkę i sugestię
  `-OutputDirectory` z krótszym katalogiem. Nie tworzy nowego katalogu wyników.
- CheckOnly zachowuje kontrolę zależności i dodatkowo sprawdza domyślny
  katalog dla pełnego porównania. Można mu teraz podać OutputDirectory,
  żeby sprawdzić inną lokalizację bez tworzenia danych.

W bieżącym katalogu projektu najdłuższa przewidywana ścieżka nowego domyślnego
przebiegu ma **245 jednostek UTF-16**. Nazwy przykładów, 64-znakowe seedy,
24-znakowe hashe partii/raportów i matematyka pozostają bez zmian.
Nie zmieniono profili, konfiguracji, seedów diagnostycznych ani starych raportów.

## Polecenia

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_comparison.ps1 -CheckOnly
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_comparison.ps1 -SmokeTest
```

Jeśli projekt lub TEMP jest bardzo głęboko, wybierz nowy krótki katalog:

```powershell
$shortOutput = 'D:\rc\' + [guid]::NewGuid().ToString('N').Substring(0,12)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_comparison.ps1 -CheckOnly -OutputDirectory $shortOutput
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_comparison.ps1 -SmokeTest -OutputDirectory $shortOutput
```

CheckOnly nie tworzy katalogu, więc SmokeTest może użyć tej samej nowej nazwy.
Do wznowienia nowego przebiegu używaj tego samego trybu i ResumeDirectory.
Nie usuwaj starej nieudanej próby i nie przenoś jej plików do nowego katalogu.
Pozostaje dotychczasowe przypinanie kodu przez SHA: stary przebieg sprzed
aktualizacji może odmówić wznowienia z powodu zmiany kodu. Nową próbę uruchom
osobno, bez obchodzenia kontroli run.json.

## Weryfikacja

Sześć nowych testów sprawdza dokładnie 260 (odmowa), 259 (akceptacja), krótki
output, dłuższy bridge_volatility, zgłoszoną ścieżkę staging 260, UTF-16,
pełny UUID w run.json, wznowienie i odmowę przed mkdir/CLI. Dotychczasowe
testy skryptu oraz regresje generatora i audytu pozostają aktywne.
Pełny log i wynik małej próby PowerShell są w handoffie.
Pełny zestaw: **136 testów OK**, bez pominięć, 41.397 s (Windows, CPython 3.13.15).
Natywny PowerShell: CheckOnly, 8 serii w temp, wznowienie i odmowa zbyt długiego
outputu bez tworzenia katalogu — OK. Testy nie polegają na ustawieniu long paths hosta.
Nie wykonywano ponownej kalibracji ani pełnego porównania 720 serii.
