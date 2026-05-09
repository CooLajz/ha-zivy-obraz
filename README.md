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

## Neplatné stavy entit

Ve výchozím nastavení se entity se stavem `unknown`, `unavailable` nebo
chybějícím stavem neodesílají a zobrazí se v diagnostice `Failed entities`
s důvodem `invalid_state`. Prázdný textový stav `""` je validní hodnota a
odesílá se beze změny.

Při vyplněném `Import key` lze zapnout konfigurační přepínač
`Send N/A for invalid entity states`. Pokud je zapnutý, integrace místo
neplatné hodnoty odešle do Živého obrazu hodnotu `N/A`. Entita se pak počítá
jako úspěšně odeslaná, takže nezvyšuje `Failed entities`. Na eINK displeji je
díky tomu vidět například `N/A` nebo `N/A °C` místo staré hodnoty.

## Ruční odeslání hodnot

Hodnoty lze odeslat okamžitě pomocí služby:

```yaml
service: zivy_obraz.push
```

Bez parametrů služba odešle všechny načtené instance integrace, které mají
nastavený Import key.

Volitelný parametr `send_all` může přepsat nastavení odesílání jen změněných
stavů pro jedno ruční volání:

```yaml
service: zivy_obraz.push
data:
  send_all: true
```

- `send_all: true` odešle všechny vybrané entity
- `send_all: false` odešle jen změněné entity
- bez `send_all` se použije nastavení integrace

Parametr `dry_run` provede stejnou přípravu dat, ale neodešle HTTP request na
Import API:

```yaml
service: zivy_obraz.push
data:
  name: "Chata"
  dry_run: true
```

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

## Náhled a návratová data odeslání

Služba `zivy_obraz.push` umí vracet response data se seznamem hodnot, které
byly odeslané, přeskočené nebo chybové. Při `dry_run: true` vrátí stejnou
strukturu jako náhled bez skutečného odeslání.

```yaml
entry_id: "abc123"
name: "Chata"
status: "would_push"
dry_run: true
send_only_changed: true
request_batches: 1
pushed:
  - variable: "sensor_teplota_kuchyne"
    value: "23.5"
skipped:
  - variable: "sensor_vlhkost_kuchyne"
    value: "48"
    reason: "unchanged"
failed:
  - variable: "sensor_neznamy_stav"
    reason: "invalid_state"
```

Parametr `send_all` funguje stejně jako u služby `zivy_obraz.push`:

- `send_all: true` zobrazí náhled všech vybraných entit
- `send_all: false` zobrazí náhled jen změněných entit
- bez `send_all` se použije nastavení integrace

---

## Zařízení instance, ovládání a diagnostika

Integrace vytvoří pro danou instanci samostatné zařízení:

```
Živý Obraz - Název instance
```

Pod tímto zařízením jsou dostupné provozní konfigurační entity:

- `Import refresh interval` - interval načítání dat z Export API v sekundách
- `Overdue tolerance` - tolerance zpoždění v minutách
- `Create overdue notifications` - zapnutí/vypnutí oznámení při overdue stavu
- `Push interval` - interval automatického odesílání do Import API v sekundách
- `Automatic push` - zapnutí/vypnutí automatického odesílání
- `Send only changed entity states` - odesílat pouze změněné hodnoty entit
- `Send N/A for invalid entity states` - odeslat `N/A` místo neplatných stavů

Push nastavení a tlačítko `Push values now` se vytvoří pouze při vyplněném
`Import key`.

Intervaly `Import refresh interval` a případně `Push interval` lze nastavit v
rozsahu 60 až 86400 sekund. `Overdue tolerance` se automaticky hlídá tak, aby
nebyla nižší než aktuální interval načítání přepočtený na minuty.

Stejné zařízení obsahuje také akční tlačítka:

- `Refresh import now` - okamžitě stáhne aktuální data z Export API
- `Push values now` - okamžitě odešle hodnoty podle aktuálního nastavení, pokud
  je vyplněný `Import key`

Ruční tlačítka neresetují automatické časovače. `Refresh import now` zachová
původní plánovaný čas dalšího automatického načtení a `Push values now` zachová
původní plánovaný čas dalšího automatického odeslání.

Pod tímto zařízením jsou také dostupné diagnostické entity pro poslední
odeslání:

- `Last successful push`
- `Push status`
- `Pushed entities`
- `Skipped entities`
- `Failed entities`
- `Request batches`
- `Push problem`
- `Next push`

