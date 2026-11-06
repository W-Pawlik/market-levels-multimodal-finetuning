# Nowe seedy — gotowe polecenia PowerShell

Wykonuj w katalogu projektu. Skrypt wywołany pełną ścieżką działa także z innego
katalogu. Wymaga pełnych źródeł, istniejącej instalacji editable, danych i profili
autora. Dane, profile i raporty rynku pozostają poza handoffem.

```powershell
./.venv/Scripts/python.exe -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw 'Instalacja nieudana' }
./.venv/Scripts/python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Testy nieudane' }
```

Najpierw kontrola bez tworzenia danych:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_fresh_seeds.ps1 -CheckOnly
```

Następnie mała próba **32 serii** (po 2 na instrument/grupę/seed):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_fresh_seeds.ps1 -SmokeTest
```

Zapisz wypisaną ścieżkę katalogu. Przejrzyj raporty techniczne BTC/ETH w summary/.
Nie traktuj ich jako wyniku porównania 60-przykładowego.

## Pełna nowa próba — osobne świadome uruchomienie autora

Poniższy krok nie został wykonany podczas implementacji. Wygeneruje **960 serii**
na seedach 20261201/20261211. Nie wymaga i nie wykonuje kalibracji.

```powershell
$freshRun = 'data/synthetic/rf-' + [guid]::NewGuid().ToString('N').Substring(0,12)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_fresh_seeds.ps1 -CheckOnly -OutputDirectory $freshRun
if ($LASTEXITCODE -ne 0) { throw 'Kontrola nieudana' }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_fresh_seeds.ps1 -RunFull -OutputDirectory $freshRun
```

Nie używaj katalogu SmokeTest jako outputu RunFull. Nowy output musi nie istnieć;
CheckOnly go nie tworzy. Jeśli ścieżka jest zbyt długa, wybierz nowy krótki katalog,
np. `$freshRun = 'D:\rf\' + [guid]::NewGuid().ToString('N').Substring(0,12)`.
Zachowaj tę samą zmienną lub zapisz jej wartość do późniejszego wznowienia.

Wznowienie przerwanego pełnego przebiegu:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_fresh_seeds.ps1 -RunFull -ResumeDirectory $freshRun
```

Po ponownym otwarciu terminala przypisz `$freshRun` dokładną wcześniejszą ścieżkę.
Dla małej próby użyj `-SmokeTest -ResumeDirectory <katalog-małej-próby>`.
Nie zmieniaj kodu, konfiguracji ani profili pomiędzy rozpoczęciem a wznowieniem.
Nie kasuj plików i checkpointów, aby obejść błąd integralności.

## Własne ścieżki wejść

Opcja `-InputsFile configs/refinement_inputs.local.json` działa jak w poprzednim
skrypcie. Przy wznowieniu podaj ten sam zestaw wejść. Do istniejących pól
`config`, `profiles`, `real_csv`, `historical_reports` dodano opcjonalne
`baseline_profiles` z czterema kluczami:

```json
{
  "baseline_profiles": {
    "BTCUSDT|v1": "data/synthetic/calibration/BTCUSDT_train_2020_2023_unapproved.json",
    "ETHUSDT|v1": "data/synthetic/calibration/ETHUSDT_train_2020_2023_unapproved.json",
    "BTCUSDT|original": "data/synthetic/calibration/v2/BTCUSDT_train_2020_2023_v2_unapproved.json",
    "ETHUSDT|original": "data/synthetic/calibration/v2/ETHUSDT_train_2020_2023_v2_unapproved.json"
  }
}
```

To równocześnie wartości domyślne. Cztery profile refinement są domyślnie
odnajdywane w `data/synthetic/*/profiles/`; przy wieloznaczności podaj jawne
`profiles` jak w [poprzedniej instrukcji](INSTRUKCJA_POWERSHELL.md).
Nie twórz nowych profili i nie dobieraj parametrów według tej kontroli stabilności.

## Co przekazać po pełnej próbie

Dla każdego instrumentu przekaż pliki `*_comparison.json`, `*_summary.md`
z jego podkatalogu summary/ oraz `summary/{SYMBOL}/STABILITY.md`.
Dołącz run.json lub informację o seedach/liczności; zachowaj logi lokalnie.
Nowe raporty pozostaw oddzielnie od trzech poprzednich seedów.
Nie podejmuj decyzji wyłącznie na podstawie liczby poprawionych metryk:
sprawdź priorytety, pogorszenia kontrolne i rozrzut między seedami.
