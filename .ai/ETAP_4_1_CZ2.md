# Uzupełnienie stanu projektu — etap 4.1, część 2

2026-11-10. Dokument uzupełnia historyczny `CURRENT_STATE.md` bez zmiany
istniejących plików, zgodnie ze zleceniem tej iteracji tworzącej nowe artefakty.

Autor zatwierdził Qwen/Qwen3-VL-2B-Instruct, rewizję
`89644892e4d85e24eaac8bacfd4f463576704203`. Nie ponawiać wyboru modeli ani Qwen3.5.

Nowy ograniczony CLI: `python -m market_levels.cli.vlm_stability`
(`preflight`, `train`, `resave`, `reload`, `validate`), konfiguracja
`configs/vlm/stability.json`. Ciężkie biblioteki nadal tylko w osobnym środowisku
VLM; zwykły zestaw unittest pozostaje offline i bez zależności ML.

Wykonano osiem kolejnych aktualizacji AdamW na 32 deterministycznie wybranych
train, bez OOM i NaN/Inf, z aktualizacją LoRA. Peak globalny 7948/8192 MiB,
stałe allocated po kroku, ale rosnące reserved do 14 364 MiB pod WDDM. To nie
potwierdza bezpiecznej pamięci wielogodzinnego treningu.

Zapis/odczyt pełnego modelu NF4 + adapter działa w nowych procesach. Dodatkowy
`resave` kontroluje dosłownie stan i generację przed serializacją oraz po odczycie,
bez dodatkowych aktualizacji. Nie oceniać jakości adaptera po ośmiu krokach
jako końcowego modelu.

Pełna bazowa walidacja BF16 i NF4: po 36/36, 0 poprawnych JSON, micro-F1=0,
TP=0, FP=0, FN=147. Wszystkie odpowiedzi otaczają JSON Markdownem. Nie naprawiano
odpowiedzi ani ewaluatora. Precision i MAE nieokreślone, recall=0.
NF4 bez adaptera jest głównym odniesieniem przyszłego NF4 + adapter;
BF16 jest pomocniczy. Typy zamrożonych parametrów NF4 dopasowano do PEFT/QLoRA.

Oficjalny ewaluator wymaga wyjścia w `results/evaluation/` lub `results/diagnostics/`.
Wyniki tej części znajdują się w `results/evaluation/vlm41-cz2-20261110-1840-{bf16,nf4}`;
zapieczętowane kopie są w katalogu iteracji. Nie osłabiać ograniczenia lokalizacji.
CLI `compare` nie służy do porównania dwóch wariantów bazowych o innej precyzji.

Windows 1455 podczas pierwszego ładowania BF16 wynikał z presji pamięci hosta:
usługa powiadomień zajmowała około 54 GiB. Autor osobno zatwierdził restart tej
konkretnej usługi; powróciła do Running, a bazowe walidacje wykonano po zwolnieniu
pamięci. Nie zmieniano bibliotek, checkpointu, promptu ani pliku stronicowania.

Wyniki i lokalny adapter: `results/vlm41-cz2-20261110-1840/`,
adapter pod `train/adapter/`. Oryginalne dane/historyczne wyniki pozostają chronione.
Nie uruchomiono testu, pełnego treningu 698 przykładów ani etapu 4.2.
Końcowe testy: 334/334 OK, bez pominięć, oraz 3/3 osobne testy maskowania.
Kontrola SHA potwierdziła 12 920/12 920 niezmienionych historycznych plików,
w tym 3212/3212 plików zbioru produkcyjnego.

Szczegóły i aktualne polecenia:

- [Raport części 2](../docs/vlm/RAPORT_4_1_WYBOR_MODELU_CZ2.md).
- [PowerShell części 2](../docs/vlm/INSTRUKCJA_POWERSHELL_4_1_CZ2.md).

Po przekazaniu wyników czekać na decyzję autora o etapie 4.2.
