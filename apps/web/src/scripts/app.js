const DATA_URLS = ["/api/v1/predictor/rounds/current", "src/data/tip-round.local.json", "src/data/tip-round.json"];
const EVALUATION_URL = "src/data/evaluation.local.json";
const STORAGE_PREFIX = "ski-predictor:submission:";

let leaders = [];

const dom = {
  form: document.querySelector("#prediction-form"),
  questionList: document.querySelector("#question-list"),
  title: document.querySelector("#tip-round-title"),
  subtitle: document.querySelector("#tip-round-subtitle"),
  progress: document.querySelector("#question-progress"),
  message: document.querySelector("#form-message"),
  saveButton: document.querySelector("#save-prediction"),
  resetButton: document.querySelector("#reset-prediction"),
  exportButton: document.querySelector("#export-prediction"),
  playerName: document.querySelector("#player-name"),
  toast: document.querySelector("#toast"),
  deadlineStatus: document.querySelector("#deadline-status"),
  raceList: document.querySelector("#race-list"),
  overviewRaceCount: document.querySelector("#overview-race-count"),
  overviewListCount: document.querySelector("#overview-list-count"),
  overviewAthleteCount: document.querySelector("#overview-athlete-count"),
  overviewRaces: document.querySelector("#overview-races"),
  overviewStartLists: document.querySelector("#overview-start-lists"),
  overviewAthletes: document.querySelector("#overview-athletes"),
  evaluationSection: document.querySelector("#auswertung"),
  evaluationStatus: document.querySelector("#evaluation-status"),
  evaluationBadge: document.querySelector("#evaluation-badge"),
  evaluationWeekendPoints: document.querySelector("#evaluation-weekend-points"),
  evaluationRawPoints: document.querySelector("#evaluation-raw-points"),
  evaluationQuestionList: document.querySelector("#evaluation-question-list"),
  heroSeries: document.querySelector("#hero-series"),
  heroTitle: document.querySelector("#hero-title"),
  heroDate: document.querySelector("#hero-date"),
  seasonLabel: document.querySelector("#season-label"),
};

let tipRound;
let athletesById;
let countdownTimer;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function athleteOptions(athleteIds, selected = "") {
  return `<option value="">Bitte auswählen</option>${athleteIds.filter((id) => athletesById.has(id)).map((id) => {
    const athlete = athletesById.get(id);
    return `<option value="${escapeHtml(id)}" ${selected === id ? "selected" : ""}>${escapeHtml(athlete.displayName)} · ${escapeHtml(athlete.ageClass)}</option>`;
  }).join("")}`;
}

function questionTypeLabel(type) {
  return {
    NUMBER: "Anzahl",
    ATHLETE: "Person",
    INTERNAL_RANKING: "Reihenfolge",
    HEAD_TO_HEAD: "Direktvergleich",
    PLACEMENT: "Platzierung",
    PODIUM: "Podium",
  }[type] ?? type;
}

