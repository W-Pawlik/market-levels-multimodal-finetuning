# Rejestr decyzji etapu 3.3

Zatwierdzone przez autora pracy, 2026-11-02:

1. Binance Vision, badania akademickie, osobne potwierdzenie warunków publikacji.
2. Historia: 2020-01 – 2026-10, spot BTC/USDT i ETH/USDT.
3. Zachowujemy źródłowe ZIP oraz osobne przetworzone OHLC.
4. Przesunięcie okien: trening 60 świec, walidacja/test 120 świec.
5. Dane syntetyczne: generator losowy z różnymi reżimami rynku.
6. 800 przykładów jako cel roboczy, możliwość korekty po diagnostyce.
7. Udział: 55% syntetycznych, 45% rzeczywistych (roboczo).
8. Matplotlib + mplfinance, wstępnie 1024 x 768 px.
9. Praca i własny kod; bez publikacji pełnego zbioru i wag przed weryfikacją praw.

Wcześniejsze niezmieniane ustalenia: 120 świec/wykres, 4h, 3+3 poziomy,
reguły wykrywania ekstremów i ATR(14) zgodne z podrozdziałem 3.2.

Status techniczny:
- wykonano: kod pobierania i walidacji danych, testy offline oraz refaktoryzacja
  do pakietu `market_levels` (2026-11-03);
- autor uruchomił pobranie BTCUSDT i ETHUSDT za styczeń 2020; lokalne archiwa
  potwierdzono ponownie offline: po 186 świec, bez braków. Nie oznacza to
  pobrania ani walidacji całego zatwierdzonego zakresu;
- do wykonania: pobranie i analiza pozostałego zakresu, generator syntetyczny,
  generator obrazów, podział chronologiczny, etykietowanie i niezależny audyt testu.

Kwestie prawne otwarte: upublicznienie pełnych danych, obrazów z danych Binance,
wytrenowanego adaptera lub całego modelu; obowiązki uczelni w repozytorium prac.
