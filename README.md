[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

# Home Assistant – Živý obraz integration

Home Assistant integrace pro službu **Živý obraz (zivyobraz.eu)**.

Integrace umožňuje:

- číst data z panelů Živého obrazu (export API)
- posílat hodnoty z Home Assistant do Živého obrazu (import API)

Díky tomu lze jednoduše zobrazovat data z Home Assistant na e-paper displejích nebo dashboardech Živého obrazu.

---

# 🇨🇿 Česky

## Funkce

Integrace podporuje:

### Čtení dat z Živého obrazu
Integrace dokáže načítat data z exportního API: http://out.zivyobraz.eu/?export_key=XXXX&epapers=json

Z exportovaných dat jsou automaticky vytvořeny:

- `sensor`
- `binary_sensor`

Tyto entity reprezentují data z panelů Živého obrazu.

---

### Odesílání dat do Živého obrazu

Integrace může také odesílat hodnoty entit z Home Assistant na Živý obraz pomocí import API: https://in.zivyobraz.eu/?import_key=XXXX

Hodnoty jsou odesílány jako HTTP GET parametry.

Příklad výsledného requestu: https://in.zivyobraz.eu/?import_key=XXXX&dum.sensor_teplota_kuchyne=23.5


---

### Výběr entit pomocí Home Assistant Labels

Entity, které se mají odesílat do Živého obrazu, se vybírají pomocí **Labels**.

Stačí přidat label: ZivyObraz


Integrace automaticky odešle všechny entity s tímto labelem.

Výhody tohoto přístupu:

- žádná konfigurace seznamu entit
- žádný YAML
- okamžitá změna po přidání labelu
- snadné filtrování v seznamu entit

---

### Prefix proměnných

Pro podporu více Home Assistant instalací lze nastavit **prefix**.

Příklad: prefix = dum

Výsledné proměnné v Živém obrazu:
dum.sensor_teplota_kuchyne,
dum.sensor_teplota_obyvak


To umožňuje používat více Home Assistant serverů se stejným Živým obrazem.

---

### Interval odesílání

Odesílání hodnot lze nastavit v sekundách.

Například: 60


Integrace pak každých 60 sekund odešle aktuální hodnoty entit.

---

### Automatické dělení dlouhých URL

Pokud by URL obsahovala příliš mnoho parametrů, integrace ji automaticky rozdělí do více requestů.

Tím se zabrání překročení maximální délky URL.

---

## Konfigurace

Po instalaci integrace je potřeba vyplnit:

### Export key

Klíč pro čtení dat z Živého obrazu.

Integrace automaticky vytvoří URL: http://out.zivyobraz.eu/?export_key=EXPORT_KEY&epapers=json


---

### Import key (volitelné)

Pokud chcete posílat data z Home Assistant do Živého obrazu.

https://in.zivyobraz.eu/?import_key=IMPORT_KEY


---

### Label

Label pro entity, které se mají odesílat.

Výchozí hodnota: ZivyObraz


---

### Prefix

Volitelný prefix proměnných.

Například:
dum
byt
chata
garaz


---

### Interval odesílání

Jak často se mají hodnoty odesílat do Živého obrazu.

---

## Postup použití

1️⃣ Nainstaluj integraci

2️⃣ Zadej **Export key**

3️⃣ (volitelně) zadej **Import key**

4️⃣ Přidej label `ZivyObraz` k entitám

5️⃣ Hotovo

Integrace začne automaticky odesílat hodnoty.