function renderQuestion(question, index) {
  const questionId = escapeHtml(question.id);
  let control = "";

  if (question.type === "NUMBER" || question.type === "PLACEMENT") {
    control = `<label class="single-input"><span>${question.type === "PLACEMENT" ? "Platzierung" : "Dein Tipp"}</span><input type="number" name="answer-${questionId}" data-question-id="${questionId}" min="${question.minimum}" max="${question.maximum}" inputmode="numeric" placeholder="${question.minimum} bis ${question.maximum}" /></label>`;
  }

  if (question.type === "ATHLETE") {
    control = `<label class="single-input"><span>Person auswählen</span><select name="answer-${questionId}" data-question-id="${questionId}">${athleteOptions(question.athleteIds)}</select></label>`;
  }

  if (question.type === "HEAD_TO_HEAD") {
    control = `<div class="choice-grid">${question.athleteIds.map((athleteId) => {
      const athlete = athletesById.get(athleteId);
      return `<label class="choice-option"><input type="radio" name="answer-${questionId}" data-question-id="${questionId}" value="${escapeHtml(athleteId)}" /><span>${escapeHtml(athlete.displayName)}<small>${escapeHtml(athlete.ageClass)}</small></span></label>`;
    }).join("")}</div>`;
  }

  if (question.type === "INTERNAL_RANKING" || question.type === "PODIUM") {
    control = `<div class="ranking-grid">${Array.from({ length: question.positions }, (_, position) => `<label><span>${position + 1}. Platz</span><select name="answer-${questionId}-${position}" data-question-id="${questionId}" data-position="${position}">${athleteOptions(question.athleteIds)}</select></label>`).join("")}</div>`;
  }

  return `<fieldset class="question-card" data-question-card="${questionId}">
    <legend class="visually-hidden">Frage ${index + 1}</legend>
    <div class="question-head"><span class="question-number">${String(index + 1).padStart(2, "0")}</span><div><div class="question-meta"><span class="question-type">${questionTypeLabel(question.type)} · 100 Punkte</span><span class="question-scope">Rennen: ${escapeHtml(question.raceLabel ?? "gesamtes Wochenende")}</span></div><h3>${escapeHtml(question.prompt)}</h3><p>${escapeHtml(question.hint)}</p></div></div>
    <div class="answer-control">${control}</div>
    <p class="question-error" data-question-error="${questionId}"></p>
  </fieldset>`;
}

function renderWeekendOverview() {
  const groups = tipRound.groups ?? [];
  const racesById = new Map(tipRound.races.map((race) => [race.id, race]));
  const groupsById = new Map(groups.map((group) => [group.id, group]));
  const startLists = new Map();

  tipRound.races.forEach((race) => {
    const source = race.sourceFile ?? `Startliste ${race.name}`;
    const current = startLists.get(source) ?? [];
    current.push(race);
    startLists.set(source, current);
  });

  dom.overviewRaceCount.textContent = String(tipRound.races.length);
  dom.overviewListCount.textContent = String(startLists.size);
  dom.overviewAthleteCount.textContent = String(tipRound.athletes.length);

  dom.overviewRaces.innerHTML = tipRound.races.map((race) => {
    const raceGroups = groups.filter((group) => group.raceId === race.id);
    const groupSummary = raceGroups.length
      ? raceGroups.map((group) => `${group.label} (${group.athleteIds.length} OHA)`).join(" · ")
      : "Wertungsgruppen werden aus der Startliste übernommen";
    return `<div class="overview-entry"><strong>${escapeHtml(race.name)}</strong><span>${escapeHtml(race.day)} · ${escapeHtml(race.discipline)}</span><small>${escapeHtml(groupSummary)}</small></div>`;
  }).join("");

  dom.overviewStartLists.innerHTML = Array.from(startLists.entries()).map(([source, races]) => `<div class="overview-entry"><strong>${escapeHtml(source)}</strong><span>${races.length} ${races.length === 1 ? "Bewerb" : "Bewerbe"}</span><small>${races.map((race) => escapeHtml(race.name)).join(" · ")}</small></div>`).join("");

  const athletesByAgeClass = new Map();
  tipRound.athletes.forEach((athlete) => {
    const current = athletesByAgeClass.get(athlete.ageClass) ?? [];
    current.push(athlete);
    athletesByAgeClass.set(athlete.ageClass, current);
  });
  const sortedAgeClasses = Array.from(athletesByAgeClass.keys()).sort((left, right) => Number(left.match(/\d+/)?.[0] ?? 99) - Number(right.match(/\d+/)?.[0] ?? 99));
  dom.overviewAthletes.innerHTML = sortedAgeClasses.map((ageClass) => `<div class="athlete-group"><h4>${escapeHtml(ageClass)}</h4><ul>${athletesByAgeClass.get(ageClass).map((athlete) => {
    const starts = (athlete.starts ?? []).map((start) => {
      const race = racesById.get(start.raceId);
      const group = groupsById.get(start.groupId);
      return `${race?.name ?? "Bewerb"}${start.startNumber ? ` · Stnr. ${start.startNumber}` : ""}${group?.label ? ` · ${group.label}` : ""}`;
    });
    return `<li><strong>${escapeHtml(athlete.displayName)}</strong><small>${escapeHtml(starts.join(" | ") || "Für dieses Wochenende gemeldet")}</small></li>`;
  }).join("")}</ul></div>`).join("");
}

