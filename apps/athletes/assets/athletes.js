const state = { athletes: [], selectedId: null, analytics: null, seasonId: null };
const dom = {
  list: document.querySelector("#athlete-list"), search: document.querySelector("#athlete-search"), athleteSelect: document.querySelector("#athlete-select"),
  profile: document.querySelector("#profile"), empty: document.querySelector("#empty-profile"), notice: document.querySelector("#notice"),
  name: document.querySelector("#profile-name"), meta: document.querySelector("#profile-meta"), id: document.querySelector("#profile-id"), season: document.querySelector("#season-select"),
  basePoints: document.querySelector("#metric-base-points"), baseNote: document.querySelector("#metric-base-note"), overallPoints: document.querySelector("#metric-overall-points"), slPoints: document.querySelector("#metric-sl-points"), gsPoints: document.querySelector("#metric-gs-points"), pointsFormula: document.querySelector("#metric-points-formula"), formulaContext: document.querySelector("#formula-context"), formulaCandidates: document.querySelector("#formula-candidates"), ageRank: document.querySelector("#metric-age-rank"), ageRankLabel: document.querySelector("#metric-age-rank-label"), birthRank: document.querySelector("#metric-birth-rank"), birthRankLabel: document.querySelector("#metric-birth-rank-label"),
  races: document.querySelector("#metric-races"), racesDate: document.querySelector("#metric-races-date"), resultsMetric: document.querySelector("#metric-results"), starts: document.querySelector("#metric-starts"),
  chart: document.querySelector("#points-chart"), change: document.querySelector("#points-change"), ranking: document.querySelector("#ranking-details"), raceCount: document.querySelector("#race-count-details"),
  results: document.querySelector("#results"), resultCount: document.querySelector("#result-count-label"), summary: document.querySelector("#season-summary"),
};

function escapeHtml(value) { const node = document.createElement("div"); node.textContent = String(value ?? ""); return node.innerHTML; }
function decimal(value) { return Number.isFinite(Number(value)) ? Number(value).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "–"; }
function date(value) { if (!value) return "Kein Stichtag"; return new Intl.DateTimeFormat("de-DE", { day:"2-digit", month:"2-digit", year:"numeric" }).format(new Date(value)); }
function seconds(value) { if (!Number.isFinite(Number(value))) return "–"; const minutes = Math.floor(value / 60); return `${minutes}:${(value % 60).toFixed(2).padStart(5,"0")}`; }
function ageClass(seasonId, birthYear) { const endYear = Number(String(seasonId || "").split("-")[1]), age = endYear - Number(birthYear); return [13,14].includes(age) ? "U14" : [15,16].includes(age) ? "U16" : null; }
function signedDecimal(value) { return (Number(value) >= 0 ? "+" : "") + decimal(value); }
function expandedFormula(formula, points) {
  return String(formula || "")
    .replaceAll("SLbest", decimal(points.bestSlalomResult))
    .replaceAll("RSbest", decimal(points.bestGiantSlalomResult))
    .replaceAll("BAS", decimal(points.basePoints));
}
function formulaCards(points) {
  if (!points?.formulaCandidates?.length) return '<div class="chart-empty">Noch keine Formel berechenbar.</div>';
  return points.formulaCandidates.map((candidate) =>
    '<article class="' + (candidate.selected ? 'selected' : '') + '">' +
      '<span>' + (candidate.selected ? 'Gewertet' : 'Alternative') + '</span>' +
      '<code>' + escapeHtml(candidate.formula) + '</code>' +
      '<small>' + escapeHtml(expandedFormula(candidate.formula, points)) + '</small>' +
      '<strong>' + decimal(candidate.value) + '</strong>' +
    '</article>'
  ).join("");
}

async function request(url, options = {}) {
  const response = await fetch(url, options); let body = {};
  try { body = await response.json(); } catch { body = {}; }
  if (!response.ok) throw new Error(body.error?.message || `Fehler ${response.status}`);
  return body;
}

function filteredAthletes() {
  const query = dom.search.value.trim().toLocaleLowerCase("de");
  return state.athletes.filter((athlete) => !query || `${athlete.displayName} ${athlete.birthYear}`.toLocaleLowerCase("de").includes(query));
}

function renderAthletes() {
  const athletes = filteredAthletes();
  dom.list.innerHTML = athletes.map((athlete) => `<button class="athlete-button${athlete.id === state.selectedId ? " active" : ""}" data-athlete="${athlete.id}" type="button"><strong>${escapeHtml(athlete.displayName)}</strong><small>Jahrgang ${escapeHtml(athlete.birthYear || "–")} · ${escapeHtml(athlete.externalIds?.[0] ? `DSV ${athlete.externalIds[0]}` : "ohne DSV-ID")}</small></button>`).join("") || `<p>Keine Athleten gefunden.</p>`;
  dom.list.querySelectorAll("[data-athlete]").forEach((button) => button.addEventListener("click", () => selectAthlete(button.dataset.athlete)));
  dom.athleteSelect.innerHTML = state.athletes.map((athlete) => `<option value="${athlete.id}">${escapeHtml(athlete.displayName)} · ${escapeHtml(athlete.birthYear || "–")}</option>`).join("");
  dom.athleteSelect.value = state.selectedId || "";
}

