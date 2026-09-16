const dom = {
  accountName: document.querySelector("#account-name"),
  logoutButton: document.querySelector("#logout-button"),
  intro: document.querySelector("#page-intro"),
  starterCount: document.querySelector("#starter-count"),
  clubCount: document.querySelector("#club-count"),
  navigation: document.querySelector("#list-navigation"),
  container: document.querySelector("#start-list-container"),
};

let authUser;

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function slug(value, index) {
  const normalized = String(value).normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "").toLowerCase();
  return `startliste-${normalized || index + 1}`;
}

function eventDate(value) {
  if (!value) return "Datum offen";
  return new Date(`${value}T12:00:00`).toLocaleDateString("de-DE", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });
}

async function initialize() {
  try {
    const authResponse = await fetch("/api/v1/auth/me");
    if (!authResponse.ok) {
      window.location.replace("/login/?next=/tippspiel/startlisten.html");
      return;
    }
    const auth = await authResponse.json();
    authUser = auth.user;
    dom.accountName.textContent = authUser.displayName;
    dom.logoutButton.hidden = auth.authentication !== "required";

    const roundResponse = await fetch("/api/v1/predictor/rounds/current");
    if (!roundResponse.ok) throw new Error("Die aktuelle Tipprunde konnte nicht geladen werden.");
    const round = await roundResponse.json();
    const response = await fetch(`/api/v1/predictor/rounds/${encodeURIComponent(round.id)}/start-list`);
    if (!response.ok) throw new Error("Die Startlisten konnten nicht geladen werden.");
    const payload = await response.json();
    dom.intro.textContent = `${round.title} · alle gemeldeten Personen`;
    dom.starterCount.textContent = `${payload.totalStarters} Starter`;
    dom.clubCount.textContent = `${payload.targetClubStarters} OHA`;

    if (!payload.items.length) {
      dom.container.innerHTML = '<p class="empty-state">Für diese Tipprunde sind noch keine aufbereiteten Startlisten vorhanden.</p>';
      return;
    }
    const ids = payload.items.map((item, index) => slug(item.sourceFile, index));
    dom.navigation.innerHTML = payload.items.map((item, index) => `<a href="#${ids[index]}">${escapeHtml(item.sourceFile)}</a>`).join("");
    dom.container.innerHTML = payload.items.map((item, index) => {
      const groups = item.groups.map((group) => `<section class="starter-group"><header><div><span class="kicker">${escapeHtml(group.ageClass ?? "Altersklasse")}</span><h3>${escapeHtml(group.label ?? group.ageClass)}</h3></div><span>${group.starters.length} Starter</span></header><div class="starter-table" role="table" aria-label="${escapeHtml(group.label)}"><div class="starter-row starter-table-head" role="row"><span>Stnr.</span><span>Name</span><span>Verein</span><span>Jahrgang</span></div>${group.starters.map((starter) => `<div class="starter-row${starter.targetClub ? " target-club-starter" : ""}" role="row"><span class="start-number">${escapeHtml(starter.startNumber ?? "–")}</span><strong>${escapeHtml(starter.displayName)}${starter.targetClub ? ' <span class="club-marker">OHA</span>' : ""}</strong><span>${escapeHtml(starter.club ?? "–")}</span><span>${escapeHtml(starter.birthYear ?? "–")}</span></div>`).join("")}</div></section>`).join("");
      return `<article class="start-list-card" id="${ids[index]}" data-source="${escapeHtml(item.sourceFile)}"><header class="start-list-head"><div><span class="kicker">${escapeHtml(eventDate(item.event.date))} · ${escapeHtml(item.event.discipline ?? "Disziplin offen")}</span><h2>${escapeHtml(item.event.name ?? item.sourceFile)}</h2><p>${escapeHtml(item.event.location ?? "Ort offen")} · ${escapeHtml(item.sourceFile)}</p></div><div><strong>${item.total}</strong><span>Starter</span><small>${item.targetClubTotal} OHA</small></div></header>${groups}</article>`;
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
