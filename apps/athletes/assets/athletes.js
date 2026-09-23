const state = { athletes: [], selectedId: null, analytics: null, seasonId: null, user: null };
const dom = {
  list: document.querySelector("#athlete-list"), search: document.querySelector("#athlete-search"), athleteSelect: document.querySelector("#athlete-select"),
  profile: document.querySelector("#profile"), empty: document.querySelector("#empty-profile"), notice: document.querySelector("#notice"),
  name: document.querySelector("#profile-name"), meta: document.querySelector("#profile-meta"), id: document.querySelector("#profile-id"), season: document.querySelector("#season-select"),
  points: document.querySelector("#metric-points"), pointsDate: document.querySelector("#metric-points-date"), rank: document.querySelector("#metric-rank"),
  races: document.querySelector("#metric-races"), racesDate: document.querySelector("#metric-races-date"), resultsMetric: document.querySelector("#metric-results"), starts: document.querySelector("#metric-starts"),
  chart: document.querySelector("#points-chart"), change: document.querySelector("#points-change"), ranking: document.querySelector("#ranking-details"), raceCount: document.querySelector("#race-count-details"),
  results: document.querySelector("#results"), resultCount: document.querySelector("#result-count-label"), logout: document.querySelector("#logout-button"),
};

function escapeHtml(value) { const node = document.createElement("div"); node.textContent = String(value ?? ""); return node.innerHTML; }
function decimal(value) { return Number.isFinite(Number(value)) ? Number(value).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "–"; }
function date(value) { if (!value) return "Kein Stichtag"; return new Intl.DateTimeFormat("de-DE", { day:"2-digit", month:"2-digit", year:"numeric" }).format(new Date(value)); }
function seconds(value) { if (!Number.isFinite(Number(value))) return "–"; const minutes = Math.floor(value / 60); return `${minutes}:${(value % 60).toFixed(2).padStart(5,"0")}`; }

async function request(url, options = {}) {
  if (options.method && options.method !== "GET" && state.user?.csrfToken) options.headers = { ...(options.headers || {}), "X-CSRF-Token": state.user.csrfToken };
  const response = await fetch(url, options); let body = {};
  try { body = await response.json(); } catch { body = {}; }
  if (response.status === 401 || response.status === 403) { window.location.replace("/login/?next=/athleten/"); throw new Error("Bitte anmelden."); }
  if (!response.ok) throw new Error(body.error?.message || `Fehler ${response.status}`);
  return body;
}

function filteredAthletes() {
  const query = dom.search.value.trim().toLocaleLowerCase("de");
  return state.athletes.filter((athlete) => !query || `${athlete.fullName} ${athlete.birthYear}`.toLocaleLowerCase("de").includes(query));
}

function renderAthletes() {
  const athletes = filteredAthletes();
  dom.list.innerHTML = athletes.map((athlete) => `<button class="athlete-button${athlete.id === state.selectedId ? " active" : ""}" data-athlete="${athlete.id}" type="button"><strong>${escapeHtml(athlete.displayName)}</strong><small>Jahrgang ${escapeHtml(athlete.birthYear || "–")} · ${escapeHtml(athlete.externalIds?.[0] ? `DSV ${athlete.externalIds[0]}` : "ohne DSV-ID")}</small></button>`).join("") || `<p>Keine Athleten gefunden.</p>`;
  dom.list.querySelectorAll("[data-athlete]").forEach((button) => button.addEventListener("click", () => selectAthlete(button.dataset.athlete)));
  dom.athleteSelect.innerHTML = state.athletes.map((athlete) => `<option value="${athlete.id}">${escapeHtml(athlete.displayName)} · ${escapeHtml(athlete.birthYear || "–")}</option>`).join("");
  dom.athleteSelect.value = state.selectedId || "";
}

function chart(history) {
  if (!history.length) return `<div class="chart-empty">Für diese Saison ist noch kein Ranglistenstand vorhanden.</div>`;
  const width = 780, height = 220, left = 48, right = 24, top = 26, bottom = 38;
  const values = history.map((item) => Number(item.listPoints));
  const minimum = Math.min(...values), maximum = Math.max(...values), padding = Math.max((maximum - minimum) * .2, 5);
  const low = minimum - padding, high = maximum + padding;
  const x = (index) => history.length === 1 ? width / 2 : left + index * ((width - left - right) / (history.length - 1));
  const y = (value) => top + (high - value) / (high - low) * (height - top - bottom);
  const points = history.map((item,index) => `${x(index)},${y(Number(item.listPoints))}`).join(" ");
  const grid = [0,.5,1].map((part) => { const value = high - (high-low)*part; const yy = y(value); return `<line class="chart-grid" x1="${left}" y1="${yy}" x2="${width-right}" y2="${yy}"/><text class="chart-label" x="4" y="${yy+4}">${decimal(value)}</text>`; }).join("");
  const dots = history.map((item,index) => `<circle class="chart-dot" cx="${x(index)}" cy="${y(Number(item.listPoints))}" r="5"/><text class="chart-value" text-anchor="middle" x="${x(index)}" y="${y(Number(item.listPoints))-12}">${decimal(item.listPoints)}</text><text class="chart-label" text-anchor="middle" x="${x(index)}" y="${height-8}">${date(item.publishedAt).slice(0,5)}</text>`).join("");
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Verlauf der DSV-Listenpunkte">${grid}<polyline class="chart-line" points="${points}"/>${dots}</svg>`;
}

function selectedSeason() { return state.analytics?.seasons.find((item) => item.seasonId === state.seasonId); }

