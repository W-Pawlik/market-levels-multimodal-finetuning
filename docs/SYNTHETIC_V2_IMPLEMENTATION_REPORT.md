# Raport implementacji generatora OHLC v2

Weryfikacja na Windows, CPython 3.13.15. Punkt odniesienia: **77 testów OK**.
Po wdrożeniu: **96 testów OK**, w tym wszystkie dotychczasowe 77.

## Zmiany i kompatybilność

Dodano generator 2.0.0 z rozdzieleniem Close 4h, wewnętrznej ścieżki mostu
i procesu zmienności. Obsługuje base, bridge, tails, volatility i full.
Dotychczasowy v1 nadal jest domyślny. Nie zmieniono jego kodu w generator.py,
planowania faz w regimes.py, współdzielonej walidacji OHLC ani pobierania Binance.

Nowe flagi istniejącego CLI generowania: `--generator-version v1|v2`,
`--v2-variant base|bridge|tails|volatility|full`, `--experiment-id` dla v2.
Kalibracja: `--generator-version v2`. Porównanie: dodatkowy tryb `--reports`.
Stare argumenty i działanie domyślne pozostają. Nie dodano zależności.

W konfiguracji są oddzielne ustawienia v2 i ograniczonej kalibracji. V1 nie
zapisuje nowych kluczy w historycznej reprezentacji konfiguracji. Dzięki temu
zachowano metadane, OHLC i identyfikatory dotychczasowych partii. Schemat profilu
2 jest oddzielny od 1, bez cichego uznawania v1 za kompletny profil v2.
Profile v2 są początkowo `unapproved`, również przy ręcznych parametrach;
w tym przypadku mają jawne `estimation_kind=diagnostic` i nie są traktowane
jako kalibracja rynku.

## Pliki

`+` nowy, `~` zmodyfikowany. Dane lokalne i wyniki diagnostyczne są ignorowane w Git.

```text
~ .ai/CURRENT_STATE.md
~ .ai/WORKFLOW.md
~ README.md
~ configs/experiment.json
docs/
  ~ ARCHITECTURE.md
  ~ DECYZJE_3_3.md
  ~ SYNTHETIC_GENERATOR.md
  ~ SYNTHETIC_CALIBRATION_COMPARISON.md
  + SYNTHETIC_GENERATOR_V2.md
  + SYNTHETIC_V2_POWERSHELL.md
  + SYNTHETIC_V2_IMPLEMENTATION_REPORT.md
src/market_levels/
  cli/
    ~ generate_synthetic.py
    ~ calibrate_synthetic.py
    ~ compare_synthetic.py
  data_processing/
    pipelines/
      ~ synthetic.py
      ~ compare_synthetic.py
    synthetic/
      ~ README.md
      ~ settings.py
      ~ calibration.py
      ~ comparison.py
      ~ training_period.py
      + dispatch.py
      + generator_v2.py
      + stochastic_processes.py
      + v2_parameters.py
      + profile_v2.py
      + calibration_v2.py
      + experiments.py
tests/
  fixtures/
    + synthetic_v1_regression.json
  unit/
    + test_synthetic_v2.py
  integration/
    + test_synthetic_v2_pipeline.py
```

## Równania i normalizacja

```text
Close log-return = mu - kappa*(X_open-center) + sigma_regime*L_t*Z_t
Z_t = epsilon * (k if U<p else 1) / sqrt((1-p)+p*k²)
h_0 ~ N(0,v), v=stationary_std²
h_t = phi*h_(t-1) + stationary_std*sqrt(1-phi²)*epsilon_h
L_t = exp(h_t-v)
X_k = X_open + (k/12)*(X_close-X_open) + gamma*sigma_t*(W_(k/12)-(k/12)*W_1)
```

Mieszanka ma zerową średnią i wariancję 1. Dla stacjonarnego Gaussowskiego h
E[L²]=1; niezależność Z i h zachowuje wariancję iloczynu. Korekta wynosi v,
bo kontrolujemy drugi moment skali. Nie dodano osobnego mnożnika dla przykładu.
Stacjonarny stan początkowy i pamięć AR dają różne poziomy zmienności serii.
Stan nie resetuje się na zmianie reżimu.

