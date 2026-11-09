# Próbka regresyjna

`pipeline_baseline.json` zapisano przed refaktoryzacją, uruchamiając oryginalny
`src.download_data.run` na lokalnym ZIP z dwiema świecami: 2024-01-01 04:00
i 12:00 UTC, OHLC 100/112/91/110. Wynik ma jedną lukę wewnętrzną,
jedną brakującą świecę na początku i 182 na końcu: łącznie 184.

Zapis obejmuje CSV, wszystkie pola raportu, manifest i stdout. Usunięto jedynie
czas utworzenia manifestu, a katalog tymczasowy zastąpiono `<OUTPUT>`.
SHA-256 ZIP zastąpiono `<SHA256>`, ponieważ nagłówek generowanego w teście ZIP
zawiera czas utworzenia. Test niezależnie sprawdza rzeczywisty SHA-256 tego ZIP.
Ścieżki wzorca pochodzą z Windows i są normalizowane przy porównywaniu.

Test tworzy ZIP samodzielnie, bez Internetu. CSV jest porównywany bajtowo
z zachowaniem CRLF, JSON przez pełne porównanie pól oraz sprawdzenie formatu
zapisu. Pierwotny test integracyjny z dwiema świecami 00:00 i 04:00 również
zachowano osobno, bez zmiany jego oczekiwań.

## Wzorzec reorganizacji src z 2026-11-08

`refactor_behavior.json` zapisano z kopii źródeł sprzed reorganizacji.
Obejmuje 28 przypadków: BTC/ETH, dwa master seedy, v1 oraz sześć wariantów v2.
Profile są ręcznymi profilami diagnostycznymi, bez kalibracji na danych rynku.

Wzorzec zawiera hash OHLC, pełnych metadanych i diagnostyki etykietowania,
dokładny JSON etykiety, metryki okna oraz hashe CSV, PNG i nakładki. Wyniki nie
są aktualizowane automatycznie przez testy. Dla hashy obiektów użyto JSON
`sort_keys=True`, `ensure_ascii=False`, `allow_nan=False`, separatorów `(',', ':')`.
Pliki porównuje się bajtowo przez SHA-256, bez normalizacji obrazu lub CSV.

Referencja powstała na CPython 3.13.15 i Matplotlib 3.11.2. Testy jawnie podają
pominięcie, jeśli wersja środowiska nie pozwala porównać tego wzorca. W trakcie
refaktoryzacji wykonano też osobne porównanie pełnych wyników małej kalibracji,
refinementu i selekcji okien ze starą implementacją; nie jest ono nową kalibracją rynku.
