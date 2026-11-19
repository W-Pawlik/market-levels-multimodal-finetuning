# Końcowa ewaluacja Qwen3-VL — szablon 4.6B

Status: niewypełniony. Nie wykonano produkcyjnej inferencji ani ewaluacji testowej
w ramach 4.6A. Brak liczb jakości nie oznacza wyniku zerowego.

## 1. Cel końcowej ewaluacji

Opisać jednorazowe porównanie NF4 i NF4 z wybranym adapterem, po zamknięciu treningu.

## 2. Potwierdzenie zamrożenia modelu

Przytoczyć FINAL_MODEL_SELECTION.json, rewizję, SHA-256 adaptera i manifestu,
konfigurację oraz niezależny audyt przygotowania. Nie zmieniać wyboru po teście.

## 3. Charakterystyka zbioru testowego

Podać manifest i separację czasową; 66 realnych okien, 33 BTC i 33 ETH,
120 świec 4h, 1024×768. Odnotować ograniczoną reprezentatywność i zależności rynkowe.

## 4. Konfiguracja inferencji

Udokumentować identyczność rewizji, procesora, template, promptu, kwantyzacji,
typów danych, kolejności ID i generowania; dwa osobne procesy oraz ewentualne resume.

## 5. Kontrole integralności

Zestawić hashe sesji, obu surowych przebiegów, danych i trzech raportów.
Zachować ostrzeżenia, błędy, kody, przerwania i pomiary zasobów.

## 6. Wyniki modelu bazowego NF4

Uzupełnić dopiero z oficjalnego summary.json. Nie przenosić wyników validation.

## 7. Wyniki modelu dostrojonego

Uzupełnić dopiero z oficjalnego summary.json, z pełnymi mianownikami metryk.

## 8. Oficjalne porównanie

Przytoczyć sparowane różnice P/R/F1, TP/FP/FN i JSON z comparison.json,
na wszystkich tolerancjach, bez rankingu nowych checkpointów.

## 9. Wyniki według instrumentu i strony

Podać BTC/ETH, supports/resistances i symbol×strona; sprawdzić sumy liczności.

## 10. Analiza przykładowych błędów

Opisać FP/FN, format, brak trafień i pełne zestawy. Dobór przykładów i regułę
remisów ujawnić. Ewentualną diagnostykę Markdown oddzielić od oceny oficjalnej.

## 11. Skuteczność poza validation

Omówić zgodność z etykietami w późniejszym okresie bez twierdzeń o rentowności.
MAE/ATR dotyczy dopasowanych par, nie wszystkich predykcji.

## 12. Ograniczenia badania

Mała próba, tylko dwa instrumenty i jeden interwał, algorytmiczne etykiety,
duży udział syntetyków w treningu, ograniczona LoRA, zamrożona wizja, 8 GB VRAM,
wybór dodatkowego eksperymentu po analizie validation; brak założenia niezależności okien.

## 13. Wnioski końcowe

Sformułować dopiero po zabezpieczeniu obu przebiegów i zweryfikowaniu raportów.
Nie uzupełniać oczekiwanymi ani fikcyjnymi wartościami testowego F1.