function renderProfile() {
  const payload = state.analytics, season = selectedSeason();
  if (!payload || !season) {
    dom.profile.hidden = true; dom.empty.hidden = false;
    dom.empty.innerHTML = payload ? `<strong>Noch keine Saisondaten</strong><p>Für ${escapeHtml(payload.athlete.displayName)} sind noch keine freigegebenen Ergebnisse oder DSV-Snapshots vorhanden.</p>` : `<strong>Athlet auswählen</strong><p>Wähle eine Person aus, um Ergebnisse und Entwicklung zu sehen.</p>`;
    return;
  }
  dom.profile.hidden = false; dom.empty.hidden = true;
  dom.name.textContent = payload.athlete.displayName; dom.meta.textContent = `Jahrgang ${payload.athlete.birthYear || "–"} · ${payload.athlete.club || "Verein unbekannt"}`;
  dom.id.textContent = payload.athlete.externalIds?.length ? `DSV-ID ${payload.athlete.externalIds.join(", ")}` : "Noch keine DSV-ID hinterlegt";
  dom.season.innerHTML = payload.seasons.map((item) => `<option value="${item.seasonId}">${item.seasonId.replace("-","/")}</option>`).join(""); dom.season.value = state.seasonId;
  const ranking = season.latestRanking, count = season.latestPublishedRaceCount;
  dom.points.textContent = decimal(ranking?.listPoints); dom.pointsDate.textContent = ranking ? `Stand ${date(ranking.publishedAt)}` : "Kein Ranglistenstand";
  dom.rank.textContent = ranking?.overallRank ? `#${ranking.overallRank}` : "–";
  dom.races.textContent = count?.raceCount ?? "–"; dom.racesDate.textContent = count ? `Stand ${date(count.observedAt)}` : "Keine offizielle Angabe";
  dom.resultsMetric.textContent = season.recordedResults.length; dom.starts.textContent = `${season.recordedRaceStarts} Starts in der Datenbasis`;
  dom.chart.innerHTML = chart(season.rankingHistory);
  dom.change.className = "change";
  if (season.listPointsChange === null) dom.change.textContent = "Noch kein Vergleich";
  else { const improved = season.listPointsChange < 0; dom.change.classList.add(improved ? "better" : season.listPointsChange > 0 ? "worse" : ""); dom.change.textContent = `${season.listPointsChange > 0 ? "+" : ""}${decimal(season.listPointsChange)} Punkte`; }
  const fields = [["Gesamtrang",ranking?.overallRank],["Altersklasse",ranking?.ageClassRank],["Jahrgang",ranking?.birthYearRank],["Basiswert",ranking ? decimal(ranking.basePoints) : null]];
  dom.ranking.innerHTML = fields.map(([label,value]) => `<div><dt>${label}</dt><dd>${value ?? "–"}</dd></div>`).join("");
  dom.raceCount.innerHTML = count ? `<div class="count-card"><span>Veröffentlichter Stand ${date(count.observedAt)}</span><strong>${count.raceCount} Rennen</strong><small>${escapeHtml(count.coverage?.note || "Vollständiger Saisonstand")}</small></div>` : `<div class="chart-empty">Für diese Saison liegt keine veröffentlichte Rennanzahl vor.</div>`;
  dom.resultCount.textContent = `${season.recordedResults.length} Ergebnis${season.recordedResults.length === 1 ? "" : "se"}`;
  dom.results.innerHTML = season.recordedResults.length ? season.recordedResults.map((item) => `<article class="result-row"><span class="result-date">${date(item.race.date)}</span><div class="result-race"><strong>${escapeHtml(item.race.name)}</strong><small>${escapeHtml(item.group.label)} · ${escapeHtml(item.race.discipline || "–")}</small></div><div class="result-value"><small>Platz</small><strong>${item.rank ?? "–"}</strong></div><div class="result-value"><small>Rennpunkte</small><strong>${decimal(item.federationPoints)}</strong></div><div class="result-value"><small>Zeit</small><strong>${seconds(item.officialTimeSeconds)}</strong></div><span class="result-status ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></article>`).join("") : `<div class="chart-empty">Für diese Saison sind noch keine Rennergebnisse importiert.</div>`;
}

async function selectAthlete(id) {
  state.selectedId = id; renderAthletes(); dom.profile.hidden = true; dom.empty.hidden = false; dom.empty.innerHTML = "<strong>Daten werden geladen</strong><p>Ergebnisse und Ranglistenstände werden zusammengeführt.</p>";
  try { state.analytics = await request(`/api/v1/athletes/${encodeURIComponent(id)}/analytics`); state.seasonId = state.analytics.seasons[0]?.seasonId || null; renderProfile(); }
  catch (error) { dom.notice.textContent = error.message; dom.notice.hidden = false; }
}

async function initialize() {
  try {
    const identity = await request("/api/v1/auth/me"); state.user = identity.user;
    const payload = await request("/api/v1/athletes?targetClub=true");
    const now = new Date(), seasonStart = now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1;
    state.athletes = payload.items.filter((athlete) => Number(athlete.birthYear) >= seasonStart - 16 && Number(athlete.birthYear) <= seasonStart - 12);
    renderAthletes(); if (state.athletes.length) await selectAthlete(state.athletes[0].id);
  } catch (error) { dom.notice.textContent = error.message; dom.notice.hidden = false; }
}

dom.search.addEventListener("input", renderAthletes);
dom.athleteSelect.addEventListener("change", () => selectAthlete(dom.athleteSelect.value));
dom.season.addEventListener("change", () => { state.seasonId = dom.season.value; renderProfile(); });
dom.logout.addEventListener("click", async () => { try { await request("/api/v1/auth/logout", { method:"POST" }); } finally { window.location.replace("/login/"); } });
initialize();
