# Sposób pracy i weryfikacji

## Przed zmianą

1. Przeczytaj AGENTS.md, instrukcje .ai i aktualne zadanie autora.
2. Sprawdź katalog roboczy, istniejące zmiany, właściwe źródła oraz dokumenty dotyczące zadania. Nie nadpisuj pracy autora.
3. Odróżnij stan działający od planowanego. Sprawdź konfigurację i faktycznie używane interfejsy.
4. Dla refaktoryzacji logiki zapisz punkt odniesienia: testy oraz deterministyczne wyniki. Jeśli dotykasz operacji na danych, zapisz SHA-256 istniejących plików poza katalogiem danych.
5. Zaplanuj najmniejszą spójną zmianę. Jeśli zadanie jest już jednoznacznie zlecone, realizuj je bez dodatkowej rundy potwierdzeń.

## Środowisko — Windows PowerShell

Polecenia wykonuj z głównego katalogu projektu. Jeśli środowisko już istnieje
i działa, korzystaj z niego zamiast tworzyć kolejne.

Jednorazowe przygotowanie:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Podstawowe sprawdzenie:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\market-levels-download.exe --start 2020-01 --end 2020-01 --dry-run
```

Równoważny CLI:

```powershell
.\.venv\Scripts\python.exe -m market_levels.cli.download --start 2020-01 --end 2020-01 --dry-run
```

Dry-run wczytuje konfigurację i pokazuje plan; nie pobiera ani nie zapisuje danych.
Nie potwierdza rzeczywistej dostępności serwera. Uruchomienie bez ograniczenia dat
i bez dry-run może pobrać cały zakres z JSON.

## W trakcie i po zmianie

- Zmieniaj źródła, nie kopie w build/ ani stary ZIP.
- Zachowuj pierwotne sześć przypadków testowych; importy można dostosowywać do świadomie zmienionej architektury.
- Dla zmiany logiki uruchom właściwe testy; przy zmianie pobierania, parsera, konfiguracji lub CLI uruchom pełny istniejący zestaw i odpowiedni dry-run.
- Dodawaj testy istotnych nowych zachowań i ryzyk regresji. Nie twórz testów odtwarzających wyłącznie implementację.
- Dla samych instrukcji i dokumentacji sprawdź poprawność treści, ścieżek, odnośników i zgodność z kodem; nie dodawaj testów aplikacji tylko z powodu edycji Markdown.
- Próbę prawdziwych archiwów wykonuj offline na kopiach w osobnym katalogu tymczasowym; katalog output musi zawierać własne raw/. Nie używaj oryginalnego data/ jako poligonu.
- Porównuj pełne CSV, raporty i manifesty. Normalizuj tylko rzeczywiście zmienne pola, np. czas utworzenia i ścieżkę katalogu tymczasowego.
- Gdy zadanie dotyczy ochrony danych, porównaj ich SHA-256 przed i po pracy.
- Nie naprawiaj cichym sposobem niepowiązanych problemów. Opisz je oddzielnie.

## Zamknięcie zadania

Zaktualizuj CURRENT_STATE.md, README i architekturę tylko tam, gdzie zmienił się
faktyczny stan lub sposób użycia. Nie zmieniaj historycznych wyników testów tak,
jakby były nowymi wykonaniami.

W raporcie podaj: co zmieniono, dlaczego, co faktycznie sprawdzono, wynik i istotne
ograniczenia. Nie opisuj całej chronologii narzędzi. Wskazuj nowe polecenia,
jeśli zmieniono interfejs.

Paczki do innych sesji twórz na zlecenie. Dołączaj AGENTS.md, .ai/, kod, konfigurację,
testy i dokumentację; pomijaj lokalne dane, raporty, wagi, .venv, cache, build
i egg-info. Istniejący ZIP jest migawką i nie odświeża się sam.
