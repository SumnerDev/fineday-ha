// Fine Day card for Home Assistant
//
// It's the Fine Day website's card (the same one the Webpage card shows) for one of
// your Fine Day places. Comes with the integration so it's already in Add card, and
// the place comes from the integration so there's no url to get right.

const EMBED = "https://www.sumnerd.co.nz/fineday/embed/";

const LABELS = { entity: "Place", theme: "Theme", days: "Days to list under today" };
const HELPERS = {
  entity: "Pick its Today sensor",
  theme: "Leave it empty to match Home Assistant's light or dark",
  days: "1 to 14, leave it empty for all of them",
};
const PICK = "Pick a place in the card's settings.";
const NO_PLACES = "No Fine Day places yet. Add one in Settings > Devices & services, then pick it here.";

const STYLE = `
  :host { display: block; height: 100%; }
  ha-card { height: 100%; overflow: hidden; }
  /* sections view gives us a height, masonry doesn't, so then it's the website card's shape.
     width has to be set or the ratio works out the width from the height instead */
  .frame { position: relative; width: 100%; height: 100%; aspect-ratio: 5 / 6; }
  iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; display: block; }
  .msg { padding: 16px; line-height: 1.5; color: var(--primary-text-color); }
`;

const hasPlaces = (hass) => Object.values(hass.entities || {}).some((e) => e.platform === "fineday");

class FineDayCard extends HTMLElement {
  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: { entity: { filter: { integration: "fineday", domain: "sensor", device_class: "enum" } } },
        },
        {
          name: "theme",
          selector: {
            select: {
              mode: "dropdown",
              options: [
                { value: "auto", label: "Same as Home Assistant" },
                { value: "light", label: "Light" },
                { value: "dark", label: "Dark" },
              ],
            },
          },
        },
        { name: "days", selector: { number: { min: 1, max: 14, mode: "box" } } },
      ],
      computeLabel: (s) => LABELS[s.name],
      computeHelper: (s) => HELPERS[s.name],
    };
  }

  static getStubConfig(hass) {
    // the first place's Today sensor, so it works the moment it's added
    const today = Object.values(hass.entities || {}).find((e) => e.platform === "fineday" && e.translation_key === "today");
    return today ? { entity: today.entity_id } : {};
  }

  setConfig(config) {
    const was = this._config && this._config.entity;
    this._config = { ...config };
    if (this._config.entity !== was) {
      this._place = null;
      this._asked = null;
    }
    this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  connectedCallback() {
    this._update();
  }

  disconnectedCallback() {
    // HA moves cards about (masonry evens out its columns, views come and go) and a moved
    // frame reloads anyway, so drop it here and make a fresh one when we're back on the page
    const frame = this.shadowRoot && this.shadowRoot.querySelector(".frame");
    if (frame) frame.remove();
  }

  getCardSize() {
    return 9; // about 450px, masonry only uses it to even out the columns
  }

  getGridOptions() {
    return { columns: 12, rows: 8, min_columns: 6, min_rows: 4 };
  }

  _update() {
    if (!this._config || !this._hass) return;
    const entity = this._config.entity;
    if (!entity) return this._say(hasPlaces(this._hass) ? PICK : NO_PLACES);

    // ask HA where that sensor's place is. again each time the sensor updates,
    // it's cheap and it picks up the daylight setting if that's been changed
    const st = this._hass.states[entity];
    const key = `${entity}|${st ? st.last_updated : ""}`;
    if (key !== this._asked) {
      this._asked = key;
      this._hass.callWS({ type: "fineday/place", entity_id: entity }).then(
        (place) => {
          if (this._asked !== key) return;
          this._place = place;
          this._update();
        },
        (err) => {
          if (this._asked !== key) return;
          if (err && err.code === "not_found") {
            this._place = null;
            this._say(`${entity} isn't a Fine Day sensor. ${PICK}`);
          } else {
            this._asked = null; // HA restarting or similar, leave it be and ask again next update
          }
        },
      );
    }
    if (this._place) this._show();
  }

  _show() {
    const p = this._place;
    const c = this._config;
    const dark = c.theme === "dark" || (c.theme !== "light" && !!(this._hass.themes && this._hass.themes.darkMode));
    const q = new URLSearchParams({ lat: p.latitude, lon: p.longitude, suburb: p.suburb });
    if (p.city) q.set("city", p.city);
    q.set("theme", dark ? "dark" : "light");
    q.set("bg", "transparent");
    if (p.daylight_only === false) q.set("daylight", "0");
    const days = parseInt(c.days, 10);
    if (days >= 1 && days <= 14) q.set("days", days);
    const src = `${EMBED}?${q}`;

    const root = this._root();
    let frame = root.querySelector("iframe");
    if (!frame) {
      if (!this.isConnected) return; // made once we're on the page, see disconnectedCallback
      // scripts only, it can't navigate the dashboard or open anything. and no referrer,
      // the website doesn't need to know your HA's address
      root.querySelector("ha-card").innerHTML =
        '<div class="frame"><iframe sandbox="allow-scripts allow-same-origin" referrerpolicy="no-referrer"></iframe></div>';
      frame = root.querySelector("iframe");
    }
    frame.title = `Fine Day for ${p.label}`;
    // a see-through page only stays see-through when its colour scheme matches ours
    frame.style.colorScheme = dark ? "dark" : "light";
    if (frame.getAttribute("src") !== src) frame.setAttribute("src", src);
  }

  _say(text) {
    const card = this._root().querySelector("ha-card");
    const div = document.createElement("div");
    div.className = "msg";
    div.textContent = text;
    card.replaceChildren(div);
  }

  _root() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" }).innerHTML = `<style>${STYLE}</style><ha-card></ha-card>`;
    return this.shadowRoot;
  }
}

// HA swaps in its own custom element registry as it starts up and this file can load before
// that happens. defined too early it lands in the browser's registry, HA can't see it and you
// get "Configuration error" every so often. so wait for HA's own element, then define
customElements.whenDefined("home-assistant").then(() => {
  if (customElements.get("fineday-card")) return;
  customElements.define("fineday-card", FineDayCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "fineday-card",
    name: "Fine Day",
    description: "Is it a good day to get the washing out? Today and the next two weeks for one of your Fine Day places.",
    preview: true,
    documentationURL: "https://github.com/SumnerDev/fineday-ha#on-your-dashboard",
    // HA 2026.6+: offered in Add card > By entity when you pick one of our sensors
    getEntitySuggestion: (hass, entityId) => {
      const ent = hass.entities && hass.entities[entityId];
      if (!ent || ent.platform !== "fineday") return null;
      const today = Object.values(hass.entities).find(
        (e) => e.platform === "fineday" && e.device_id === ent.device_id && e.translation_key === "today",
      );
      return { config: { type: "custom:fineday-card", entity: today ? today.entity_id : entityId } };
    },
  });
});