Close jest losowany przed mostem; gamma nie zmienia jego losowań. High/Low
pochodzą wyłącznie z 13 punktów jednej ścieżki. Końce są dokładne, Open jest
poprzednim Close. Nie ma obcinania ekstremów ani dodatkowych knotów.
Nieprawidłowe/nieosiągalne numerycznie ceny powodują błąd całej partii.
Neutralna wersja v2 nie jest bitowym odtworzeniem starej v1.

## Kalibracja

Współdzielono podstawowe oszacowania, odczyt/zapis, walidację, wybór okien
i liczenie statystyk. Nowa kalibracja używa tylko jawnego treningu z konfiguracji.
Odczytuje pełny CSV, ale dane poza okresem nie wpływają na parametry ani cel.
Pominięto przejścia przez luki; nie interpolowano.

Parametry gamma, p/k oraz phi/std dobiera ograniczone przeszukiwanie współrzędnych
całego modelu full, przez kilka rund i wspólnych seedów. Domyślnie są trzy seedy
73001/73002/73003, po cztery okna; referencja to 12 rozłącznych okien treningowych
wybranych seedem 73004. Cel obejmuje kształty, ogony, poziom i zróżnicowanie
zmienności, korelację i dodatkowe statystyki ogonów. Wagi, siatki i budżet są
projektowe, jawne i konfigurowalne. Wszystkie próby i wyniki po seedach pozostają
w profilu. Bieżący punkt jest dodatkowym kandydatem siatki.

To nie globalny optymalizator ani estymacja identyfikująca jeden „prawdziwy” model.
Użycie ograniczonej próbki odniesienia wymaga późniejszej analizy wrażliwości.
Wspólna ocena full uwzględnia współdziałanie mechanizmów. Ablacje używają tych
samych parametrów, bez ponownego strojenia każdej do konkretnego końcowego seeda.

Dodatkowo zapisuje się ruchome std z 24 zwrotów, krok 1, bez przejść przez luki,
oraz korelację abs(r) całego treningu. Parametry phi/std są dobierane numerycznie
na podstawie metryk, a nie przedstawiane jako bezpośrednia estymacja z ruchomego std.

## Wykonane testy

- Golden v1: niezmienione OHLC i pełne bazowe metadane BTC/ETH na CPython 3.13.15.
- Zweryfikowano także **120 istniejących rynkowo skalibrowanych przykładów v1**
  z wcześniejszej partii: po 60 BTC/ETH. Pierwszy przykład każdego instrumentu
  odtworzono w całości z identycznymi metadanymi i OHLC.
- Most: końce, 12 losowań kroków, odtwarzanie, niezmienność Close względem gamma,
  empiryczna średnia i wariancja punktu środkowego na 6000 ścieżek.
- Mieszanka: 100 000 realizacji, średnia w tolerancji ±0,02, wariancja ±0,04,
  większa częstość abs(Z)>3 niż dla normalnego, walidacja p i k.
- Zmienność: 100 000 stanów dla normalizacji E[L²] (tolerancja ±0,03), pamięć AR,
  stacjonarny start, ciągłość przez fazy, poprawne dodatnie skale i błędy numeryczne.
- Wszystkie warianty: 120 świec, 12 kroków, UTC, ciągłość ceny, poprawne OHLC,
  seedy strumieni, profile, parametry aktywne i odtwarzanie.
- Kalibracja: co najmniej dwa seedy, powtarzalność, brak wpływu przyszłych cen,
  odrzucanie okresów poza treningiem, audyt prób i brak automatycznej akceptacji.
- CLI/pipeline: oba schematy, dry-run, odmowa nadpisania, błędy wersji,
  wykrywanie zmienionych parametrów/mechanizmów/przebiegu h i hashy.
- Zestawienia: identyczna referencja, kilka seedów, błędy metryk i ich kierunki,
  rozrzut między seedami, odmowa powtórzonych raportów i niezgodnej referencji.
- Wykonano `pip install -e .` i mały przebieg **z komend dokumentacji PowerShell**
  w katalogu tymczasowym: kalibracja v2 BTC/ETH, sześć wariantów, automatyczne
  ścieżki manifestów/raportów i dwa raporty zbiorcze. Użyto sztucznych CSV i małej
  siatki; nie wykonano za autora właściwej serii rynkowej.
