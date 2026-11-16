const TYPE = "zivy-obraz-card";
const BRAND = "Živý Obraz";
const METRICS = [
  ["battery", "battery_percent", "mdi:battery", "Battery", "Baterie", "Batéria"],
  ["contact", "last_contact", "mdi:clock-outline", "Last contact", "Poslední kontakt", "Posledný kontakt"],
  ["wifi", "rssi", "mdi:wifi", "Wi-Fi signal", "Signál Wi-Fi", "Signál Wi-Fi"],
];
const text = (hass, en, cs, sk) =>
  ({ cs, sk })[hass?.language?.split("-")[0]] ?? en;
const previewEntries = (hass) => Object.values(hass?.entities ?? {}).filter(
  (entry) => entry.platform === "zivy_obraz" && entry.entity_id.startsWith("image.")
    && entry.translation_key === "preview",
);
const device = (hass, entry) => hass?.devices?.[entry?.device_id];
const title = (hass, entry) => {
  const panel = device(hass, entry);
  return panel?.name_by_user || panel?.name
    || hass?.states?.[entry?.entity_id]?.attributes?.friendly_name || entry?.entity_id || BRAND;
};

const formatMetric = (hass, key, value) => {
  if (key === "contact") {
    const date = new Date(value.state);
    if (!Number.isNaN(date.getTime())) {
      return new Intl.DateTimeFormat(hass.locale?.language ?? hass.language, {
        year: "numeric", month: "numeric", day: "numeric",
        hour: "2-digit", minute: "2-digit",
        timeZone: hass.locale?.time_zone === "server" ? hass.config?.time_zone : undefined,
      }).format(date);
    }
  }
  return hass.formatEntityState?.(value)
    ?? [value.state, value.attributes.unit_of_measurement].filter(Boolean).join(" ");
};

const hasDarkBackground = (card) => {
  const background = getComputedStyle(card).backgroundColor;
  const rgb = background.match(/^rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\s*\)$/);
  if (!rgb || (rgb[4] !== undefined && Number(rgb[4]) < 0.5)) return false;
  const [, red, green, blue] = rgb;
  return (0.2126 * red + 0.7152 * green + 0.0722 * blue) < 128;
};

class ZivyObrazCard extends HTMLElement {
  #hass;
  #themeFrame;
  static getConfigElement() {
    return document.createElement(`${TYPE}-editor`);
  }