function renderTipRound() {
  const firstRace = tipRound.races[0];
  const raceDate = new Date(`${firstRace.date}T12:00:00`).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
  dom.heroSeries.textContent = `${firstRace.discipline}${firstRace.location ? ` · ${firstRace.location}` : ""}`;
  dom.heroTitle.textContent = firstRace.name;
  dom.heroDate.innerHTML = `<strong>${escapeHtml(firstRace.day)}, ${escapeHtml(raceDate)}</strong>${tipRound.races.length} Rennen an diesem Wochenende`;
  dom.seasonLabel.textContent = tipRound.seasonId ? `Saison ${tipRound.seasonId.replace("-", "/")}` : "Saisonwertung";
  dom.title.textContent = tipRound.title;
  dom.subtitle.textContent = `${tipRound.subtitle} · ${tipRound.questions.length} Fragen · auf maximal 1.000 Wochenendpunkte normiert`;
  dom.questionList.innerHTML = tipRound.questions.map(renderQuestion).join("");
  const statusLabels = { DRAFT: "Entwurf", OPEN: "Tippabgabe offen", CLOSED: "Tippabgabe geschlossen", EVALUATED: "Ausgewertet", ARCHIVED: "Archiviert", CANCELLED: "Abgesagt" };
  dom.raceList.innerHTML = tipRound.races.map((race) => `<article class="race-card">
    <div class="race-card-top"><span class="race-date">${escapeHtml(race.day)}</span><span class="status">${escapeHtml(statusLabels[tipRound.status] ?? "In dieser Runde")}</span></div>
    <div class="location"><span class="event-icon" aria-hidden="true">S</span><div><strong>${escapeHtml(race.name)}</strong><span>${escapeHtml(race.discipline)}</span></div></div>
    <div class="race-card-bottom"><span>Offizielles Gesamtergebnis zählt</span><button type="button" data-scroll-to-tip>Tippen →</button></div>
  </article>`).join("");
  document.querySelectorAll("[data-scroll-to-tip]").forEach((button) => button.addEventListener("click", () => dom.form.scrollIntoView({ behavior: "smooth" })));
}

function athleteName(athleteId) {
  return athletesById.get(athleteId)?.displayName ?? athleteId;
}

function formatRanking(ranking) {
  return ranking.map((athleteId, index) => `${index + 1}. ${athleteName(athleteId)}`).join(" · ");
}

function formatRankGroups(rankGroups, unclassified = []) {
  const lastPlace = new Set(unclassified);
  let position = 1;
  return rankGroups.map((group) => {
    const names = group.map(athleteName).join(" = ");
    const suffix = group.every((athleteId) => lastPlace.has(athleteId)) ? " (DNF/DSQ, letzter Platz)" : "";
    const label = `${position}. ${names}${suffix}`;
    position += group.length;
    return label;
  }).join(" · ");
}

function formatEvaluationAnswer(answer) {
  if (answer === null || answer === undefined || answer === "") return "Nicht wertbar";
  if (Array.isArray(answer)) return answer.length ? formatRanking(answer) : "Keine gewerteten Athleten";
  if (typeof answer === "object") {
    if (Array.isArray(answer.ranking)) {
      const ranking = Array.isArray(answer.rankGroups)
        ? formatRankGroups(answer.rankGroups, answer.unclassified)
        : formatRanking(answer.ranking);
      const dns = (answer.dns ?? []).map(athleteName);
      return `${ranking || "Keine gewerteten Athleten"}${dns.length ? ` · DNS, nicht berücksichtigt: ${dns.join(", ")}` : ""}`;
    }
    return JSON.stringify(answer);
  }
  if (typeof answer === "string") return athleteName(answer);
  return String(answer);
}

