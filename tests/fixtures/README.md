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