function chart(history) {
  if (!history.length) return `<div class="chart-empty">Für diese Saison ist noch kein punktewirksames Rennergebnis vorhanden.</div>`;
  const width = 780, height = 220, left = 48, right = 24, top = 26, bottom = 38;
  const values = history.map((item) => Number(item.overallPoints));
  const minimum = Math.min(...values), maximum = Math.max(...values), padding = Math.max((maximum - minimum) * .2, 5);
  const low = minimum - padding, high = maximum + padding;
  const x = (index) => history.length === 1 ? width / 2 : left + index * ((width - left - right) / (history.length - 1));
  const y = (value) => top + (high - value) / (high - low) * (height - top - bottom);
  const points = history.map((item,index) => `${x(index)},${y(Number(item.overallPoints))}`).join(" ");
  const grid = [0,.5,1].map((part) => { const value = high - (high-low)*part; const yy = y(value); return `<line class="chart-grid" x1="${left}" y1="${yy}" x2="${width-right}" y2="${yy}"/><text class="chart-label" x="4" y="${yy+4}">${decimal(value)}</text>`; }).join("");
  const dots = history.map((item,index) => `<circle class="chart-dot" cx="${x(index)}" cy="${y(Number(item.overallPoints))}" r="5"/><text class="chart-value" text-anchor="middle" x="${x(index)}" y="${y(Number(item.overallPoints))-12}">${decimal(item.overallPoints)}</text><text class="chart-label" text-anchor="middle" x="${x(index)}" y="${height-8}">${date(item.date).slice(0,5)}</text>`).join("");
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Verlauf der DSV-Listenpunkte">${grid}<polyline class="chart-line" points="${points}"/>${dots}</svg>`;
}

function selectedSeason() { return state.analytics?.seasons.find((item) => item.seasonId === state.seasonId); }