Senzor `Push status` obsahuje v atributech poslední pokus, poslední úspěšné
odeslání a poslední chybu. Během běhu odesílání přejde krátce do stavu
`sending`. Senzor
`Pushed entities` obsahuje omezený náhled odesílaných proměnných a senzor
`Skipped entities` obsahuje omezený náhled proměnných přeskočených kvůli
nezměněné hodnotě. Senzor `Failed entities` obsahuje omezený náhled proměnných,
které se nepodařilo odeslat, včetně důvodů jako `invalid_state` nebo
`url_too_long`. Pokud je zapnutá volba `Send N/A for invalid entity states`,
neplatné stavy se odešlou jako `N/A` a do `Failed entities` se nedostanou.
Pokud je zapnuté odesílání jen změněných stavů, po restartu se odešlou všechny
vybrané entity a následně už pouze entity se změněným stavem.
U senzorů se při odesílání použije stejná prezentační přesnost hodnoty, jakou
Home Assistant používá pro `Přesnost zobrazení`, pokud ji daná verze Home
Assistantu poskytuje.
Když není co odeslat, `Push status` bude `no_new_data` a `Last successful push`
se aktualizuje na čas úspěšně dokončeného běhu. Náhledy jsou
omezené na prvních 50 položek, aby zbytečně nezvětšovaly stavové atributy Home
Assistantu. Pokud je automatické odesílání vypnuté, `Next push` bude `Unknown`.

Stejné zařízení obsahuje také diagnostické entity pro načítání dat z Export API:

- `Last successful sync`
- `Sync status`
- `Next sync`
- `Device count`
- `Sync problem`

Senzor `Sync status` obsahuje v atributech poslední pokus, poslední úspěšnou
synchronizaci a poslední chybu. Během načítání dat přejde krátce do stavu
`syncing`.

U panelů, které posílají `battery_volts`, integrace navíc vytváří bateriovou
diagnostiku:

- `Battery days since last charge`
- `Battery charge detection status`

Detekce posledního nabití je konzervativní odhad z denních průměrů napětí.
Integrace nejdřív nasbírá tři validní dny jako baseline. Další validní den se
nabití zapíše až při nárůstu denního průměru alespoň o `0.15 V` proti průměru
předchozích tří validních dní. Stačí jeden validní vzorek za den, takže detekce
funguje i pro displeje, které se refreshují jen jednou denně. Historie detekce
se ukládá do Home Assistant storage a přežije restart. Hodnoty nad `4.20 V` se
do detekce ani do celkového minima/maxima nezahrnují, aby případné nabíjecí
špičky nezkreslovaly baseline. Integrace záměrně nevytváří senzor aktuálního
nabíjení, protože napětí baterie se u různých desek, baterek a intervalů refresh
chová příliš rozdílně.
Celkové minimum a maximum validního napětí baterie jsou dostupné jako atributy
senzoru `Battery voltage`.
Datum posledního nabití je dostupné jako atribut senzoru
`Battery days since last charge`.

Hlavní provozní entity jsou ve výchozím stavu zapnuté. Detailní diagnostické
entity jako `Push status`, `Sync status`, počítadla a náhledy proměnných jsou
ve výchozím stavu skryté a lze je zapnout ručně v Home Assistant.

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

Pokud je zapnuté odesílání jen změněných hodnot, lze vybraným entitám přidat
ještě odvozený label `<label> Always`, například:

```
ZivyObraz Always
```

Entita musí mít hlavní label i tento odvozený label. Taková entita se odešle
při každém intervalu, i když se její hodnota nezměnila. Odvozený label se
nezakládá automaticky; pokud neexistuje, integrace ho tiše ignoruje.

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

## Provozní nastavení přes entity

Intervaly, tolerance zpoždění a přepínače pro oznámení a odesílání se nastavují
přímo přes entity zařízení `Živý Obraz - Název instance`. Díky tomu je lze
měnit z dashboardu, automatizací nebo skriptem bez otevření nastavení integrace.

Změna intervalu načítání nebo odesílání přeplánuje příslušný časovač od nově
nastaveného času. Ruční tlačítka naopak časovače neposouvají.

---

## Automatické dělení dlouhých URL

Pokud URL obsahuje příliš mnoho parametrů, integrace ji automaticky rozdělí do více requestů.

---

# Konfigurace

Nastavení integrace je rozdělené na dvě stránky.

## Načítání dat / Export API

`Export key` slouží ke čtení dat panelů a najdete ho po přihlášení do služby v
sekci **Účet**.

```
http://out.zivyobraz.eu/?export_key=EXPORT_KEY&epapers=json
```

Pokud vyplníte `Group ID`, načtou se pouze panely z této skupiny. Pokud pole
necháte prázdné, načtou se všechny panely pod daným účtem.

