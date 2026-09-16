const dom = {
  accountName: document.querySelector("#account-name"),
  logoutButton: document.querySelector("#logout-button"),
  intro: document.querySelector("#page-intro"),
  resultCount: document.querySelector("#result-count"),
  clubCount: document.querySelector("#club-count"),
  navigation: document.querySelector("#list-navigation"),
  container: document.querySelector("#result-list-container"),
};

let authUser;

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function slug(value, index) {
  const normalized = String(value).normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "").toLowerCase();
  return `ergebnis-${normalized || index + 1}`;
}

function eventDate(value) {
  if (!value) return "Datum offen";
  return new Date(`${value}T12:00:00`).toLocaleDateString("de-DE", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });
}

function formatTime(seconds) {
  if (seconds === null || seconds === undefined) return "–";
  const minutes = Math.floor(Number(seconds) / 60);
  const remainder = (Number(seconds) % 60).toFixed(2).padStart(5, "0");
  return minutes ? `${minutes}:${remainder}` : `${remainder} s`;
}

function resultValue(entry) {
  if (entry.status !== "CLASSIFIED") return entry.status ?? "–";
  const gap = entry.gapSeconds > 0 ? ` · +${formatTime(entry.gapSeconds)}` : "";
  return `${formatTime(entry.officialTimeSeconds)}${gap}`;
}

function runSummary(entry) {
  const runs = (entry.runResults ?? []).map((run) => `Lauf ${run.runNumber}: ${run.status === "CLASSIFIED" ? formatTime(run.timeSeconds) : run.status}`).join(" · ");
  const percentage = entry.percentageGap > 0 ? `Rückstand ${Number(entry.percentageGap).toFixed(2).replace(".", ",")} %` : "";
  const points = entry.federationPoints !== null && entry.federationPoints !== undefined ? `${Number(entry.federationPoints).toFixed(2).replace(".", ",")} Punkte` : "";
  return [runs, percentage, points].filter(Boolean).join(" · ");
}

async function initialize() {
  try {
    const authResponse = await fetch("/api/v1/auth/me");
    if (!authResponse.ok) {
      window.location.replace("/login/?next=/tippspiel/ergebnisse.html");
      return;
    }
    const auth = await authResponse.json();
    authUser = auth.user;
    dom.accountName.textContent = authUser.displayName;
    dom.logoutButton.hidden = auth.authentication !== "required";

    const roundResponse = await fetch("/api/v1/predictor/rounds/current");
    if (!roundResponse.ok) throw new Error("Die aktuelle Tipprunde konnte nicht geladen werden.");
    const round = await roundResponse.json();
    const response = await fetch(`/api/v1/predictor/rounds/${encodeURIComponent(round.id)}/result-list`);
    if (!response.ok) throw new Error("Die Ergebnislisten konnten nicht geladen werden.");
    const payload = await response.json();
    dom.intro.textContent = `${round.title} · offizielle Gesamtergebnisse`;
    dom.resultCount.textContent = `${payload.totalEntries} Ergebnisse`;
    dom.clubCount.textContent = `${payload.targetClubEntries} OHA`;

    if (!payload.items.length) {
      dom.container.innerHTML = '<p class="empty-state">Für diese Tipprunde sind noch keine aufbereiteten Ergebnislisten vorhanden.</p>';
      return;
    }
    const ids = payload.items.map((item, index) => slug(item.sourceFile, index));
    dom.navigation.innerHTML = payload.items.map((item, index) => `<a href="#${ids[index]}">${escapeHtml(item.sourceFile)}</a>`).join("");
    dom.container.innerHTML = payload.items.map((item, index) => {
      const groups = item.groups.map((group) => `<section class="starter-group result-group"><header><div><span class="kicker">${escapeHtml(group.ageClass ?? "Altersklasse")}</span><h3>${escapeHtml(group.label ?? group.ageClass)}</h3></div><span>${group.entries.length} Ergebnisse</span></header><div class="result-table" role="table" aria-label="${escapeHtml(group.label)}"><div class="result-row result-table-head" role="row"><span>Rang</span><span>Name</span><span>Verein</span><span>Ergebnis</span></div>${group.entries.map((entry) => `<div class="result-row${entry.targetClub ? " target-club-starter" : ""}${entry.status !== "CLASSIFIED" ? " is-unclassified" : ""}" role="row"><span class="result-rank">${escapeHtml(entry.rank ?? entry.status ?? "–")}</span><div class="result-person"><strong>${escapeHtml(entry.displayName)}${entry.targetClub ? ' <span class="club-marker">OHA</span>' : ""}</strong><small>Stnr. ${escapeHtml(entry.startNumber ?? "–")} · Jg. ${escapeHtml(entry.birthYear ?? "–")}${entry.federation ? ` · ${escapeHtml(entry.federation)}` : ""}</small></div><span class="result-club">${escapeHtml(entry.club ?? "–")}</span><div class="result-time"><strong>${escapeHtml(resultValue(entry))}</strong><small>${escapeHtml(runSummary(entry))}</small></div></div>`).join("")}</div></section>`).join("");
      return `<article class="start-list-card" id="${ids[index]}" data-source="${escapeHtml(item.sourceFile)}"><header class="start-list-head"><div><span class="kicker">${escapeHtml(eventDate(item.event.date))} · ${escapeHtml(item.event.discipline ?? "Disziplin offen")}</span><h2>${escapeHtml(item.event.name ?? item.sourceFile)}</h2><p>${escapeHtml(item.event.location ?? "Ort offen")} · ${escapeHtml(item.sourceFile)}</p></div><div><strong>${item.total}</strong><span>Ergebnisse</span><small>${item.targetClubTotal} OHA</small></div></header>${groups}</article>`;
    }).join("");

    const requested = new URLSearchParams(window.location.search).get("liste");
    if (requested) {
      const match = Array.from(document.querySelectorAll(".start-list-card")).find((element) => element.dataset.source === requested);
      if (match) window.setTimeout(() => match.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    }
  } catch (error) {
    dom.container.innerHTML = `<p class="empty-state error-state">${escapeHtml(error.message)}</p>`;
  }
}

dom.logoutButton.addEventListener("click", async () => {
  await fetch("/api/v1/auth/logout", { method: "POST", headers: { "X-CSRF-Token": authUser.csrfToken } });
  window.location.replace("/login/");
});

initialize();
