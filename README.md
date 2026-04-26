# Home Assistant – Živý obraz Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![GitHub release](https://img.shields.io/github/release/CooLajz/ha-zivy-obraz.svg)](https://github.com/CooLajz/ha-zivy-obraz/releases)
[![License](https://img.shields.io/github/license/CooLajz/ha-zivy-obraz.svg)](LICENSE)
![Hassfest](https://github.com/CooLajz/ha-zivy-obraz/actions/workflows/hassfest.yaml/badge.svg)
![HACS Validation](https://github.com/CooLajz/ha-zivy-obraz/actions/workflows/hacs.yaml/badge.svg)

Home Assistant integrace pro službu **Živý obraz**  
https://zivyobraz.eu

Integrace umožňuje **obousměrnou komunikaci** mezi Home Assistant a službou Živý obraz:

- čtení dat z panelů Živého obrazu (Export API)
- odesílání hodnot z Home Assistant (Import API)

Díky tomu lze zobrazovat data z Home Assistant na e-paper displejích napojených na službu Živého obrazu a v Home Assistant zobrazovat stavy e-paper displejů ze služby Živý obraz.

---

# Table of Contents

- 🇨🇿 **Česky**
  - [Instalace](#instalace)
  - [Funkce](#funkce)
  - [Konfigurace](#konfigurace)
  - [Použití](#použití)
  - [Architektura](#architektura)

- 🇬🇧 **English**
  - [Installation](#installation)
  - [Features](#features)
  - [Configuration](#configuration)
  - [Usage](#usage)
  - [Architecture](#architecture-1)

- [Contribution](#contribution)

---

# 🇨🇿 Dokumentace (Česky)

## Screenshoty

**Seznam zařízení ze služby Živý obraz v Home Assistant**

<img width="1029" height="463" alt="image" src="https://github.com/user-attachments/assets/e7f070e5-5b02-4f0d-b973-71722696f1d4" />

**Detail zařízení**

<img width="1013" height="965" alt="image" src="https://github.com/user-attachments/assets/7d26f9a6-aba8-48db-96e7-f59afe7de7e8" />

---

# Instalace

## Instalace přes HACS (doporučeno)

1. Nainstalujte **HACS**
2. Otevřete **HACS → Integrations**
3. Klikněte na **tři tečky vpravo nahoře**
4. Vyberte **Custom repositories**
5. Přidejte repozitář

```
https://github.com/CooLajz/ha-zivy-obraz
```

Typ:

```
Integration
```

6. Vyhledejte **Živý Obraz**
7. Klikněte **Install**
8. Restartujte Home Assistant
9. Jděte do

```
Settings → Devices & Services → Add Integration
```

10. Vyhledejte **Živý Obraz**

---

## Manuální instalace

1. Stáhněte nebo naklonujte tento repozitář
2. Zkopírujte složku

```
custom_components/zivy_obraz
```

do adresáře `custom_components`

3. Restartujte Home Assistant
4. Přidejte integraci přes

```
Settings → Devices & Services → Add Integration
```

---

# Funkce

## Čtení dat ze Živého obrazu

Integrace načítá data z exportního API:

```
http://out.zivyobraz.eu/?export_key=XXXX&epapers=json
```

Z těchto dat se automaticky vytvoří entity:

- `sensor`
- `binary_sensor`

---

## Odesílání dat do Živého obrazu

Integrace může odesílat hodnoty z Home Assistant pomocí Import API:

```
https://in.zivyobraz.eu/?import_key=XXXX
```

Příklad requestu:

```
https://in.zivyobraz.eu/?import_key=XXXX&dum.sensor_teplota_kuchyne=23.5
```

## Ruční odeslání hodnot

Hodnoty lze odeslat okamžitě pomocí služby:

```yaml
service: zivy_obraz.push
```

Bez parametrů služba odešle všechny načtené instance integrace, které mají
nastavený Import key.

Konkrétní instanci lze vybrat podle jejího názvu:

```yaml
service: zivy_obraz.push
data:
  name: "Chata"
```

Nebo přes přesné ID config entry:

```yaml
service: zivy_obraz.push
data:
  entry_id: "abc123"
```

Pokud má více instancí stejný název, použijte `entry_id`.

---

## Ruční odeslání vlastních hodnot

Vlastní hodnoty lze odeslat službou:

```yaml
service: zivy_obraz.push_values
data:
  name: "Chata"
  values:
    - variable: "custom_message"
      value: "Ahoj z Home Assistantu"
    - variable: "custom_temperature"
      value: "23.5"
```

Pokud není vyplněn `name` ani `entry_id`, hodnoty se odešlou do všech
načtených instancí s nastaveným Import key.

---

## Diagnostika odesílání

Pokud je vyplněný Import key, integrace vytvoří pro danou instanci samostatné
diagnostické zařízení:

```
Živý Obraz - Název instance
```

Pod tímto zařízením jsou dostupné diagnostické entity pro poslední odeslání:

- `Last push`
- `Last successful push`
- `Push status`
- `Pushed entities`
- `Skipped entities`
- `Request batches`
- `Push problem`

Senzor `Push status` obsahuje v atributech poslední chybu. Senzor
`Pushed entities` obsahuje omezený náhled odesílaných proměnných a senzor
`Skipped entities` obsahuje omezený náhled přeskočených proměnných. Náhledy jsou
omezené na prvních 50 položek, aby zbytečně nezvětšovaly stavové atributy Home
Assistantu.

---

## Výběr entit pomocí Labels

Entity se vybírají pomocí **Home Assistant Labels**.

Stačí přidat label:

```
ZivyObraz
```

<img width="558" height="784" alt="image" src="https://github.com/user-attachments/assets/dfb035d7-e665-4a0b-bf30-1e6fcca13994" />

Integrace automaticky odešle všechny entity s tímto labelem.

Stejný label lze přidat i na celý device. V takovém případě integrace odešle všechny jeho viditelné a aktivní entity, takže není nutné tagovat každou entitu zvlášť.

Výhody:

- žádný YAML
- není nutné konfigurovat seznam entit
- změny jsou okamžité
- snadné filtrování

---

## Prefix proměnných

Pro více Home Assistant instalací lze nastavit prefix.

Například:

```
dum
```

Proměnné pak budou:

```
dum_sensor_teplota_kuchyne
dum_sensor_teplota_obyvak
```

---

## Interval aktualizace

Interval odesílání i stahování dat se nastavuje v sekundách.

Například:

```
300
```

Doporučujeme nastavit interval podle obnovy displejů.

---

## Automatické dělení dlouhých URL

Pokud URL obsahuje příliš mnoho parametrů, integrace ji automaticky rozdělí do více requestů.

---

# Konfigurace

Po instalaci je potřeba vyplnit:

## Export key

Klíč pro čtení dat.

```
http://out.zivyobraz.eu/?export_key=EXPORT_KEY&epapers=json
```

Klíč najdete po přihlášení do služby v sekci **Účet**.

---

## Import key (volitelné)

Pro odesílání dat.

```
https://in.zivyobraz.eu/?import_key=IMPORT_KEY
```

Klíč najdete po přihlášení do služby v sekci **Účet**.

---

## Label

Výchozí label:

```
ZivyObraz
```

---

## Prefix

Volitelný prefix.

Například:

```
dum
byt
chata
garaz
```

---

## Interval

Určuje jak často se data odesílají a stahují.

---

# Použití

1️⃣ Nainstalujte integraci  
2️⃣ Zadejte **Export key**  
3️⃣ (volitelně) zadejte **Import key**  
4️⃣ Přidejte label `ZivyObraz` k entitám  
5️⃣ Hotovo

Integrace začne automaticky odesílat hodnoty.

---

# Architektura

Integrace používá dvě API služby Živý obraz.

### Export API (čtení dat)

```
Home Assistant
      │
      ▼
out.zivyobraz.eu
      │
      ▼
panel data → Home Assistant sensors
```

### Import API (odesílání dat)

```
Home Assistant entities
      │
      ▼
in.zivyobraz.eu
      │
      ▼
Živý obraz displays
```

---

---

# 🇬🇧 Documentation (English)

## Installation

### Install via HACS (recommended)

1. Install **HACS**
2. Open **HACS → Integrations**
3. Click **three dots**
4. Select **Custom repositories**
5. Add repository

```
https://github.com/CooLajz/ha-zivy-obraz
```

Type:

```
Integration
```

6. Search for **Živý Obraz**
7. Click **Install**
8. Restart Home Assistant
9. Go to

```
Settings → Devices & Services → Add Integration
```

10. Search for **Živý Obraz**

---

## Manual installation

1. Download or clone this repository
2. Copy folder

```
custom_components/zivy_obraz
```

into `custom_components`

3. Restart Home Assistant
4. Add integration via

```
Settings → Devices & Services → Add Integration
```

---

# Features

## Reading data

The integration reads panel data from:

```
http://out.zivyobraz.eu/?export_key=XXXX&epapers=json
```

Entities created automatically:

- `sensor`
- `binary_sensor`

---

## Sending data

Home Assistant values can be sent using:

```
https://in.zivyobraz.eu/?import_key=XXXX
```

Example:

```
https://in.zivyobraz.eu/?import_key=XXXX&dum.sensor_teplota_kuchyne=23.5
```

## Manual push

Values can be sent immediately using the service:

```yaml
service: zivy_obraz.push
```

Without parameters, the service pushes all loaded integration instances that
have an Import key configured.

Select one instance by its configured name:

```yaml
service: zivy_obraz.push
data:
  name: "Cottage"
```

Or use the exact config entry ID:

```yaml
service: zivy_obraz.push
data:
  entry_id: "abc123"
```

If multiple instances share the same name, use `entry_id`.

---

## Manual custom value push

Send custom values using:

```yaml
service: zivy_obraz.push_values
data:
  name: "Cottage"
  values:
    - variable: "custom_message"
      value: "Hello from Home Assistant"
    - variable: "custom_temperature"
      value: "23.5"
```

If neither `name` nor `entry_id` is provided, values are sent to all loaded
instances with an Import key configured.

---

## Push diagnostics

When an Import key is configured, the integration creates a separate diagnostic
device for the integration instance:

```
Živý Obraz - Instance name
```

The device exposes diagnostic entities for the last push attempt:

- `Last push`
- `Last successful push`
- `Push status`
- `Pushed entities`
- `Skipped entities`
- `Request batches`
- `Push problem`

The `Push status` sensor exposes the last error as an attribute. The
`Pushed entities` sensor exposes a bounded preview of pushed variables and the
`Skipped entities` sensor exposes a bounded preview of skipped variables.
Previews are limited to the first 50 items to avoid oversized Home Assistant
state attributes.

---

## Selecting entities using Labels

Entities are selected using Home Assistant **Labels**.

Add label:

```
ZivyObraz
```

All entities with this label will be automatically sent.

---

## Variable prefix

Supports multiple Home Assistant installations.

Example:

```
dum
```

Variables will appear as:

```
dum_sensor_teplota_kuchyne
dum_sensor_teplota_obyvak
```

---

## Update interval

Send and fetch interval in seconds.

Example:

```
300
```

---

## Automatic splitting of long URLs

If a request becomes too long, the integration automatically splits it into multiple requests.

---

# Configuration

## Export key

Used for reading data.

```
http://out.zivyobraz.eu/?export_key=EXPORT_KEY&epapers=json
```

---

## Import key (optional)

Used for sending data.

```
https://in.zivyobraz.eu/?import_key=IMPORT_KEY
```

---

## Label

Default:

```
ZivyObraz
```

---

## Prefix

Optional prefix.

```
dum
byt
chata
garaz
```

---

## Interval

Defines how often data is sent and fetched.

---

# Usage

1️⃣ Install integration  
2️⃣ Enter **Export key**  
3️⃣ (Optional) enter **Import key**  
4️⃣ Add label `ZivyObraz` to entities  
5️⃣ Done

The integration will automatically start sending values.

---

# Architecture

### Export API

```
Home Assistant → out.zivyobraz.eu → panel data → sensors
```

### Import API

```
Home Assistant entities → in.zivyobraz.eu → displays
```

---

# Contribution

Contributions are welcome.

If you find a bug or have an idea for improvement:

- open an **Issue**
- or create a **Pull Request**

Please include:

- description of the problem
- Home Assistant version
- logs if relevant
