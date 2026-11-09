# training

Etap 4.1, część 1: `domain/masking.py` maskuje prefiks obrazu i instrukcji.
`workflows/one_step.py` sprawdza NF4 + LoRA dla Qwen3-VL: cztery przykłady train,
microbatch 1, jeden krok optymalizatora, zamrożona część wizualna, pomiary
straty, gradientów, zmian adaptera i pamięci. Wynik jest diagnozą techniczną.

Nie ma interfejsu pełnego treningu. Parametry pilotażu nie są zatwierdzeniem
hiperparametrów pracy inżynierskiej. Próba Qwen3.5 wymaga odrębnej weryfikacji.
[Instrukcja](../../../docs/vlm/INSTRUKCJA_POWERSHELL_4_1.md).
