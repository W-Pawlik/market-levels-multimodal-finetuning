# Rysunki do podrozdziału 5.4

Wygenerowano dwa rzeczywiste przykłady końcowego testu dostrojonego modelu,
bez nowej inferencji, treningu ani generowania danych cenowych.

| Rysunek | ID testowe | TP / FP / FN | F1 przy 0,5 ATR |
| --- | --- | --- | --- |
| 5.1, ETHUSDT | `9f49cdba6e4d2d0cff453353` | 4 / 1 / 1 | 0,8000 |
| 5.2, BTCUSDT | `9ae321c8cccbc677d118c424` | 0 / 6 / 5 | 0,0000 |

Gotowe pliki:

- [5.1 PNG](figures/rysunek_5_1_ethusdt_porownanie.png)
- [5.1 SVG](figures/rysunek_5_1_ethusdt_porownanie.svg)
- [5.2 PNG](figures/rysunek_5_2_btcusdt_blad_skali.png)
- [5.2 SVG](figures/rysunek_5_2_btcusdt_blad_skali.svg)

PNG: 4080 × 1650 px, 300 DPI, białe tło. SVG zawierają wektorowe świece,
poziomy i tekst zamieniony na ścieżki, bez osadzonych bitmap.
Katalogi `figures/` i `verification/` pozostają lokalne i są wykluczone z Git;
odnośniki do obrazów i dowodów działają w lokalnej kopii z wygenerowanymi plikami.
Publiczne repozytorium zawiera kod odtwarzania, testy oraz opis weryfikacji.
W rysunku 5.1 oba panele mają identyczne świece i granice osi.
W rysunku 5.2 wspólna liniowa oś cen w prawym panelu pokazuje wszystkie
oryginalne wartości. Kolejność i numeracja punktów odpowiadają tablicom źródłowym;
poziomy referencyjne i predykcje nie są tam łączone w pary.

## Uruchomienie

Z głównego katalogu repozytorium, w istniejącym środowisku z dodatkiem `[charts]`:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/create_thesis_figures_5_4.py
```

Skrypt odmawia nadpisania obrazów i istniejącego katalogu weryfikacji.
Ponowne generowanie wymaga nowych katalogów, np.:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/create_thesis_figures_5_4.py --output docs/thesis/figures-reproduction --verification docs/thesis/verification/reproduction
```

Można wskazać inne lokalizacje tych samych artefaktów przez `--dataset`,
`--predictions` i `--evaluation`. Skrypt kontroluje oba ustalone przypadki;
ogólne funkcje `load_visualization_examples`, `comparison_figure` i `save_figure`
pozwalają wykorzystać mechanizm do innych zapisanych przykładów.

## Implementacja

Utworzone pliki kodu:

- `scripts/create_thesis_figures_5_4.py`: uruchomienie, kontrola ID, symboli, wartości i metryk wskazanych przez autora.
- `src/market_levels/evaluation/workflows/visualization.py`: odczyt i powiązanie źródeł, kontrola oficjalnego raportu oraz odtworzenie oryginalnych PNG.
- `src/market_levels/evaluation/reporting/figures.py`: dwa panele, prezentacja błędu skali i eksport PNG/SVG.
- `tests/unit/evaluation/test_figures.py`: trzy testy kontraktu nowych wizualizacji.

Zmodyfikowane pliki kodu:

- `src/market_levels/charts/io/rendering.py`: opcjonalny argument `figure`, umożliwiający rysowanie przez `build_figure()` na istniejącym `SubFigure`.
- `src/market_levels/labeling/io/overlays.py`: wspólna funkcja `draw_levels()`;
  `render_levels()` zachowuje dotychczasowy wygląd. Nowe rysunki podają większy
  odstęp etykiet odpowiedni do niższych paneli.

Logika etykietowania, treningu, inferencji i oficjalnej ewaluacji jest bez zmian.
Zastana zmiana autora w `synthetic/domain/generation/v2.py` pozostała nietknięta.

## Weryfikacja wykonana 2026-11-22

- Etykiety i OHLC pochodzą z `data/datasets/ds35-800-20261107-a`.
- Surowe predykcje pochodzą z `results/vlm46-final-test/finetuned-nf4/predictions.jsonl`.
- Metryki pochodzą z `results/evaluation/vlm46-final-test-finetuned-nf4/per_example.jsonl`;
  niezmieniony ewaluator potwierdził ich odtworzenie. Zweryfikowano też cały
  oficjalny raport, manifest zbioru i identyczność plików predykcji.
- Sprawdzono dokładne wartości obu referencji i predykcji z treścią zadania,
  z zachowaniem `Decimal` oraz surowego tekstu odpowiedzi.
- Oba odtworzone bazowe PNG są identyczne bajtowo z oryginalnymi obrazami testowymi,
  przy Pythonie 3.13.15 i Matplotlib 3.11.2. Nie wykryto rozbieżności renderera.
- Otworzono oba końcowe PNG i sprawdzono tytuły, legendy, osie oraz etykiety.
  Pillow potwierdził poprawność PNG i DPI, parser XML poprawność SVG oraz brak bitmap.
- Pełny istniejący zestaw: **407 testów OK**, bez pominięć (`verification/tests.log`).
- Nowe testy: **3/3 OK** (`verification/figure-tests.log`): zachowanie świec i osi,
  odstępy etykiet, oddzielenie tytułu od legendy, niezmienione wartości błędnych
  predykcji, eksport i odmowa nadpisania.
- Po końcowych zmianach osobno uruchomiono regresję renderera:
  **1/1 OK, 28 przypadków PNG i nakładek**, oraz granice zależności: **3/3 OK**.
- SHA-256 i inwentarz **3408 chronionych plików** zbioru, sesji końcowego testu
  i jego oficjalnych raportów pozostały niezmienione; brak plików dodanych do źródeł.
- `git diff --check`: OK.

Dowody końcowe: [odczyt, metryki i odtworzone PNG](verification/final/verification.json),
[integralność źródeł i obrazów](verification/artifact-and-integrity-check.json).
Pozostałe katalogi w `verification/` zawierają oddzielne podglądy robocze
i logi; cztery podstawowe obrazy znajdują się wyłącznie w `figures/`.

Ograniczenie: nie wykonywano próby osadzenia w programie Word. Przy wstawianiu
warto użyć pełnej szerokości obszaru tekstu; SVG zachowuje ostrość po skalowaniu.
Ponowne odtworzenie PNG na innych wersjach środowiska może mieć inne bajty;
skrypt zgłosi taką rozbieżność zamiast ją ukrywać.