  static getStubConfig() {
    return { invert_in_dark_mode: false };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" }).innerHTML = `
      <style>
        ha-card { overflow: hidden; }
        header { padding: 12px 16px; font-weight: 600; overflow-wrap: anywhere; }
        a { color: inherit; text-decoration: none; }
        a:hover { text-decoration: underline; }
        img { display: block; width: 100%; height: auto; }
        .preview.themed { isolation: isolate; background: var(--primary-text-color, white); }
        .preview.themed img { filter: invert(1); mix-blend-mode: multiply; }
        [hidden] { display: none !important; }
        p { margin: 0; padding: 12px 16px; color: var(--secondary-text-color); }
        dl { display: flex; flex-wrap: wrap; gap: 6px 16px; margin: 0; padding: 10px 16px; }
        dl:empty { display: none; }
        dl div { max-width: 100%; }
        dt { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
        ha-icon { --mdc-icon-size: 16px; flex-shrink: 0; color: var(--secondary-text-color); }
        dd { display: flex; align-items: center; gap: 5px; margin: 0; overflow-wrap: anywhere; }
      </style>
      <ha-card>
        <header><a></a></header>
        <div class="preview"><img loading="lazy" decoding="async" hidden></div>
        <p role="status" hidden></p>
        <dl></dl>
      </ha-card>`;
    this.image = this.shadowRoot.querySelector("img");
    this.status = this.shadowRoot.querySelector("p");
    this.image.addEventListener("error", () => {
      this.image.hidden = true;
      this.status.hidden = false;
    });
    this.image.addEventListener("load", () => {
      this.image.hidden = false;
      this.status.hidden = true;
    });
  }

  setConfig(config) {
    this.config = config;
    this.update();
  }

  set hass(hass) {
    this.#hass = hass;
    this.update();
  }

  connectedCallback() {
    this.updateTheme();
  }

  disconnectedCallback() {
    cancelAnimationFrame(this.#themeFrame);
    this.#themeFrame = undefined;
  }

  updateTheme() {
    if (!this.isConnected || this.#themeFrame !== undefined) return;
    this.#themeFrame = requestAnimationFrame(() => {
      this.#themeFrame = undefined;
      const inverted = this.config?.invert_in_dark_mode === true
        && (this.#hass?.themes?.darkMode === true
          || hasDarkBackground(this.shadowRoot.querySelector("ha-card")));
      this.image.parentElement.classList.toggle("themed", inverted);
    });
  }

  getCardSize() { return 5; }

  update() {
    const hass = this.#hass;
    if (!hass || !this.config) return;
    const id = this.config.entity;
    const entry = hass.entities?.[id];
    const state = hass.states?.[id];
    const heading = this.shadowRoot.querySelector("a");
    heading.textContent = title(hass, entry ?? { entity_id: id });
    if (entry?.device_id) {
      heading.href = `/config/devices/device/${encodeURIComponent(entry.device_id)}`;
    } else {
      heading.removeAttribute("href");
    }
    this.image.alt = heading.textContent;
    this.updateTheme();
    const picture = state?.attributes.entity_picture;
    const source = state?.state !== "unavailable" && typeof picture === "string"
      && picture.startsWith("/api/image_proxy/")
      ? `${picture}${picture.includes("?") ? "&" : "?"}v=${encodeURIComponent(state.state)}`
      : null;
    this.status.textContent = id
      ? text(hass, "Screen preview unavailable", "Náhled obrazovky není dostupný", "Náhľad obrazovky nie je dostupný")
      : text(hass, "Select an ePaper", "Vyberte ePaper", "Vyberte ePaper");
    if (source !== this.source) {
      this.source = source;
      if (source) {
        this.image.src = source;
        this.image.hidden = false;
        this.status.hidden = true;
      } else {
        this.image.removeAttribute("src");
        this.image.hidden = true;
        this.status.hidden = false;
      }
    }

    const metrics = this.shadowRoot.querySelector("dl");
    const sensors = entry?.device_id ? Object.values(hass.entities).filter(
      (item) => item.device_id === entry.device_id && item.platform === "zivy_obraz"
        && item.entity_id.startsWith("sensor."),
    ) : [];
    metrics.replaceChildren(...METRICS.flatMap(([key, translation, icon, ...labels]) => {
      if (this.config[`show_${key}`] === false) return [];
      const sensor = sensors.find((item) => item.translation_key === translation);
      const value = hass.states[sensor?.entity_id];
      if (!value) return [];
      const item = document.createElement("div");
      const label = document.createElement("dt");
      label.textContent = text(hass, ...labels);
      item.title = label.textContent;
      const symbol = document.createElement("ha-icon");
      symbol.setAttribute("icon", icon);
      symbol.setAttribute("aria-hidden", "true");
      const reading = document.createElement("dd");
      reading.append(symbol, formatMetric(hass, key, value));
      item.append(label, reading);
      return [item];
    }));
  }
}

class ZivyObrazCardEditor extends HTMLElement {
  #hass;

  constructor() {
    super();
    this.attachShadow({ mode: "open" }).innerHTML = `
      <style>
        :host { display: grid; gap: 12px; padding: 8px 0; }
        label { display: flex; align-items: center; gap: 8px; }
        label:first-of-type { display: grid; }
        select { max-width: 100%; padding: 8px; font: inherit; color: var(--primary-text-color);
          background: var(--card-background-color); border: 1px solid var(--divider-color); }
        input { accent-color: var(--primary-color); }
      </style>
      <label><span></span><select name="entity"></select></label>
      <label><input type="checkbox" name="invert_in_dark_mode"><span></span></label>
      <label><input type="checkbox" name="show_battery"><span></span></label>
      <label><input type="checkbox" name="show_contact"><span></span></label>
      <label><input type="checkbox" name="show_wifi"><span></span></label>`;
    this.shadowRoot.addEventListener("change", ({ target }) => {
      this.config = { ...this.config, [target.name]: target.type === "checkbox" ? target.checked : target.value };
      this.dispatchEvent(new CustomEvent("config-changed", {
        detail: { config: this.config }, bubbles: true, composed: true,
      }));
    });
    this.update();
  }

  setConfig(config) {
    this.config = config;
    this.update();
  }

  set hass(hass) {
    this.#hass = hass;
    this.update();
  }

  update() {
    const hass = this.#hass;
    const config = this.config ?? {};
    const select = this.shadowRoot.querySelector("select");
    const entries = previewEntries(hass);
    const selected = config.entity ?? "";
    const options = [new Option(text(hass, "Select an ePaper", "Vyberte ePaper", "Vyberte ePaper"), "")];
    for (const entry of entries) options.push(new Option(title(hass, entry), entry.entity_id));
    if (selected && !entries.some((entry) => entry.entity_id === selected)) {
      options.push(new Option(selected, selected));
    }
    select.replaceChildren(...options);
    select.value = selected;
    const labels = [
      "ePaper",
      text(hass, "Match theme colors", "Barvy podle motivu", "Farby podľa motívu"),
      ...METRICS.map((metric) => text(hass, ...metric.slice(3))),
    ];
    this.shadowRoot.querySelectorAll("label span").forEach((label, index) => {
      label.textContent = labels[index];
    });
    for (const input of this.shadowRoot.querySelectorAll("input")) {
      input.checked = input.name === "invert_in_dark_mode"
        ? config[input.name] === true : config[input.name] !== false;
    }
  }
}

if (!customElements.get(TYPE)) {
  customElements.define(TYPE, ZivyObrazCard);
  customElements.define(`${TYPE}-editor`, ZivyObrazCardEditor);
  (window.customCards ??= []).push({
    type: TYPE, name: BRAND, preview: false,
    description: "ePaper screen preview and device status",
  });
}
