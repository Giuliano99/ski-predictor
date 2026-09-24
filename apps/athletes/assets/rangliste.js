const state = { user: null, items: [], sortKey: "birthYear", sortDirection: "desc" };
const dom = {
  season: document.querySelector("#overview-season"), filters: [...document.querySelectorAll("[data-filter]")],
  sortButtons: [...document.querySelectorAll("[data-sort]")], reset: document.querySelector("#reset-filters"), body: document.querySelector("#overview-body"),
  count: document.querySelector("#overview-count"), notice: document.querySelector("#notice"),
};

function escapeHtml(value) { const node = document.createElement("div"); node.textContent = String(value ?? ""); return node.innerHTML; }
function decimal(value) { return Number.isFinite(Number(value)) ? Number(value).toLocaleString("de-DE", { minimumFractionDigits:2, maximumFractionDigits:2 }) : "–"; }

async function request(url, options = {}) {
  if (options.method && options.method !== "GET" && state.user?.csrfToken) options.headers = { ...(options.headers || {}), "X-CSRF-Token":state.user.csrfToken };
  const response = await fetch(url, options); let body = {};
  try { body = await response.json(); } catch { body = {}; }
  if (response.status === 401 || response.status === 403) { window.location.replace("/login/?next=/athleten/teamuebersicht.html"); throw new Error("Bitte anmelden."); }
  if (!response.ok) throw new Error(body.error?.message || `Fehler ${response.status}`);
  return body;
}

function filteredItems() {
  const values = Object.fromEntries(dom.filters.map((input) => [input.dataset.filter, input.value.trim()]));
  return state.items.filter((item) => (!values.gender || item.gender === values.gender) && (!values.ageClass || item.ageClass === values.ageClass));
}

function sortedItems(items) {
  const direction = state.sortDirection === "asc" ? 1 : -1, key = state.sortKey;
  return [...items].sort((left, right) => {
    const a = left[key], b = right[key];
    if (a == null) return b == null ? 0 : 1;
    if (b == null) return -1;
    return (typeof a === "string" ? a.localeCompare(b, "de") : Number(a) - Number(b)) * direction;
  });
}

function render() {
  const items = sortedItems(filteredItems()); dom.count.textContent = items.length;
  dom.sortButtons.forEach((button) => { button.dataset.indicator = button.dataset.sort === state.sortKey ? (state.sortDirection === "asc" ? "▲" : "▼") : ""; });
  dom.body.innerHTML = items.map((item) => `<tr>
    <td data-label="Athlet"><a class="athlete-link" href="/athleten/?athlete=${encodeURIComponent(item.athleteId)}"><strong>${escapeHtml(item.displayName)}</strong><small>${escapeHtml(item.fullName)}</small></a></td>
    <td data-label="Jahrgang">${escapeHtml(item.birthYear || "–")}</td><td data-label="AK">${escapeHtml(item.ageClass)}</td>
    <td data-label="Basiswert">${decimal(item.basePoints)}</td><td data-label="Aktuelle Punkte"><strong>${decimal(item.overallPoints)}</strong></td>
    <td data-label="SL">${decimal(item.slalomPoints)}</td><td data-label="RS">${decimal(item.giantSlalomPoints)}</td>
    <td data-label="Rang Jahrgang">${item.birthYearRank ? `#${item.birthYearRank}` : "–"}</td><td data-label="Rang AK">${item.ageClassRank ? `#${item.ageClassRank}` : "–"}</td>
  </tr>`).join("") || `<tr><td colspan="9">Keine passenden Athleten gefunden.</td></tr>`;
}

async function loadOverview() {
  dom.body.innerHTML = `<tr><td colspan="9">Punkte und Ränge werden berechnet …</td></tr>`;
  try {
    const payload = await request(`/api/v1/athlete-seasons/${encodeURIComponent(dom.season.value)}/overview`); state.items = payload.items; render();
  }
  catch (error) { dom.notice.textContent = error.message; dom.notice.hidden = false; }
}

async function initialize() {
  try {
    const identity = await request("/api/v1/auth/me"); state.user = identity.user;
    const collections = await request("/api/v1/collections");
    const seasons = [...new Set(collections.items.map((item) => item.seasonId).filter(Boolean))].sort().reverse();
    const now = new Date(), start = now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1, current = `${start}-${start + 1}`;
    dom.season.innerHTML = seasons.map((season) => `<option value="${season}">${season.replace("-","/")}</option>`).join("");
    dom.season.value = seasons.includes(current) ? current : seasons[0] || current;
    await loadOverview();
  } catch (error) { dom.notice.textContent = error.message; dom.notice.hidden = false; }
}

dom.filters.forEach((input) => input.addEventListener(input.tagName === "SELECT" ? "change" : "input", render));
dom.sortButtons.forEach((button) => button.addEventListener("click", () => { const key = button.dataset.sort; state.sortDirection = state.sortKey === key && state.sortDirection === "asc" ? "desc" : "asc"; state.sortKey = key; render(); }));
dom.reset.addEventListener("click", () => { dom.filters.forEach((input) => { input.value = ""; }); render(); });
dom.season.addEventListener("change", loadOverview);
initialize();