---

## Odesílání dat / Import API

`Import key` je volitelný a slouží k odesílání hodnot z Home Assistantu do
Živého obrazu. Najdete ho po přihlášení do služby v sekci **Účet**.

```
https://in.zivyobraz.eu/?import_key=IMPORT_KEY
```

Pokud `Import key` nevyplníte, push tlačítko, push diagnostika a push
konfigurační entity se nevytvoří.

---

## Send N/A for invalid entity states

Volitelný konfigurační přepínač pro odesílání do Import API. Pokud je zapnutý,
hodnoty entit ve stavu `unknown`, `unavailable` nebo bez dostupného stavu se
odešlou jako `N/A` místo toho, aby se zařadily mezi failed entity. Prázdný
textový stav `""` se odesílá beze změny.

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

# Použití

1️⃣ Nainstalujte integraci  
2️⃣ Zadejte **Export key**  
3️⃣ (volitelně) zadejte **Import key**  
4️⃣ Přidejte label `ZivyObraz` k entitám  
5️⃣ Hotovo

Pokud je vyplněný Import key a zapnuté automatické odesílání, integrace začne
automaticky odesílat hodnoty. Provozní nastavení lze následně měnit přes entity
na zařízení instance.

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

## Invalid entity states

By default, entities with state `unknown`, `unavailable`, or a missing state are
not sent and appear in `Failed entities` with the `invalid_state` reason. An
empty text state `""` is a valid value and is sent unchanged.

When an `Import key` is configured, the `Send N/A for invalid entity states`
config switch can be enabled. It sends `N/A` to Živý Obraz instead of the
invalid value. The entity is counted as successfully pushed, so it does not increase
`Failed entities`. This makes the eINK display show values such as `N/A` or
`N/A °C` instead of keeping an old value.

## Manual push

Values can be sent immediately using the service:

```yaml
service: zivy_obraz.push
```

Without parameters, the service pushes all loaded integration instances that
have an Import key configured.

The optional `send_all` parameter can override the send-only-changed setting for
one manual call:

```yaml
service: zivy_obraz.push
data:
  send_all: true
```

- `send_all: true` sends all selected entities
- `send_all: false` sends only changed entities
- without `send_all`, the integration setting is used

The `dry_run` parameter prepares the same data without making an HTTP request
to the Import API:

```yaml
service: zivy_obraz.push
data:
  name: "Cottage"
  dry_run: true
```

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

## Push response and dry-run preview

The `zivy_obraz.push` service can return response data with values that were
pushed, skipped, or reported as failed. With `dry_run: true`, it returns the
same structure as a preview without sending anything.

```yaml
entry_id: "abc123"
name: "Cottage"
status: "would_push"
dry_run: true
send_only_changed: true
request_batches: 1
pushed:
  - variable: "sensor_kitchen_temperature"
    value: "23.5"
skipped:
  - variable: "sensor_kitchen_humidity"
    value: "48"
    reason: "unchanged"
failed:
  - variable: "sensor_unknown_state"
    reason: "invalid_state"
```

The `send_all` parameter works the same way as for `zivy_obraz.push`:

- `send_all: true` previews all selected entities
- `send_all: false` previews only changed entities
- without `send_all`, the integration setting is used

---

## Instance device, controls, and diagnostics

The integration creates a separate device for the integration instance:

```
Živý Obraz - Instance name
```

This device exposes operational config entities:

- `Import refresh interval` - Export API refresh interval in seconds
- `Overdue tolerance` - overdue tolerance in minutes
- `Create overdue notifications` - enable/disable overdue notifications
- `Push interval` - scheduled Import API push interval in seconds
- `Automatic push` - enable/disable scheduled push
- `Send only changed entity states` - send only changed entity values
- `Send N/A for invalid entity states` - send `N/A` instead of invalid states

Push settings and the `Push values now` button are created only when an
`Import key` is configured.

`Import refresh interval` and, when available, `Push interval` can be set from
60 to 86400 seconds. `Overdue tolerance` is kept at least as high as the current
refresh interval converted to minutes.

The same device also exposes action buttons:

- `Refresh import now` - fetch current data from the Export API immediately
- `Push values now` - send values immediately using the current settings, when
  an `Import key` is configured

Manual buttons do not reset scheduled timers. `Refresh import now` keeps the
previously scheduled next automatic refresh time, and `Push values now` keeps
the previously scheduled next automatic push time.

The device also exposes diagnostic entities for the last push attempt:

- `Last successful push`
- `Push status`
- `Pushed entities`
- `Skipped entities`
- `Failed entities`
- `Request batches`
- `Push problem`
- `Next push`

