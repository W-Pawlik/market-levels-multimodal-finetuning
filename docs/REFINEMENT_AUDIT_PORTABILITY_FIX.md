# Przenośność walidatora audytu refinement

Przyczyną zgłoszonego błędu jest dokładne porównanie zagnieżdżonych wyników
float po ponownym obliczeniu funkcji celu. Zależnie od środowiska ostatni bit
może się różnić: 0.0016521334745063683 i 0.0016521334745063685 różnią się
o około 2.17e-19. Równy całkowity loss nie zapewnia równości wszystkich składników.

W `synthetic/refinement.py` dodano `_objective_results_match()`. Tylko wyniki
obliczeń `trial.loss` i `trial.seed_objectives` porównuje przez `math.isclose`
z **rel_tol=1e-12, abs_tol=1e-18**. Warunek to różnica nie większa niż
max(1e-12 × max(|a|, |b|), 1e-18). Obie liczby muszą być skończone.
To tolerancja błędu numerycznego, niezależna od tolerancji diagnostycznych rynku.

Porównanie rekurencyjne wymaga identycznych typów, zbiorów kluczy, długości
i kolejności list. Nie utożsamia bool z int, int z float ani liczby z napisem.
Flagi przekroczeń tolerancji są dokładne. Nie toleruje brakujących/dodatkowych
pól. Parametry, seedy, statusy, zakresy, źródło i SHA nie są przekazywane do
porównania przybliżonego. Pozostają dotychczasowe kontrole siatki i minimum oraz
dokładna zgodność zapisanych selected_loss/baseline_loss z odpowiednimi próbami.
Nie zmieniono generatora, funkcji celu, konfiguracji ani formatu profilu.

Dodano pięć testów: wskazane 2.17e-19 i okolice zera, odrzucanie istotnych zmian
i NaN/Inf, ścisłe typy/struktura, walidacja profilu z różnicą jednego ULP bez
modyfikacji wejścia oraz odrzucanie manipulacji i zmian schematu w całym walidatorze.
Dotychczasowe regresje generatora i Windows pozostają w pełnym zestawie.

Wynik: **121 testów OK**, bez pominięć, 20.615 s, Windows PowerShell /
CPython 3.13.15. Polecenie: `./.venv/Scripts/python.exe -m unittest discover -s tests -v`.
Testy skupione na refinement: 15 OK. `git diff --check`: bez błędów whitespace.

Cztery istniejące profile BTC/ETH × full/bridge_volatility wczytano przez
`load_profile`: wszystkie OK, każdy zawiera 36 prób. Bajty i hashe plików
przed/po są identyczne. W bieżącym środowisku również przed poprawką cztery
profile przechodziły walidację; zgłoszona różnica jest odtworzona w regresji,
nie deklarujemy jej wystąpienia na tym komputerze. Zestaw hashów i wyników
walidacji znajduje się w `PROFILE_VALIDATION.json` w handoffie.

Nie ponawiano kalibracji BTC/ETH ani nie wykonywano dużych eksperymentów.
Testy korzystają wyłącznie z dotychczasowych małych sztucznych fixture.
Zmiany: ten dokument, `.ai/CURRENT_STATE.md`, `synthetic/refinement.py`
oraz dwa istniejące pliki `test_refinement_v2.py` / `test_refinement_v2_pipeline.py`.
Handoff zawiera aktualny projekt, log pełnego zestawu testów i potwierdzenie hashów;
nie zawiera lokalnych profili ani danych rynku.
