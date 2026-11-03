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
- autor zakończył pobieranie pełnego zakresu 2020-01–2026-10: po 82 archiwa
  i 14 975 świec BTCUSDT/ETHUSDT. Lokalny odczyt CSV potwierdził liczbę świec
  oraz jedną lukę 2020-02-19 12:00 UTC w obu szeregach; bez interpolacji;
- wdrożono generator syntetyczny, kalibrację z jawnym okresem, walidację,
  raporty i CLI. Nie przeprowadzono końcowej kalibracji;
- do wykonania: zatwierdzenie chronologicznego podziału, kalibracja wyłącznie
  treningowa, kontrola statystyczna i wizualna, generator obrazów, etykietowanie
  i niezależny audyt testu.

Zatwierdzone założenia generatora, 2026-11-03:

1. BTCUSDT i ETHUSDT, 4h, niezależne przykłady po 120 świec.
2. Losowe logarytmiczne zmiany ceny, 12 kroków wewnętrznych na świecę.
3. Od 1 do 3 faz: trend wzrostowy, spadkowy, konsolidacja i krótkie wybicie.
4. Konsolidacja: łagodny powrót do lokalnego środka; bez sztywnych barier.
5. Open kolejnej świecy równy Close poprzedniej; High/Low z wewnętrznej ścieżki.
6. Oddzielna kalibracja BTC/ETH tylko na danych treningowych, bez łączenia luk.
7. Jawny seed, profil, konfiguracja, wersja generatora i środowiska w metadanych.
8. Kontrola techniczna, statystyczna i późniejsza wizualna. Daty syntetyczne
   są indeksem symulacji, a nie podstawą podziału historycznych danych.

Siły trendów, mnożniki zmienności, rewersja, długości i wagi faz oraz diagnostyczne
ceny i sigma są wartościami roboczymi implementacji. Nie zatwierdzono ich jako
empirycznej kalibracji. Zakresy i statusy: [opis generatora](SYNTHETIC_GENERATOR.md).
Cel 440 syntetycznych przykładów przy 800 wykresach pozostaje roboczy;
nie jest stałą generatora i nie został automatycznie wygenerowany.

Kwestie prawne otwarte: upublicznienie pełnych danych, obrazów z danych Binance,
wytrenowanego adaptera lub całego modelu; obowiązki uczelni w repozytorium prac.