function renderEvaluation(evaluation) {
  const questionsById = new Map(tipRound.questions.map((question) => [question.id, question]));
  const isFixture = evaluation.testFixture || evaluation.submissionId === "perfect-fixture-submission";
  const scoredCount = evaluation.questionEvaluations.filter((item) => item.status === "SCORED").length;
  const annulledCount = evaluation.questionEvaluations.length - scoredCount;

  dom.evaluationWeekendPoints.textContent = String(evaluation.weekendPoints);
  dom.evaluationRawPoints.textContent = `${evaluation.rawPoints} / ${evaluation.maximumRawPoints}`;
  dom.evaluationStatus.textContent = `${scoredCount} Fragen gewertet${annulledCount ? ` · ${annulledCount} annulliert` : ""}.`;
  dom.evaluationBadge.hidden = !isFixture;
  dom.evaluationQuestionList.innerHTML = evaluation.questionEvaluations.map((item, index) => {
    const question = questionsById.get(item.questionId);
    const annulled = item.status === "ANNULLED";
    const percentage = item.maximumPoints ? Math.round(item.points / item.maximumPoints * 100) : 0;
    return `<article class="evaluation-card${annulled ? " annulled" : ""}">
      <div class="evaluation-card-head"><span class="question-number">${String(index + 1).padStart(2, "0")}</span><div><span class="question-scope">Rennen: ${escapeHtml(question?.raceLabel ?? "gesamtes Wochenende")}</span><h3>${escapeHtml(question?.prompt ?? item.questionId)}</h3></div><strong class="evaluation-points">${annulled ? "Annulliert" : `${item.points} / ${item.maximumPoints}`}</strong></div>
      <div class="answer-comparison"><div><span>Dein Tipp</span><strong>${escapeHtml(formatEvaluationAnswer(item.submittedAnswer))}</strong></div><div><span>Ergebnis</span><strong>${escapeHtml(formatEvaluationAnswer(item.actualAnswer))}</strong></div></div>
      <div class="score-bar" aria-label="${percentage} Prozent der Fragepunkte"><span style="width:${percentage}%"></span></div>
    </article>`;
  }).join("");
  dom.evaluationSection.hidden = false;
}

async function optionalJson(url) {
  try {
    const response = await fetch(url);
    return response.ok ? response.json() : null;
  } catch {
    return null;
  }
}

async function optionalJsonFirst(urls) {
  for (const url of urls) {
    const value = await optionalJson(url);
    if (value) return value;
  }
  return null;
}

async function loadResults() {
  const weekendEvaluationUrls = [`/api/v1/predictor/rounds/${encodeURIComponent(tipRound.id)}/evaluation`, "src/data/weekend-evaluation.local.json"];
  const seasonLeaderboardUrls = [`/api/v1/predictor/seasons/${encodeURIComponent(tipRound.seasonId)}/leaderboard`, "src/data/season-leaderboard.local.json"];
  const [weekend, season] = await Promise.all([
    optionalJsonFirst(weekendEvaluationUrls),
    optionalJsonFirst(seasonLeaderboardUrls),
  ]);

  const weekendMatches = weekend?.tipRoundId === tipRound.id && weekend?.tipRoundVersion === tipRound.contentVersion;
  const seasonRoundVersion = season?.tipRoundVersions?.[tipRound.id];
  const seasonMatches = !seasonRoundVersion || seasonRoundVersion === tipRound.contentVersion;
  if (season?.standings && seasonMatches && (!tipRound.seasonId || season.seasonId === tipRound.seasonId)) {
    leaders = season.standings.map((standing) => ({
      rank: standing.rank,
      name: standing.displayName,
      detail: `${standing.rounds} ${standing.rounds === 1 ? "Tipprunde" : "Tipprunden"} · Ø ${standing.averagePoints}`,
      points: standing.seasonPoints,
    }));
  } else if (weekendMatches) {
    leaders = weekend.standings.map((standing) => ({ rank: standing.rank, name: standing.displayName, detail: "Wochenendwertung", points: standing.weekendPoints }));
  }

  const submissionId = storedSubmission()?.id;
  const personalEvaluation = weekendMatches
    ? weekend.evaluations.find((evaluation) => evaluation.submissionId === submissionId)
    : null;
  if (personalEvaluation) {
    renderEvaluation(personalEvaluation);
    return;
  }

  const evaluation = await optionalJson(EVALUATION_URL);
  if (evaluation?.tipRoundId === tipRound.id && evaluation?.tipRoundVersion === tipRound.contentVersion && (!submissionId || evaluation.submissionId === submissionId)) renderEvaluation(evaluation);
}

