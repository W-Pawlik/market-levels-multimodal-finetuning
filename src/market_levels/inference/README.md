# inference

Etap 4.1, część 1: `domain/inputs.py` definiuje wejście bez etykiety i wiadomość
obraz–instrukcja. `io/pilot.py` wybiera osiem validation według dat oraz zapisuje
surowy tekst bez naprawiania. `workflows/pilot.py` wykonuje lokalną inferencję
w dwóch budżetach obrazu, kontroluje udział encodera wizualnego i zapisuje pomiary.
`workflows/scoring.py` używa istniejących funkcji oceny pojedynczego przykładu;
jawnie oznacza wynik ośmiu obrazów jako pomocniczy. Pełny ewaluator nie zmienia się.

Pilot nie udostępnia testu ani zewnętrznego API inferencyjnego.
[Instrukcja](../../../docs/vlm/INSTRUKCJA_POWERSHELL_4_1.md).
