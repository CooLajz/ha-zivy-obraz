# Home Assistant – Živý obraz Integration

[![HACS](https://img.shields.io/badge/HACS-Default-blue.svg)](https://hacs.xyz)
[![GitHub release](https://img.shields.io/github/release/CooLajz/ha-zivy-obraz.svg)](https://github.com/CooLajz/ha-zivy-obraz/releases)
[![License](https://img.shields.io/github/license/CooLajz/ha-zivy-obraz.svg)](LICENSE)
![Hassfest](https://github.com/CooLajz/ha-zivy-obraz/actions/workflows/hassfest.yaml/badge.svg)
![HACS Validation](https://github.com/CooLajz/ha-zivy-obraz/actions/workflows/hacs.yaml/badge.svg)

Home Assistant integrace pro službu [**Živý Obraz**](https://zivyobraz.eu/?page=o-sluzbe)

Integrace umožňuje **obousměrnou komunikaci** mezi Home Assistant a službou Živý obraz:

- čtení dat z panelů Živého obrazu (Export API)
- odesílání hodnot z Home Assistant (Import API)
- ovládání zařízení Živého obrazu (Command API)

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
3. Vyhledejte **Živý Obraz**
4. Klikněte **Install**
5. Restartujte Home Assistant
6. Jděte do

```
Settings → Devices & Services → Add Integration
```

7. Vyhledejte **Živý Obraz**

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

## Ovládání zařízení přes Command API

Po zadání `Command key` integrace vytvoří u každého panelu ovládací entity:

- `OTA firmware updates`
- `Refresh display`
- `Rotate display 180 degrees`
- `Show AP connect screen`
- `Jednorázově vynutit aktualizaci Wi-Fi`
- `Invert display colors`
- `Interval kontroly při vypnutém obnovování displeje` - doba v minutách, po které
  zařízení při vypnutém obnovování displeje znovu ověří aktuální nastavení

Invertování barev má tři stavy:

- `Podle nastavení obrazovky` odstraní individuální přepsání a použije
  nastavení obrazovky ve službě Živý obraz
- `Invertovat` zapne dodatečnou negaci barev vůči nastavení obrazovky
- `Neinvertovat` dodatečnou negaci vypne

Po úspěšné odpovědi Command API se stav entity v Home Assistant aktualizuje
okamžitě. Následující načtení Export API stav znovu autoritativně synchronizuje.

Přepínač `Jednorázově vynutit aktualizaci Wi-Fi` nastaví požadavek pro příští
probuzení zařízení. Zařízení provede úplný Wi-Fi scan a znovu se připojí k
nejsilnějšímu přístupovému bodu se stejným SSID. Po zpracování se přepínač
automaticky vypne. Čekající požadavek nelze ručně zrušit.

Pro hromadné změny a textové hodnoty slouží služba `zivy_obraz.command`:

```yaml
action: zivy_obraz.command
data:
  target: "group:6"
  ota: true
  refresh_screen: true
```

Služba podporuje vlastnosti `caption`, `note`, `pin_key`, `invert_screen`,
`force_wifi_full_scan`, `ota`, `refresh_screen`, `rotate_180`,
`show_ap_connect_screen` a `sleep_forced`.

Možné cíle:

- bez `target` nebo `target: "all"` - všechna zařízení spravovaná vybranou
  instancí
- `group:<id>` - skupina s číselným ID
- `group:0`, `group:default` nebo `default` - výchozí skupina zařízení bez
  `group_id`
- `device:<id>` - zařízení podle unikátního Device ID
- `device:<mac>` - zařízení podle MAC adresy

Příklad výchozí skupiny:

```yaml
action: zivy_obraz.command
data:
  target: "default"
  ota: false
```

Příklad konkrétního zařízení:

```yaml
action: zivy_obraz.command
data:
  target: "device:80:b5:4e:df:f8:78"
  note: "Test"
```

Instanci lze volitelně vybrat pomocí `entry_id` nebo `name`. Pokud instance
není vybraná, příkaz se zpracuje ve všech načtených instancích, které mají
nastavený Command key. Instance bez Command key se přeskočí. Pokud používáte
instanci filtrovanou pomocí `Group ID`, prázdný `target` se automaticky přeloží
na tuto skupinu.

Pokud má více instancí stejný název, použijte `entry_id`; parametry `entry_id`
a `name` nelze použít současně.

Hodnota `invert_screen` ve službě přijímá `default`, `invert` nebo
`do_not_invert`. Kvůli kompatibilitě jsou podporované také booleovské hodnoty.
`caption` může mít 1 až 255 znaků, `note` nejvýše 255 znaků a `sleep_forced`
hodnotu 5 až 240 minut. `pin_key` je pouze zapisovací tajná hodnota: integrace
ho neukládá do dat zařízení a maskuje ho v návratových a diagnostických datech.

Prázdná hodnota `note` poznámku smaže a prázdná hodnota `pin_key` odstraní PIN.

Úspěšná odpověď může obsahovat `updated: 0`, pokud už všechna cílová zařízení
požadovanou hodnotu mají. Takový výsledek není chyba.

Služba vrací response data s použitým cílem, počtem aktualizací a seznamem
ovlivněných zařízení. Při zpracování více instancí jsou výsledky v seznamu
`entries`. Command key a PIN jsou v návratových datech maskované.

Senzory `Device ID` a `Content source` jsou diagnostické a ve
výchozím stavu zakázané; lze je ručně povolit v detailu zařízení. Číselná
entita `Interval kontroly při vypnutém obnovování displeje` je při nastaveném
Command key standardně viditelná a umožňuje nastavit hodnotu 5 až 240 minut.
Používá se pouze tehdy, když je `Refresh display` vypnutý.

Diagnostický senzor `Lokální IP adresa` je ve výchozím stavu viditelný. Jeho
stav obsahuje `local_ip` a v atributech jsou dostupné veřejná IP z `last_ip` a
MAC adresa zařízení.

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
neplatné hodnoty odešle do Živého obrazu náhradní hodnotu nastavenou v
možnostech integrace. Výchozí hodnota je `N/A`. Entita se pak počítá jako
úspěšně odeslaná, takže nezvyšuje `Failed entities`. Na eINK displeji je díky
tomu vidět například `N/A`, `--` nebo `N/A °C` místo staré hodnoty.

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

Náhradní hodnota pro neplatné stavy se nastavuje v možnostech integrace na
stránce `Data upload / Import API`.

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

`Push status` obsahuje poslední pokus, poslední úspěšné odeslání a poslední
chybu. Senzory `Pushed entities`, `Skipped entities` a `Failed entities`
nabízejí náhled zpracovaných proměnných včetně důvodů selhání, například
`invalid_state` nebo `url_too_long`. Při zapnutém `Send N/A for invalid entity
states` se neplatné stavy odešlou s náhradní hodnotou a mezi chyby se nezařadí.
Při odesílání pouze změněných stavů se po restartu jednou odešlou všechny
vybrané entity a poté už jen změny. Hodnoty senzorů respektují nastavení
`Přesnost zobrazení`, pokud ho daná verze Home Assistantu podporuje.
Pokud není co odeslat, stav je `no_new_data`; při vypnutém automatickém
odesílání je `Next push` neznámý.

Stejné zařízení obsahuje také diagnostické entity pro načítání dat z Export API:

- `Last successful sync`
- `Sync status`
- `Next sync`
- `Device count`
- `Sync problem`

`Sync status` obsahuje poslední pokus, poslední úspěšnou synchronizaci a
poslední chybu.

U panelů, které posílají `battery_volts`, integrace navíc vytváří bateriovou
diagnostiku:

- `Battery days since last charge`
- `Battery charge detection status`

Poslední nabití se odhaduje z denních průměrů napětí po vytvoření třídenní
baseline. Nárůst alespoň o `0.15 V` se vyhodnotí jako nabití; historie se ukládá
a přežije restart Home Assistantu. Stačí jeden validní vzorek za den, takže
detekce funguje i u panelů obnovovaných jednou denně. Senzory `Battery` a
`Battery voltage` zobrazují vyhlazenou hodnotu, zatímco surová hodnota a celkové
minimum a maximum jsou dostupné v atributech. Datum posledního nabití je
atributem senzoru `Battery days since last charge`.

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

# Konfigurace

Nastavení integrace je rozdělené na stránky pro Export API, Import API a
Command API.

## Načítání dat / Export API

`Export key` slouží ke čtení dat panelů a najdete ho po přihlášení do služby v
sekci **Účet**.

```
http://out.zivyobraz.eu/?export_key=EXPORT_KEY&epapers=json
```

Pokud vyplníte `Group ID`, načtou se pouze panely z této skupiny. Pokud pole
necháte prázdné, načtou se všechny panely pod daným účtem.

U existující konfigurace je uložený `Export key` v nastavení skrytý. Pro jeho
výměnu zaškrtněte `Změnit Export key`; následně se zobrazí prázdné pole pro
nový klíč.

---

## Odesílání dat / Import API

`Import key` je volitelný a slouží k odesílání hodnot z Home Assistantu do
Živého obrazu. Najdete ho po přihlášení do služby v sekci **Účet**.

```
https://in.zivyobraz.eu/?import_key=IMPORT_KEY
```

Pokud `Import key` nevyplníte, push tlačítko, push diagnostika a push
konfigurační entity se nevytvoří.

U existující konfigurace je uložený `Import key` v nastavení skrytý. Volba
`Změnit nebo odebrat Import key` zobrazí prázdné pole; pokud ho necháte prázdné,
Import key se odebere a automatické odesílání se vypne.

---

## Ovládání zařízení / Command API

`Command key` je volitelný a slouží k ovládání panelů. Najdete ho po přihlášení
do služby Živý obraz v sekci **Účet**.

Při zadání nebo výměně se Command key před uložením ověří, aniž by se změnilo
nastavení zařízení. Neplatný klíč se neuloží a formulář zobrazí chybu.

Bez Command key se ovládací entity panelů nevytvoří a daná instance se při
hromadném volání služby `zivy_obraz.command` přeskočí. U existující konfigurace
je klíč skrytý; volba `Změnit nebo odebrat Command key` zobrazí prázdné pole pro
jeho výměnu nebo odebrání.

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

1. Nainstalujte integraci.
2. Zadejte **Export key**.
3. Volitelně zadejte **Import key**.
4. Volitelně zadejte **Command key**.
5. Přidejte label `ZivyObraz` k entitám odesílaným přes Import API.
6. Hotovo.

Pokud je vyplněný Import key a zapnuté automatické odesílání, integrace začne
automaticky odesílat hodnoty. Provozní nastavení lze následně měnit přes entity
na zařízení instance.

---

# Architektura

Integrace používá tři API služby Živý obraz.

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

### Command API (ovládání zařízení)

```
Home Assistant controls and services
      │
      ▼
cmd.zivyobraz.eu
      │
      ▼
device settings → Export API state synchronization
```

---

# 🇬🇧 Documentation (English)

## Installation

### Install via HACS (recommended)

1. Install **HACS**
2. Open **HACS → Integrations**
3. Search for **Živý Obraz**
4. Click **Install**
5. Restart Home Assistant
6. Go to

```
Settings → Devices & Services → Add Integration
```

7. Search for **Živý Obraz**

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

## Controlling devices through the Command API

After a `Command key` is configured, the integration creates control entities
for every panel:

- `OTA firmware updates`
- `Refresh display`
- `Rotate display 180 degrees`
- `Show AP connect screen`
- `Force one-time Wi-Fi update`
- `Invert display colors`
- `Display refresh-disabled check interval` - number of minutes before a device with
  display refresh disabled checks its current settings again

Display color inversion has three states:

- `Use display setting` removes the device-specific override and uses the
  display setting configured in the Živý Obraz service
- `Invert` enables an additional color negation against the display setting
- `Do not invert` disables the additional color negation

After a successful Command API response, the Home Assistant entity state is
updated immediately. A later Export API refresh synchronizes the authoritative
state again.

The `Force one-time Wi-Fi update` switch schedules a request for the device's
next wake-up. The device performs a full Wi-Fi scan and reconnects to the
strongest access point with the same SSID. The switch turns off automatically
after the request is processed. A pending request cannot be cancelled manually.

Use the `zivy_obraz.command` service for bulk changes and text properties:

```yaml
action: zivy_obraz.command
data:
  target: "group:6"
  ota: true
  refresh_screen: true
```

The service supports `caption`, `note`, `pin_key`, `invert_screen`,
`force_wifi_full_scan`, `ota`, `refresh_screen`, `rotate_180`,
`show_ap_connect_screen`, and `sleep_forced`.

Supported targets:

- no `target` or `target: "all"` - all devices managed by the selected
  integration instance
- `group:<id>` - a group with a numeric ID
- `group:0`, `group:default`, or `default` - the default group containing
  devices without a `group_id`
- `device:<id>` - a device selected by its unique Device ID
- `device:<mac>` - a device selected by its MAC address

Default group example:

```yaml
action: zivy_obraz.command
data:
  target: "default"
  ota: false
```

Single-device example:

```yaml
action: zivy_obraz.command
data:
  target: "device:80:b5:4e:df:f8:78"
  note: "Test"
```

An integration instance can optionally be selected using `entry_id` or `name`.
When no instance is selected, all loaded instances with a configured Command
key are processed. Instances without a Command key are skipped. For an instance
filtered by `Group ID`, an empty `target` is automatically translated to that
group.

If multiple instances share the same name, use `entry_id`; `entry_id` and
`name` cannot be used together.

The `invert_screen` service field accepts `default`, `invert`, or
`do_not_invert`. Boolean values remain supported for compatibility. `caption`
accepts 1–255 characters, `note` accepts up to 255 characters, and
`sleep_forced` accepts 5–240 minutes. `pin_key` is a write-only secret: the
integration does not store it in device data and masks it in response and
diagnostic data.

An empty `note` clears the note, and an empty `pin_key` removes the PIN.

A successful response may contain `updated: 0` when all targeted devices
already have the requested value. This is not an error.

The service returns response data containing the effective target, update count,
and affected devices. When multiple instances are processed, results are in the
`entries` list. The Command key and PIN are masked in response data.

The `Device ID` and `Content source` sensors are diagnostic entities that
are disabled by default and can be enabled manually on the device page. The
`Display refresh-disabled check interval` number entity is visible by default
when a Command key is configured and allows setting 5–240 minutes. The value is
used only while `Refresh display` is disabled.

The `Local IP address` diagnostic sensor is enabled by default. Its state
contains `local_ip`, while the public IP from `last_ip` and the device MAC
address are available as attributes.

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
config switch can be enabled. It sends the fallback value configured in the
integration options to Živý Obraz instead of the invalid value. The default
fallback is `N/A`. The entity is counted as successfully pushed, so it does not
increase `Failed entities`. This makes the eINK display show values such as
`N/A`, `--`, or `N/A °C` instead of keeping an old value.

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

The invalid-state fallback value is configured in the integration options on
the `Data upload / Import API` page.

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

`Push status` exposes the last attempt, last successful push, and last error.
The `Pushed entities`, `Skipped entities`, and `Failed entities` sensors provide
previews of processed variables, including failure reasons such as
`invalid_state` or `url_too_long`. With `Send N/A for invalid entity states`
enabled, invalid states are sent with the configured fallback and are not
reported as failed. With send-only-changed enabled, the first push after a
restart sends all selected entities and later pushes send only changes. Sensor
values respect Home Assistant `Display precision` when supported. When there is
nothing to send, the status is `no_new_data`; when scheduled push is disabled,
`Next push` is unknown.

The same device also exposes Export API synchronization diagnostic entities:

- `Last successful sync`
- `Sync status`
- `Next sync`
- `Device count`
- `Sync problem`

`Sync status` exposes the last attempt, last successful sync, and last error.

Panels that report `battery_volts` also get battery diagnostics:

- `Battery days since last charge`
- `Battery charge detection status`

The last charge is estimated from daily voltage averages after a three-day
baseline is established. An increase of at least `0.15 V` is treated as a
charge, and the history is stored across Home Assistant restarts. One valid
sample per day is enough, so detection also works for panels refreshed once per
day. The `Battery` and `Battery voltage` sensors show a smoothed value, while the
raw value and overall minimum and maximum are available as attributes. The last
charge date is an attribute of `Battery days since last charge`.

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

# Configuration

The integration setup contains separate pages for the Export API, Import API,
and Command API.

## Data download / Export API

`Export key` is used to read panel data and is available on the Živý Obraz
website in **Account**.

```
http://out.zivyobraz.eu/?export_key=EXPORT_KEY&epapers=json
```

Fill `Group ID` to load only panels in that group. Leave it empty to load all
panels in the account.

For an existing configuration, the stored `Export key` is hidden in options.
Enable `Change Export key` to reveal an empty field for a replacement key.

---

## Data upload / Import API

`Import key` is optional and is used to send Home Assistant values to Živý
Obraz. It is available on the Živý Obraz website in **Account**.

```
https://in.zivyobraz.eu/?import_key=IMPORT_KEY
```

Without `Import key`, the push button, push diagnostics, and push config
entities are not created.

For an existing configuration, the stored `Import key` is hidden in options.
Enable `Change or remove Import key` to reveal an empty field. Leaving it empty
removes the Import key and disables automatic push.

---

## Device control / Command API

`Command key` is optional and is used to control panels. It is available on the
Živý Obraz website in **Account**.

When a Command key is entered or replaced, the integration validates it before
saving without changing any device settings. Invalid keys are not saved and the
form displays an error.

Without a Command key, panel control entities are not created and the instance
is skipped by account-wide `zivy_obraz.command` service calls. For an existing
configuration, the key is hidden in options. Enable `Change or remove Command
key` to reveal an empty field for replacing or removing it.

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

1. Install the integration.
2. Enter the **Export key**.
3. Optionally enter the **Import key**.
4. Optionally enter the **Command key**.
5. Add the `ZivyObraz` label to entities sent through the Import API.
6. Done.

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

### Command API

```
Home Assistant controls → cmd.zivyobraz.eu → device settings → Export API sync
```