function valuesForQuestion(question) {
  if (question.type === "HEAD_TO_HEAD") {
    return dom.form.querySelector(`input[name="answer-${question.id}"]:checked`)?.value ?? "";
  }
  if (question.type === "INTERNAL_RANKING" || question.type === "PODIUM") {
    return Array.from(dom.form.querySelectorAll(`[data-question-id="${question.id}"][data-position]`)).map((element) => element.value);
  }
  return dom.form.querySelector(`[data-question-id="${question.id}"]`)?.value ?? "";
}

function validateQuestion(question, showErrors = false) {
  const value = valuesForQuestion(question);
  let error = "";

  if (Array.isArray(value)) {
    if (value.some((item) => !item)) error = "Bitte alle Positionen besetzen.";
    else if (new Set(value).size !== value.length) error = "Jede Person darf nur einmal gewählt werden.";
  } else if (!value) {
    error = "Bitte diese Frage beantworten.";
  } else if (question.type === "NUMBER" || question.type === "PLACEMENT") {
    const numericValue = Number(value);
    if (!Number.isInteger(numericValue) || numericValue < question.minimum || numericValue > question.maximum) {
      error = `Bitte eine ganze Zahl zwischen ${question.minimum} und ${question.maximum} eingeben.`;
    }
  }

  const card = dom.form.querySelector(`[data-question-card="${question.id}"]`);
  const errorElement = dom.form.querySelector(`[data-question-error="${question.id}"]`);
  card.classList.toggle("invalid", Boolean(error) && showErrors);
  errorElement.textContent = showErrors ? error : "";
  return { valid: !error, value };
}

function updateProgress() {
  const answered = tipRound.questions.filter((question) => validateQuestion(question).valid).length;
  dom.progress.textContent = `${answered} / ${tipRound.questions.length} beantwortet`;
}

function storageKey() {
  return `${STORAGE_PREFIX}${tipRound.id}`;
}

function storedSubmission() {
  const rawSubmission = localStorage.getItem(storageKey());
  if (!rawSubmission) return null;
  try {
    const submission = JSON.parse(rawSubmission);
    if (submission.tipRoundVersion !== tipRound.contentVersion) {
      localStorage.removeItem(storageKey());
      return null;
    }
    return submission;
  } catch {
    localStorage.removeItem(storageKey());
    return null;
  }
}

function exportableSubmission(submission) {
  const submittedAt = submission.submittedAt ?? submission.savedAt ?? new Date().toISOString();
  return {
    schemaVersion: 1,
    id: submission.id ?? `local-${tipRound.id}-${submittedAt.replaceAll(/[^0-9]/g, "").slice(0, 14)}`,
    tipRoundId: tipRound.id,
    tipRoundVersion: tipRound.contentVersion,
    player: submission.player,
    submittedAt,
    answers: submission.answers,
  };
}

function updateExportState() {
  const submission = storedSubmission();
  dom.exportButton.disabled = !submission?.player?.displayName;
}

function playerIdForName(name) {
  const slug = name.normalize("NFD").replaceAll(/[\u0300-\u036f]/g, "").toLowerCase().replaceAll(/[^a-z0-9]+/g, "-").replaceAll(/^-|-$/g, "");
  return `local-${slug || "spieler"}`;
}

function collectSubmission() {
  const answers = {};
  let firstInvalidCard;

  tipRound.questions.forEach((question) => {
    const validation = validateQuestion(question, true);
    answers[question.id] = validation.value;
    if (!validation.valid && !firstInvalidCard) firstInvalidCard = dom.form.querySelector(`[data-question-card="${question.id}"]`);
  });

  return { answers, firstInvalidCard };
}

