# Ograniczenia i niepewności refinement v2

- Nie wykonano dostrajania rynku ani oceny po 60 przykładów. Nie ma podstaw do
  twierdzenia, że nowy wariant jest lepszy. Cztery empiryczne profile powstaną
  dopiero po uruchomieniu procedury przez autora. Nic nie jest approved.
- Tolerancje, wagi i kara są ustaloną polityką diagnostyczną, nie dowodem
  zgodności rozkładów. Kara ogranicza pogorszenie, ale nie wyklucza go twardo.
- Mała, skończona siatka może mieć minimum na brzegu. Nie rozszerzamy jej
  automatycznie. Oryginalna zmienność jest dodatkowym kandydatem baseline.
- Referencja 36 okien i późniejsza diagnostyka 60 okien pochodzą z treningu;
  mogą się nakładać. Nowe seedy sprawdzają stabilność symulacji na tym samym
  rynku, nie generalizację na validation/test. Nie nazywać tego niezależnym testem.
- Ablacja porównuje dwa osobno dostrojone profile. Różnica nie jest czystym
  efektem usunięcia mieszanki przy identycznych parametrach zmienności.
- Profil przechowuje kopię źródła i wszystkie próby, a generator kopiuje audyt
  do metadanych. Nowe partie mogą być znacznie większe. To świadomy koszt
  samodzielnego audytu. Nie dopuszczono łańcuchów refinement profilu refinement.
- Walidator sprawdza spójność audytu i przelicza cel z cech. Nie ponawia całej
  symulacji i nie dowodzi autentyczności danych na podstawie samego JSON.
  Hash bajtów pliku źródłowego ma znaczenie podczas kalibracji; później
  weryfikowana jest także kopia źródła przez hash kanoniczny.
- Źródłowy CSV musi mieć identyczne bajty jak podczas pierwotnej kalibracji,
  nawet jeśli zmiana dotyczyłaby przyszłego okresu. Przy rozbieżności procedura
  odmawia pracy zamiast po cichu zmieniać pochodzenie lub stary profil.
- Bezpośrednia tabela refinement wymaga wszystkich czterech grup i takich
  samych seedów/liczności. Nie uśrednia różnych profili. Starsze raporty bez
  refinement nadal mogą mieć starszy zestaw wariantów.
- Testowano Windows PowerShell i CPython 3.13.15, bez macierzy innych systemów
  i wersji Pythona. Golden hashes obowiązują wskazaną wersję CPython; na innych
  wersjach test golden jawnie pomija porównanie, inne kontrakty są testowane.
- Handoff nie zawiera danych rynku, lokalnych profili, raportów eksperymentów
  ani środowiska. Autor musi zachować je osobno. Instalacja i testy nie pobierają
  rynku ani nie uruchamiają dużej kalibracji.
