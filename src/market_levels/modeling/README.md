# modeling

Etap 4.1, część 1: `config.py` waliduje ograniczony pilot dwóch oficjalnych
checkpointów. `io/checkpoints.py` sprawdza tożsamość, rewizję, limit transferu,
miejsce oraz SHA pobranych wag. `io/runtime.py` ładuje lokalny model/procesor
i mierzy GPU/RAM/czas. Zależności ML są ładowane dopiero przy uruchomieniu próby.

CLI: `python -m market_levels.cli.vlm_feasibility`.
[Instrukcja](../../../docs/vlm/INSTRUKCJA_POWERSHELL_4_1.md).
