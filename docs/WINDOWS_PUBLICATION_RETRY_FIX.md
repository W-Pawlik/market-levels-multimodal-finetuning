# Publikacja katalogów przy blokadach Windows — 2026-11-06

Poprzednia obsługa blokad dotyczyła sprzątania katalogu roboczego, natomiast
`stage.rename(final)` w obu pipeline'ach wykonywało się jednokrotnie.
Przejściowy WinError 5 mógł więc przerwać publikację gotowej partii.
Nie przypisujemy blokady konkretnemu procesowi bez dodatkowych dowodów.

## Zmiana

`data_processing/staging.py` udostępnia wspólne `publish_directory(stage, final)`.
Wywołują je `pipelines/synthetic.run()` i `pipelines/compare_synthetic.save_comparison()`
w miejscu dotychczasowego rename. Zapis, odczyt i walidacja zawartości pozostają
przed publikacją. Ponawiany jest wyłącznie rename, nie generator ani zapis plików.

- Łącznie **4 próby**, opóźnienia **0.05, 0.15, 0.30 s** (suma 0.5 s).
- Windows: ponawiane tylko **WinError 5, 32, 33**. Kod winerror ma pierwszeństwo;
  inne błędy Windows nie stają się ponawialne tylko przez errno=EACCES.
  Gdy winerror nie występuje, konflikt dostępu rozpoznajemy po EACCES/EPERM.
- Kontrola nieistnienia celu przez lstat przed każdą próbą i po błędzie rename.
  Wykrywa też istniejący plik lub dowiązanie. Kolizja kończy się FileExistsError,
  nigdy sukcesem. Natywny rename na Windows nie zastępuje istniejącego celu,
  także jeśli pojawi się po sprawdzeniu lstat.
- Publikacja pozostaje atomowym rename na tym samym woluminie. Weryfikowany
  jest st_dev źródła i rodzica celu; nie ma fallbacku kopiowania ani replace().
- Każda nieudana próba ma log ze ścieżkami, numerem próby, winerror/errno
  i komunikatem. Logowana jest też pauza, sukces po ponowieniu lub wyczerpanie.
  Po wyczerpaniu rzucany jest **pierwszy oryginalny wyjątek dostępu**.
- Inne błędy nie są ponawiane. Istniejący kontekst publication_workspace
  zachowuje błąd operacji jako główny, nawet jeśli sprzątanie również zawiedzie.

Profile i ich zapis przez os.link nie wymagają zmiany. Nie zmieniono generatora,
funkcji celu, parametrów, seedów, formatów CSV ani istniejących raportów.
Skrypty PowerShell, ich tryby i kontrola MAX_PATH pozostają zachowane.

## Wznowienie

Znaleziono dodatkowe ryzyko: rekursywne wyszukiwanie manifestu/raportu mogło
zobaczyć plik z nieopublikowanego `.synthetic-*/batch` lub `.comparison-*/report`.
`refinement_comparison.unique_file()` ograniczono do układu `<id>/<plik>`.
Manifesty są szukane wyłącznie w diagnostics/, a nazwa katalogu partii musi
odpowiadać run_id. Pozostałość stagingu nie jest uznawana za opublikowany wynik.

`incomplete_stage()` podaje dokładną ścieżkę etapu, potwierdza zachowanie
ukończonych etapów i wskazuje ręczne zabezpieczenie całego niekompletnego
katalogu poza przebiegiem oraz ponowne uruchomienie ResumeDirectory.
Nie usuwa i nie przenosi niczego automatycznie. Nie obchodź błędu przez
usuwanie checkpointów albo poprawnych partii.

Jeżeli po rzeczywistym błędzie trzeba zabezpieczyć katalog, najpierw zatrzymaj
proces i sprawdź dokładnie podane ścieżki. Wybierz nową, nieistniejącą lokalizację
kopii poza przebiegiem. Dopiero wtedy użyj ręcznie
`Move-Item -LiteralPath <dokładny-niekompletny-etap> -Destination <nowa-kopia>`.
Nie stosuj tej operacji do ukończonego etapu lub całego katalogu wyników.
Po aktualizacji kodu wcześniejszy run.json może odmówić wznowienia przez SHA kodu;
nie podmieniaj SHA. Pełny eksperyment zacznij w osobnym nowym katalogu.

## Testy

Dziesięć nowych testów `tests/integration/test_publication_retry.py` wstrzykuje
błędy rename: 5→sukces, 32→33→sukces, trwałą blokadę czterech prób,
błędy EIO/ENOSPC/EXDEV/ENOENT i WinError 87, istniejący cel i jego pojawienie
się podczas/pomiędzy próbami. Sprawdza zachowanie pierwszego wyjątku i logów,
identyczne bajty manifestu i CSV względem przebiegu bez błędu, dokładnie jedno
losowanie na przykład oraz pojedynczy zapis payloadu raportu pomimo ponowień.
Nieopublikowany manifest i raport są odrzucane podczas wznowienia.

Pełny zestaw: **151 testów OK**, bez pominięć, 72.828 s,
Windows / CPython 3.13.15. Log jest dołączony do handoffu.
`git diff --check` nie zgłosił błędów whitespace.
Kontrola SHA przed/po obejmuje 6552 istniejące pliki danych, profili i raportów.
Dotychczasowe testy obejmują
także błędy sprzątania i rzeczywistą blokadę uchwytu katalogu na Windows.
Sprawdzono --help obu CLI i natywną próbę PowerShell w temp: 4 serie
bridge_volatility na seedzie 20261211 i dwa raporty, bez ponownej kalibracji.
Ukończony przez autora SmokeTest 32 serii pozostał bez zmian.

## Końcowy eksperyment — uruchamia wyłącznie autor

Nie ma potrzeby powtarzania ukończonego SmokeTestu. Po przeglądzie poprawki:

```powershell
./.venv/Scripts/python.exe -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw 'Instalacja nieudana' }
./.venv/Scripts/python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Testy nieudane' }
$fullRun = 'data/synthetic/rf-' + [guid]::NewGuid().ToString('N').Substring(0,12)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_fresh_seeds.ps1 -CheckOnly -OutputDirectory $fullRun
if ($LASTEXITCODE -ne 0) { throw 'Kontrola nieudana' }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_fresh_seeds.ps1 -RunFull -OutputDirectory $fullRun
```

Zachowaj wypisaną wartość fullRun. Po przerwaniu, bez dalszej zmiany kodu/wejść:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_fresh_seeds.ps1 -RunFull -ResumeDirectory $fullRun
```

To 960 nowych serii na 20261201/20261211, cztery grupy, tylko trening,
selection_seed=20261106. Pełnego eksperymentu **nie uruchomiono** w tej sesji.
Nie zatwierdzono żadnego generatora.