- `git diff --check` bez błędów białych znaków. Potwierdzono SHA-256 wszystkich
  **276 wcześniejszych plików processed/ i synthetic/**: bez zmian.

## Mała próba diagnostyczna

Artefakty lokalne: `data/synthetic/diagnostics/v2-smoke-20261103-01/`.
Referencja to **sztucznie przygotowane świece**, nie notowania BTC/ETH.
Próbka nie wymagała lokalnej pełnej historii Binance.

| Wariant | BTC | ETH | Świece łącznie | Walidacja i round-trip |
| --- | ---: | ---: | ---: | --- |
| V1 | 2 | 2 | 480 | OK |
| V2-base | 2 | 2 | 480 | OK |
| V2-bridge | 2 | 2 | 480 | OK |
| V2-tails | 2 | 2 | 480 | OK |
| V2-volatility | 2 | 2 | 480 | OK |
| V2-full | 2 | 2 | 480 | OK |

Łącznie 24 serie, 2880 świec, 34 560 wewnętrznych kroków ścieżek, 12 raportów
porównawczych i dwa końcowe zestawienia sześciu wariantów. Seed diagnostyki:
20261107; seed wyboru okien 20261106. W tej technicznej kalibracji użyto dwóch
seedów 91/92 i małej siatki, odrębnych od diagnostyki. Nie było błędnych ani
powtórzonych przykładów w zaakceptowanych partiach. Osobne output wariantów
zachowują istniejące zasady wykrywania duplikatów.

Indeks: `SMOKE_REPORT.json`; końcowa kontrola: `FINAL_CHECK.json`.
Końcowe zestawienia z finalnego kodu:

```text
final_summary/f7d12f57a766d607bb57e51f/BTCUSDT_comparison.json
final_summary/f7d12f57a766d607bb57e51f/BTCUSDT_summary.md
final_summary/e6d9bca14aea93276021666c/ETHUSDT_comparison.json
final_summary/e6d9bca14aea93276021666c/ETHUSDT_summary.md
```

To potwierdzenie działania narzędzi, **nie empiryczny wynik realizmu generatora**.
Nie ekstrapolujemy dopasowania do prostych sztucznych świec na rzeczywisty rynek.

## Ograniczenia i następny krok autora

Nie wykonano kalibracji v2 na rzeczywistym rynku ani pełnej oceny 60 BTC + 60 ETH
na kilku seedach. Nie ma podstaw do zatwierdzenia nowej matematyki lub twierdzenia
o sukcesie empirycznym. Nie użyto walidacji 2024 ani testu 2025–2026 do strojenia.
Nie wygenerowano docelowych 440 przykładów, wykresów, etykiet ani modelu AI.
Nie utworzono commita ani nie publikowano danych.

Wymagają oceny: gamma, p/k, phi/std, wagi celu, siatki i liczba prób, wrażliwość
na referencyjne okna, dotychczasowe parametry faz i uproszczenie 12 kroków.
Mieszanka jest symetryczna, proces h stacjonarny, most ma normalną fluktuację;
nie zapewniają odtworzenia całej mikrostruktury, ekstremów ani asymetrii rynku.
Kalibracja na treningu i porównanie z nim nie są niezależną walidacją.
Nie wiadomo jeszcze, czy full jest lepszy od prostszych wariantów.

Autor powinien przejrzeć implementację, uruchomić profile v2 wyłącznie na treningu,
wykonać małą próbę, następnie porównać wybrane warianty na tych samych 60 oknach
(seed 20261106), najlepiej przy co najmniej trzech seedach diagnostycznych.
Potem ocenić wielometryczne błędy, rozrzut wyników i późniejszą próbkę wizualną.
Kontrola wizualna oczekuje na renderer. Ograniczenia licencyjne pozostają.

Dokładne komendy dla obu instrumentów, wariantów i tabel zbiorczych:
[SYNTHETIC_V2_POWERSHELL.md](SYNTHETIC_V2_POWERSHELL.md).
Pełna matematyka, normalizacja i status parametrów:
[SYNTHETIC_GENERATOR_V2.md](SYNTHETIC_GENERATOR_V2.md).
