# Ręczne fixture sr-eval-v1

Nie są to obrazy rynku, odpowiedzi VLM ani produkcyjne przykłady testowe.
Referencje i odpowiedzi zapisano ręcznie. Stałe sztuczne OHLC służą jedynie
ustaleniu jednoznacznego ATR: H=101.5, L=98.5, O=C=100 daje ATR=3;
H=L=O=C=100 daje ATR=0. Każdy CSV ma 120 świec 4h.
Referencje nie są wynikiem ponownego użycia algorytmu etykietującego.
Fixture nie wymaga obrazów (`image: null`), wyłącznie jawnego rodzaju
`evaluation_fixture_dataset` / `technical_fixture`.

Przy k=0.5, zatem T=1.5 (poza zero_atr), zestaw A ma:

| ID bez fixture_ | Referencja supports / resistances | Predykcja A | TP | FP | FN | F1 przykładu |
|---|---|---|---:|---:|---:|---|
| exact | [100] / [110] | dokładna | 2 | 0 | 0 | 1 |
| boundary | [100] / [] | support 101.5 | 1 | 0 | 0 | 1 |
| outside | [100] / [] | support 101.5001 | 0 | 1 | 1 | 0 |
| missing | [100,102] / [] | support 100 | 1 | 0 | 1 | 2/3 |
| extra | [100] / [] | supports 100,95 | 1 | 1 | 0 | 2/3 |
| duplicates | [100] / [] | supports 100,100.00 | 1 | 1 | 0 | 2/3 |
| wrong_side | [100] / [] | resistance 100 | 0 | 1 | 1 | 0 |
| empty | [] / [] | obie puste | 0 | 0 | 0 | 1 |
| invalid | [100] / [] | blok Markdown z JSON | 0 | 0 | 1 | 0 |
| greedy | [100,102] / [] | supports 101,99 | 2 | 0 | 0 | 1 |
| invalid_empty | [] / [] | `{bad` | 0 | 0 | 0 | 0 |
| zero_atr | [100] / [] | support 100, ATR=0 | 1 | 0 | 0 | 1 |

Suma: TP=9, FP=4, FN=4; micro-F1=9/13; pomocniczy średni F1=7/12.
Poprawny format ma 10/12 odpowiedzi; jeden duplikat ceny. MAE USDT:
BTC=0 na 3 parach; ETH=3.5/6 na 6 parach. Globalnie błąd/ATR ma 8 par;
jedna para z ATR=0 jest wyłączona, nie zastąpiona zerem.
Przy 0.25 ATR sumy to 6/7/7; przy 1 ATR 10/3/3.
`expected-main.json` przechowuje te same ręczne oczekiwania.

Zestaw B to ręcznie przepisane dokładne referencje, dające oczekiwany wynik 1.
Służy kontroli porównania raportów A/B, a nie demonstracji skuteczności modelu
bazowego/dostrojonego ani algorytmu względem siebie samego. Oba manifesty mają
`prediction_kind: technical_fixture`, `variant: technical_fixture`.

Dodatkowe `fixture_train_guard` i `fixture_test_guard` reprezentują odrębne
okresy w manualnym zbiorze, pozwalając wykryć pomylenie splitów.
Nie są oceniane w demonstracji validation i nie pochodzą z produkcyjnego testu.
