# Instrukcje projektu dla AI

Ten katalog znajduje się w głównym katalogu projektu, obok src/, configs/,
data/ i build/. Porządkuje zasady pracy nad projektem
market-levels-multimodal-finetuning i zapobiega utracie ustaleń między sesjami.

## Co przeczytać

| Plik | Przeznaczenie |
| --- | --- |
| [RULES.md](RULES.md) | Trwałe zasady architektury, konfiguracji, ochrony danych i pracy badawczej |
| [CURRENT_STATE.md](CURRENT_STATE.md) | Stan rzeczywisty, decyzje organizacyjne i ograniczenia; aktualizowany wraz z projektem |
| [WORKFLOW.md](WORKFLOW.md) | Kolejność pracy, polecenia, kontrole i przekazywanie wyników |

Główny [AGENTS.md](../AGENTS.md) kieruje agentów do tych instrukcji.
Narzędzie, które nie czyta AGENTS.md automatycznie, powinno dostać polecenie:
„Przeczytaj AGENTS.md i wskazane pliki .ai przed rozpoczęciem pracy”.
Samo istnienie katalogu nie gwarantuje odczytania go przez każde narzędzie.

## Źródła ustaleń

- Aktualne polecenie autora określa zakres pracy i może świadomie zmienić wcześniejsze decyzje.
- [configs/experiment.json](../configs/experiment.json) jest źródłem bieżących parametrów; nie twórz ich drugiej aktywnej kopii w instrukcjach.
- [DECYZJE_3_3.md](../docs/DECYZJE_3_3.md) zawiera zatwierdzone decyzje badawcze.
- [ARCHITECTURE.md](../docs/ARCHITECTURE.md) opisuje moduły i podział odpowiedzialności.
- [LICENCJA_DANYCH.md](../docs/LICENCJA_DANYCH.md) zachowuje ustalenia i otwarte kwestie licencyjne.
- [README.md](../README.md) opisuje uruchamianie.
- [REFACTORING_REPORT.md](../docs/REFACTORING_REPORT.md) jest raportem historycznym z etapów reorganizacji.

Stan implementacji ustalaj na podstawie aktualnego kodu, konfiguracji i testów.
Jeśli dokumentacja jest z nimi sprzeczna, nazwij rozbieżność i ustal jej przyczynę;
nie zmieniaj automatycznie parametrów badawczych, aby ukryć konflikt.
W szczególności późniejsze decyzje autora o usunięciu starego CLI i aktywacji
konfiguracji zastępują pierwotne wymagania zachowania starych modułów.

## Utrzymanie instrukcji

Po zmianie stanu implementacji aktualizuj CURRENT_STATE.md. RULES.md zmieniaj
wtedy, gdy zmieniają się rzeczywiste zasady. Aktualizuj WORKFLOW.md, jeśli zmienia
się sposób uruchamiania lub weryfikacji. Nie dopisuj dziennika każdej drobnej
edycji, duplikatów konfiguracji ani niepotwierdzonych sukcesów.