function restoreSubmission() {
  const submission = storedSubmission();
  if (!submission) return;
  try {
    dom.playerName.value = submission.player?.displayName ?? "";
    Object.entries(submission.answers ?? {}).forEach(([questionId, value]) => {
      if (Array.isArray(value)) {
        value.forEach((item, position) => {
          const field = dom.form.querySelector(`[data-question-id="${questionId}"][data-position="${position}"]`);
          if (field) field.value = item;
        });
      } else {
        const radio = dom.form.querySelector(`input[data-question-id="${questionId}"][value="${value}"]`);
        const field = dom.form.querySelector(`[data-question-id="${questionId}"]:not([type="radio"])`);
        if (radio) radio.checked = true;
        else if (field) field.value = value;
      }
    });
    const savedAt = new Date(submission.submittedAt ?? submission.savedAt).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
    dom.message.textContent = `Gespeicherter Tipp geladen · zuletzt gespeichert am ${savedAt}`;
  } catch {
    localStorage.removeItem(storageKey());
  }
  updateExportState();
}

function setLocked(locked) {
  dom.form.querySelectorAll("input, select, #save-prediction, #reset-prediction").forEach((element) => { element.disabled = locked; });
  dom.deadlineStatus.textContent = locked ? "Tippabgabe geschlossen" : "Tippabgabe geöffnet";
  if (locked) dom.message.textContent = "Der Abgabeschluss ist erreicht. Der Tipp kann nicht mehr geändert werden.";
}

function updateCountdown() {
  const roundStatus = tipRound.status ?? "DRAFT";
  if (roundStatus !== "OPEN") {
    document.querySelector("#days").textContent = "--";
    document.querySelector("#hours").textContent = "--";
    document.querySelector("#minutes").textContent = "--";
    setLocked(true);
    const statusText = {
      DRAFT: "Tipprunde noch nicht geöffnet",
      CLOSED: "Tippabgabe geschlossen",
      EVALUATED: "Tipprunde ausgewertet",
      ARCHIVED: "Tipprunde archiviert",
      CANCELLED: "Tipprunde abgesagt",
    };
    dom.deadlineStatus.textContent = statusText[roundStatus] ?? "Tippabgabe geschlossen";
    dom.message.textContent = roundStatus === "EVALUATED"
      ? "Die Tipprunde ist ausgewertet. Die Ergebnisse stehen unten auf der Seite."
      : "Für diese Tipprunde können aktuell keine Tipps abgegeben werden.";
    return;
  }
  if (tipRound.testMode) {
    document.querySelector("#days").textContent = "--";
    document.querySelector("#hours").textContent = "--";
    document.querySelector("#minutes").textContent = "--";
    setLocked(false);
    dom.deadlineStatus.textContent = "Testmodus geöffnet";
    return;
  }
  const remainingMilliseconds = new Date(tipRound.closesAt).getTime() - Date.now();
  const remainingMinutes = Math.max(0, Math.floor(remainingMilliseconds / 60_000));
  document.querySelector("#days").textContent = String(Math.floor(remainingMinutes / 1440)).padStart(2, "0");
  document.querySelector("#hours").textContent = String(Math.floor((remainingMinutes % 1440) / 60)).padStart(2, "0");
  document.querySelector("#minutes").textContent = String(remainingMinutes % 60).padStart(2, "0");
  setLocked(remainingMilliseconds <= 0);
}

function showToast() {
  dom.toast.classList.add("show");
  window.setTimeout(() => dom.toast.classList.remove("show"), 2600);
}