The `Push status` sensor exposes the last attempt, last successful push, and
last error as attributes. While a push is running, it briefly changes to
`sending`. The
`Pushed entities` sensor exposes a bounded preview of pushed variables and the
`Skipped entities` sensor exposes a bounded preview of variables skipped because
their value did not change. The `Failed entities` sensor exposes a bounded
preview of variables that could not be sent, including reasons such as
`invalid_state` or `url_too_long`. When `Send N/A for invalid entity states` is
enabled, invalid states are sent as `N/A` and do not appear in
`Failed entities`. When sending only changed states is enabled, all selected
entities are sent after restart and then only entities with changed states are
sent. For sensors, pushed values use the same presentation precision Home
Assistant uses for `Display precision`, when the installed Home Assistant
version provides it. When there is nothing new to send, `Push status` is
`no_new_data` and `Last successful push` is updated to the successful run time.
Previews are limited to the first 50 items to avoid oversized Home Assistant
state attributes. When scheduled push is disabled, `Next push` is `Unknown`.

The same device also exposes Export API synchronization diagnostic entities:

- `Last successful sync`
- `Sync status`
- `Next sync`
- `Device count`
- `Sync problem`

The `Sync status` sensor exposes the last attempt, last successful sync, and
last error as attributes. While data is being fetched, it briefly changes to
`syncing`.

Panels that report `battery_volts` also get battery diagnostics:

- `Battery days since last charge`
- `Battery charge detection status`

Last charge detection is a conservative estimate based on daily voltage
averages. The integration first collects three valid days as a baseline. A later
valid day is marked as charged only when its daily average increases by at least
`0.15 V` compared with the average of the previous three valid days. One valid
sample per day is enough, so detection works for displays that refresh only once
per day. Detection history is stored in Home Assistant storage and survives
restarts. Values above `4.20 V` are excluded from charge detection and from the
overall minimum/maximum sensors so charging spikes do not distort the baseline.
The integration intentionally does not expose a current charging binary sensor
because voltage behavior differs too much between boards, batteries, and refresh
intervals.
The overall minimum and maximum valid battery voltage are available as
attributes on the `Battery voltage` sensor.
The last charge timestamp is available as an attribute on the
`Battery days since last charge` sensor.

Main operational entities are enabled by default. Detailed diagnostic entities
such as `Push status`, `Sync status`, counters, and variable previews are hidden
by default and can be enabled manually in Home Assistant.

---

## Selecting entities using Labels

Entities are selected using Home Assistant **Labels**.

Add label:

```
ZivyObraz
```

All entities with this label will be automatically sent.

When sending only changed states is enabled, selected entities can also use the
derived `<label> Always` label, for example:

```
ZivyObraz Always
```

The entity must have both the main label and this derived label. Such an entity
is sent on every interval, even when its value did not change. The derived label
is not created automatically; if it does not exist, the integration silently
ignores it.

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

## Runtime settings through entities

Intervals, overdue tolerance, notification switches, and push switches are
configured directly through entities on the `Živý Obraz - Instance name`
device. They can be changed from dashboards, automations, or scripts without
opening the integration settings.

Changing the import or push interval reschedules the corresponding automatic
timer from the newly configured time. Manual action buttons do not move the
scheduled timers.

---

## Automatic splitting of long URLs

If a request becomes too long, the integration automatically splits it into multiple requests.

---

# Configuration

The integration setup is split into two pages.

## Data download / Export API

`Export key` is used to read panel data and is available on the Živý Obraz
website in **Account**.

```
http://out.zivyobraz.eu/?export_key=EXPORT_KEY&epapers=json
```

Fill `Group ID` to load only panels in that group. Leave it empty to load all
panels in the account.

---

## Data upload / Import API

`Import key` is optional and is used to send Home Assistant values to Živý
Obraz. It is available on the Živý Obraz website in **Account**.

```
https://in.zivyobraz.eu/?import_key=IMPORT_KEY
```

Without `Import key`, the push button, push diagnostics, and push config
entities are not created.

---

## Send N/A for invalid entity states

Optional Import API config switch. When enabled, entity values with state
`unknown`, `unavailable`, or no available state are sent as `N/A` instead of
being reported as failed entities. Empty text state `""` is sent unchanged.

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

# Usage

1️⃣ Install integration  
2️⃣ Enter **Export key**  
3️⃣ (Optional) enter **Import key**  
4️⃣ Add label `ZivyObraz` to entities  
5️⃣ Done

If an Import key is configured and automatic push is enabled, the integration
will automatically start sending values. Runtime settings can then be changed
through entities on the instance device.

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