function preferredSeasonId(seasons, requestedSeasonId) {
  if (requestedSeasonId && seasons.some((season) => season.seasonId === requestedSeasonId)) return requestedSeasonId;
  const seasonWithPointHistory = seasons.find((season) => season.disciplinePoints?.history?.some((item) => item.pointKind !== "SEASON_START"));
  const seasonWithResults = seasons.find((season) => season.recordedResults?.length);
  return seasonWithPointHistory?.seasonId || seasonWithResults?.seasonId || seasons[0]?.seasonId || null;
}

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
  const ranking = season.latestRanking, count = season.raceCountOverview || season.latestPublishedRaceCount, points = season.disciplinePoints;
  dom.basePoints.textContent = decimal(points?.basePoints); dom.overallPoints.textContent = decimal(points?.overallPoints); dom.slPoints.textContent = decimal(points?.slalomPoints); dom.gsPoints.textContent = decimal(points?.giantSlalomPoints); dom.pointsFormula.textContent = points?.overallFormula || "Noch keine Berechnung";
  dom.baseNote.textContent = points?.previousEndListPoints != null && points?.seasonCorrectionPoints != null
    ? decimal(points.previousEndListPoints) + " " + signedDecimal(points.seasonCorrectionPoints) + " Korrektur"
    : points?.baseSource === "MAXIMUM_NEW_ATHLETE" ? "Neueinsteiger laut Reglement" : "Startwert der Saison";
  dom.formulaContext.textContent = "BAS " + decimal(points?.basePoints) + " · SLbest " + decimal(points?.bestSlalomResult) + " · RSbest " + decimal(points?.bestGiantSlalomResult);
  dom.formulaCandidates.innerHTML = formulaCards(points);
  dom.ageRank.textContent = ranking?.ageClassRank ? `#${ranking.ageClassRank}` : "–";
  dom.birthRank.textContent = ranking?.birthYearRank ? `#${ranking.birthYearRank}` : "–";
  dom.ageRankLabel.textContent = ageClass(season.seasonId, payload.athlete.birthYear) ? `${ageClass(season.seasonId, payload.athlete.birthYear)} · Deutschland` : "Deutschland";
  dom.birthRankLabel.textContent = payload.athlete.birthYear ? `Jahrgang ${payload.athlete.birthYear} · Deutschland` : "Deutschland";
  dom.races.textContent = count?.raceCount ?? "–"; dom.racesDate.textContent = count?.source === "DSV_OFFICIAL" ? `Offizieller Stand ${date(count.observedAt)}` : count ? "Aus importierten Ergebnissen" : "Keine Angabe";
  dom.resultsMetric.textContent = season.recordedResults.length; dom.starts.textContent = `${season.recordedRaceStarts} Starts in der Datenbasis`;
  dom.chart.innerHTML = chart(points?.history || []);
  dom.change.className = "change";
  const raceHistory = points?.history?.filter((item) => item.pointKind !== "SEASON_START") || [];
  if (!points?.history?.length) dom.change.textContent = "Noch kein Startwert";
  else if (!raceHistory.length) dom.change.textContent = "Startwert";
  else { const change = points.overallPoints - points.basePoints; const improved = change < 0; dom.change.classList.add(improved ? "better" : change > 0 ? "worse" : ""); dom.change.textContent = `${change > 0 ? "+" : ""}${decimal(change)} Punkte`; }
  const fields = [["Gesamtrang",ranking?.overallRank],["Altersklasse",ranking?.ageClassRank],["Jahrgang",ranking?.birthYearRank],["Saison-Startwert",points ? decimal(points.basePoints) : null]];
  dom.ranking.innerHTML = fields.map(([label,value]) => `<div><dt>${label}</dt><dd>${value ?? "–"}</dd></div>`).join("");
  dom.raceCount.innerHTML = count ? `<div class="count-card"><span>${count.source === "DSV_OFFICIAL" ? `Offizieller DSV-Stand ${date(count.observedAt)}` : `Aus ${season.recordedResults.length} importierten Ergebnissen gezählt`}</span><strong>${count.raceCount} Rennen</strong><small>${count.source === "DSV_OFFICIAL" ? escapeHtml(count.coverage?.note || "Offizielle DSV-Angabe") : escapeHtml(count.officialMinimumIncludedRaces ? `Die offizielle DSV-Liste führt ${count.ageClass}-Athleten erst ab ${count.officialMinimumIncludedRaces} Rennen. Darunter wird die Anzahl aus den vorhandenen Ergebnislisten berechnet.` : "Für diesen Athleten liegt kein Eintrag in der offiziellen DSV-Rennanzahlliste vor.")}</small></div>` : `<div class="chart-empty">Für diese Saison liegt keine Rennanzahl vor.</div>`;
  const summary = season.resultSummary || {};
  const summaryFields = [["Starts",summary.starts ?? 0],["Gewertet",summary.classified ?? 0],["Podestplätze",summary.podiums ?? 0],["Bestes Ergebnis",summary.bestRank ? `Platz ${summary.bestRank}` : "–"],["DNF",summary.dnf ?? 0],["DSQ",summary.dsq ?? 0],["DNS",summary.dns ?? 0]];
  dom.summary.innerHTML = summaryFields.map(([label,value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join("");
  dom.resultCount.textContent = `${season.recordedResults.length} Ergebnis${season.recordedResults.length === 1 ? "" : "se"}`;
  dom.results.innerHTML = season.recordedResults.length ? season.recordedResults.map((item) => `<article class="result-row"><span class="result-date">${date(item.race.date)}</span><div class="result-race"><strong>${escapeHtml(item.race.name)}</strong><small>${escapeHtml(item.group.label)} · ${escapeHtml(item.race.discipline || "–")}${item.appliedPenaltyPoints != null ? ` · ${decimal(item.rawRacePoints)} + ${decimal(item.appliedPenaltyPoints)} Zuschlag` : ""}</small></div><div class="result-value"><small>Platz</small><strong>${item.rank ?? "–"}</strong></div><div class="result-value"><small>DSV-Punkte</small><strong>${decimal(item.federationPoints)}</strong></div><div class="result-value"><small>Zeit</small><strong>${seconds(item.officialTimeSeconds)}</strong></div><span class="result-status ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></article>`).join("") : `<div class="chart-empty">Für diese Saison sind noch keine Rennergebnisse importiert.</div>`;
}

async function selectAthlete(id) {
  state.selectedId = id; renderAthletes(); dom.profile.hidden = true; dom.empty.hidden = false; dom.empty.innerHTML = "<strong>Daten werden geladen</strong><p>Ergebnisse und Ranglistenstände werden zusammengeführt.</p>";
  try {
    state.analytics = await request(`/api/v1/athletes/${encodeURIComponent(id)}/analytics`);
    state.seasonId = preferredSeasonId(state.analytics.seasons, state.seasonId);
    renderProfile();
  }
  catch (error) { dom.notice.textContent = error.message; dom.notice.hidden = false; }
}

async function initialize() {
  try {
    const payload = await request("/api/v1/athletes?targetClub=true");
    const now = new Date(), seasonStart = now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1;
    state.athletes = payload.items.filter((athlete) => Number(athlete.birthYear) >= seasonStart - 16 && Number(athlete.birthYear) <= seasonStart - 12);
    const requestedId = new URLSearchParams(window.location.search).get("athlete");
    const initial = state.athletes.find((athlete) => athlete.id === requestedId) || state.athletes[0];
    renderAthletes(); if (initial) await selectAthlete(initial.id);
  } catch (error) { dom.notice.textContent = error.message; dom.notice.hidden = false; }
}

dom.search.addEventListener("input", renderAthletes);
dom.athleteSelect.addEventListener("change", () => selectAthlete(dom.athleteSelect.value));
dom.season.addEventListener("change", () => { state.seasonId = dom.season.value; renderProfile(); });
initialize();