function bindEvents() {
  dom.form.addEventListener("input", () => {
    dom.message.textContent = "Ungespeicherte Änderungen vorhanden.";
    dom.message.classList.remove("error");
    updateProgress();
  });

  dom.form.addEventListener("submit", (event) => {
    event.preventDefault();
    if ((tipRound.status ?? "DRAFT") !== "OPEN") return;
    if (!tipRound.testMode && Date.now() >= new Date(tipRound.closesAt).getTime()) return;

    const playerName = dom.playerName.value.trim();
    if (playerName.length < 2) {
      dom.message.textContent = "Bitte gib deinen Namen für die Rangliste ein.";
      dom.message.classList.add("error");
      dom.playerName.focus();
      return;
    }

    const { answers, firstInvalidCard } = collectSubmission();
    if (firstInvalidCard) {
      dom.message.textContent = "Bitte alle Fragen vollständig und gültig beantworten.";
      dom.message.classList.add("error");
      firstInvalidCard.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }

    const submittedAt = new Date().toISOString();
    const submission = { schemaVersion: 1, id: `local-${tipRound.id}-${submittedAt.replaceAll(/[^0-9]/g, "").slice(0, 14)}`, tipRoundId: tipRound.id, tipRoundVersion: tipRound.contentVersion, player: { id: playerIdForName(playerName), displayName: playerName }, submittedAt, answers };
    localStorage.setItem(storageKey(), JSON.stringify(submission));
    dom.message.textContent = "Dein Tipp wurde lokal gespeichert und kann bis zum Abgabeschluss geändert werden.";
    dom.message.classList.remove("error");
    updateExportState();
    showToast();
  });

  dom.resetButton.addEventListener("click", () => {
    if (!window.confirm("Möchtest du alle Antworten dieser Tipprunde zurücksetzen?")) return;
    localStorage.removeItem(storageKey());
    dom.form.reset();
    tipRound.questions.forEach((question) => validateQuestion(question));
    dom.message.textContent = "Der lokale Tipp wurde zurückgesetzt.";
    dom.message.classList.remove("error");
    updateProgress();
    updateExportState();
  });

  dom.exportButton.addEventListener("click", () => {
    const submission = storedSubmission();
    if (!submission) return;
    const exportData = exportableSubmission(submission);
    const blob = new Blob([`${JSON.stringify(exportData, null, 2)}\n`], { type: "application/json" });
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = `tipp-${tipRound.id}-${exportData.player.id}-${exportData.submittedAt.replaceAll(/[^0-9]/g, "").slice(0, 14)}.json`;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 0);
    dom.message.textContent = "Tipp exportiert. Lege die JSON Datei für die Auswertung im Submission Inbox Ordner ab.";
    dom.message.classList.remove("error");
  });
}

function renderLeaderboard() {
  if (!leaders.length) {
    document.querySelector("#leaderboard-list").innerHTML = `<li class="leaderboard-empty">Noch keine ausgewerteten Tipps.</li>`;
    return;
  }
  document.querySelector("#leaderboard-list").innerHTML = leaders.map((leader) => `<li>
    <span class="rank">${leader.rank}</span><span class="avatar">${escapeHtml(leader.name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase())}</span>
    <span class="person"><strong>${escapeHtml(leader.name)}</strong><span>${escapeHtml(leader.detail)}</span></span>
    <span class="score">${leader.points} <small>Pkt.</small></span>
  </li>`).join("");
}

async function initialize() {
  try {
    let response;
    for (const url of DATA_URLS) {
      response = await fetch(url);
      if (response.ok) break;
    }
    if (!response?.ok) throw new Error(`Tipprunde konnte nicht geladen werden: ${response?.status ?? "keine Antwort"}`);
    tipRound = await response.json();
    athletesById = new Map(tipRound.athletes.map((athlete) => [athlete.id, athlete]));
    renderWeekendOverview();
    renderTipRound();
    await loadResults();
    renderLeaderboard();
    bindEvents();
    restoreSubmission();
    updateExportState();
    updateProgress();
    updateCountdown();
    countdownTimer = window.setInterval(updateCountdown, 60_000);
  } catch (error) {
    dom.title.textContent = "Tipprunde konnte nicht geladen werden";
    dom.subtitle.textContent = "Bitte die Website über den lokalen HTTP-Server öffnen.";
    dom.message.textContent = error.message;
    dom.message.classList.add("error");
  }
}

window.addEventListener("beforeunload", () => window.clearInterval(countdownTimer));
initialize();
