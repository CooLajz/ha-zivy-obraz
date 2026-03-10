[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

# Home Assistant – Živý obraz integration

Home Assistant integrace pro službu **Živý obraz (zivyobraz.eu)**.

Integrace umožňuje:

- číst data z panelů Živého obrazu (export API)
- posílat hodnoty z Home Assistant do Živého obrazu (import API)

Díky tomu lze jednoduše zobrazovat data z Home Assistant na e-paper displejích nebo dashboardech Živého obrazu.

---


# 🇨🇿 Česky

## Instalace

### Metoda 1: Přes HACS (doporučeno)

1. Ujistěte se, že je HACS nainstalovaný
2. Běžte do HACS > Integrations
3. Klikněte na tři tečky vpravo a zvolte > Custom repositories
4. Přidejte tuto URL: https://github.com/CooLajz/ha-zivy-obraz.git
5. Vyhledejte "Živý Obraz" a stiskněte install
6. Restartujte Home Assistant
7. Jděte do nastavení > Devices & Services > Add Integration
8. Vyhledejte "Živý Obraz" a vyplňte konfiguraci

### Metoda 2: Manuální instalace

Download or clone this repository
Copy the custom_components/zivy_obraz folder to your Home Assistant custom_components/ directory
Restart Home Assistant
Go to Settings > Devices & Services > Add Integration
Search for "Živý Obraz" and follow the instructions

1. Stáhněte nebo naklonujte tento repozitář
2. Překopírujte adresář zivy_obraz do adresáře custom_components/ v instalaci Home Assistanta
3. Restartujte Home Assistant
4. Jděte do nastavení > Devices & Services > Add Integration
5. Vyhledejte "Živý Obraz" a vyplňte konfiguraci

---

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

Například: 300


Integrace pak každých 300 sekund odešle aktuální hodnoty entit.

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

export_key najdete po přihlášení do služby v záložce hodnoty (vyberte pouze klíč, pozor ať v klíči NENÍ i &epapers=json, atd...)

---

### Import key (volitelné)

Pokud chcete posílat data z Home Assistant do Živého obrazu.

https://in.zivyobraz.eu/?import_key=IMPORT_KEY

import_key najdete po přihlášení do služby v záložce hodnoty

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


---

# 🇬🇧 English

## Features

This integration connects **Home Assistant** with **Živý obraz (zivyobraz.eu)** dashboards.

It supports both:

- reading panel data from Živý obraz
- pushing Home Assistant entity states to Živý obraz

## Installation

### Method 1: Via HACS (recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed
2. Go to HACS > Integrations
3. Click the three dots in the top right corner > Custom repositories
4. Add this URL: https://github.com/CooLajz/ha-zivy-obraz.git
5. Search for "Živý Obraz" and install
6. Restart Home Assistant
7. Go to **Settings** > **Devices & Services** > **Add Integration**
8. Search for "Živý Obraz" and follow the instructions

### Method 2: Manual installation

1. Download or clone this repository
2. Copy the `custom_components/zivy_obraz` folder to your Home Assistant `custom_components/` directory
3. Restart Home Assistant
4. Go to **Settings** > **Devices & Services** > **Add Integration**
5. Search for "Živý Obraz" and follow the instructions


---

### Reading data from Živý obraz

The integration reads panel data using the export API: http://out.zivyobraz.eu/?export_key=XXXX&epapers=json


Sensors are automatically created in Home Assistant:

- `sensor`
- `binary_sensor`

These entities represent data from Živý obraz panels.

---

### Sending data to Živý obraz

Home Assistant entity states can be pushed to Živý obraz using the import API: https://in.zivyobraz.eu/?import_key=XXXX

Values are sent as HTTP GET parameters.

Example request: https://in.zivyobraz.eu/?import_key=XXXX&house.sensor_kitchen_temperature=23.5

---

### Entity selection using Home Assistant Labels

Entities are selected using **Home Assistant Labels**.

Simply add the label: ZivyObraz

All entities with this label will be sent automatically.

Advantages:

- no entity list configuration
- no YAML
- instant changes
- easy filtering in Home Assistant UI

---

### Variable prefix

A prefix can be configured to support multiple Home Assistant installations.

Example: prefix = house


Resulting variables:
house.sensor_kitchen_temperature, 
house.sensor_livingroom_temperature


---

### Push interval

The update interval defines how often entity states are sent.

Example: 300 seconds


---

### Automatic request batching

If the generated URL becomes too long, the integration automatically splits it into multiple requests.

This prevents URL length limits.

---

## Configuration

The integration requires the following configuration.

### Export key

Used to read data from Živý obraz.

The integration automatically builds the endpoint: http://out.zivyobraz.eu/?export_key=EXPORT_KEY&epapers=json


---

### Import key (optional)

Required if you want to send Home Assistant data to Živý obraz.

https://in.zivyobraz.eu/?import_key=IMPORT_KEY

---

### Label

Label used to select entities to send.

Default: ZivyObraz

---

### Prefix

Optional variable prefix.

Example:
house
garage
office


---

### Push interval

Defines how often values are sent to Živý obraz.

---

## Quick start

1. Install the integration
2. Enter your **Export key**
3. (optional) Enter **Import key**
4. Add label **ZivyObraz** to entities
5. Done

Home Assistant will automatically start sending entity states to Živý obraz.

---

## Disclaimer

This project is **not affiliated with the Živý obraz service**.
