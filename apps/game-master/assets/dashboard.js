const state = { weekends: [], extractionJobs: [], athletes: [], selectedId: null, pendingConfirmation: null, extractionPoll: 0 };
const labels = { DRAFT: "Entwurf", OPEN: "Tippen geöffnet", CLOSED: "Tippen geschlossen", EVALUATED: "Ausgewertet", ARCHIVED: "Archiviert", CANCELLED: "Abgesagt", FEHLER: "Fehler" };
const extractionLabels = { PENDING: "Wartet", PROCESSING: "Wird ausgelesen", REVIEW_REQUIRED: "Prüfung nötig", APPROVED: "Freigegeben", FAILED: "Fehlgeschlagen" };
const dom = {
  dashboard: document.querySelector("#dashboard"), empty: document.querySelector("#empty"), list: document.querySelector("#weekend-list"), detail: document.querySelector("#weekend-detail"),
  notice: document.querySelector("#notice"), newDialog: document.querySelector("#new-weekend-dialog"), newForm: document.querySelector("#new-weekend-form"),
  confirmDialog: document.querySelector("#confirm-dialog"), confirmTitle: document.querySelector("#confirm-title"), confirmText: document.querySelector("#confirm-text"), confirmButton: document.querySelector("#confirm-button"),
};

function escapeHtml(value) { const node = document.createElement("div"); node.textContent = String(value ?? ""); return node.innerHTML; }
function selectedWeekend() { return state.weekends.find((weekend) => weekend.id === state.selectedId); }
function showNotice(message, error = false) { dom.notice.textContent = message; dom.notice.classList.toggle("error", error); dom.notice.hidden = false; window.scrollTo({ top: 0, behavior: "smooth" }); }
function setBusy(label) { let overlay = document.querySelector("#busy"); if (!overlay) { overlay = document.createElement("div"); overlay.id = "busy"; overlay.className = "busy"; document.body.append(overlay); } overlay.innerHTML = `<div><div class="spinner"></div><strong>${escapeHtml(label)}</strong><p>Das kann bei mehreren PDF-Dateien einen Moment dauern.</p></div>`; overlay.hidden = false; }
function clearBusy() { const overlay = document.querySelector("#busy"); if (overlay) overlay.hidden = true; }

async function request(url, options = {}) {
  const response = await fetch(url, options);
  let body = {};
  try { body = await response.json(); } catch { body = {}; }
  if (!response.ok) throw new Error(body.error?.message || body.error || `Fehler ${response.status}`);
  return body;
}

async function refresh(preferredId = state.selectedId) {
  const [payload, extractions, athletes] = await Promise.all([request("/api/v1/weekends"), request("/api/v1/extraction-jobs"), request("/api/v1/athletes")]);
  state.weekends = payload.weekends;
  state.extractionJobs = extractions.items;
  state.athletes = athletes.items;
  state.selectedId = state.weekends.some((weekend) => weekend.id === preferredId) ? preferredId : state.weekends[0]?.id ?? null;
  render();
}

function renderList() {
  dom.list.innerHTML = state.weekends.map((weekend) => `<button class="weekend-item${weekend.id === state.selectedId ? " active" : ""}" data-weekend-id="${weekend.id}" type="button"><strong>${escapeHtml(weekend.title)}</strong><small>${escapeHtml(labels[weekend.status] ?? weekend.status)} · ${escapeHtml(weekend.id.replace("tip-round-", ""))}</small></button>`).join("");
  dom.list.querySelectorAll("[data-weekend-id]").forEach((button) => button.addEventListener("click", () => { state.selectedId = button.dataset.weekendId; render(); }));
}

function filesHtml(files, emptyText) {
  if (!files.length) return `<p>${escapeHtml(emptyText)}</p>`;
  return `<ul class="file-list">${files.map((file) => `<li>${escapeHtml(file.name)}</li>`).join("")}</ul>`;
}

function uploadHtml(category, accept, multiple, label, enabled) {
  if (!enabled) return "";
  return `<label class="button secondary upload-button">${escapeHtml(label)}<input data-upload="${category}" type="file" accept="${accept}" ${multiple ? "multiple" : ""}></label>`;
}

function reportHtml(report, title) {
  if (!report) return `<div class="report"><div class="report-head"><span>${escapeHtml(title)}</span><span>Noch nicht erstellt</span></div></div>`;
  const issues = [...report.errors, ...report.warnings];
  return `<div class="report"><div class="report-head ${report.status}"><span>${escapeHtml(title)}</span><span>${escapeHtml(report.status)}</span></div>${issues.length ? `<ul>${issues.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}<details><summary style="padding:12px 14px;cursor:pointer">Vollständigen Bericht anzeigen</summary><pre>${escapeHtml(report.content)}</pre></details></div>`;
}

function stepHtml(number, title, description, body, condition, active) {
  return `<article class="step ${condition ? "done" : active ? "active" : ""}"><span class="step-number">${condition ? "✓" : number}</span><div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p>${body}</div></article>`;
}

function actionButton(action, label, style = "") { return `<button class="button ${style}" data-action="${action}" type="button">${escapeHtml(label)}</button>`; }

function extractionHtml(weekend) {
  const weekendDate = weekend.id.replace("tip-round-", "");
  const jobs = state.extractionJobs
    .filter((job) => job.weekendDate === weekendDate)
    .filter((job, index, all) => all.findIndex((candidate) => candidate.documentId === job.documentId) === index);
  const list = jobs.length ? `<ul class="file-list">${jobs.map((job) => {
    const review = job.review?.warnings?.length ? ` · ${job.review.warnings.length} Warnung${job.review.warnings.length === 1 ? "" : "en"}` : "";
    const error = job.error ? `<small>${escapeHtml(job.error)}</small>` : "";
    const identityStats = job.review?.statistics?.identities ?? {};
    const identityText = Object.entries(identityStats).map(([key, value]) => `${key}: ${value}`).join(" · ");
    const reviewDetails = job.review ? `<details><summary>Prüfbericht anzeigen</summary><p>${job.review.statistics.groups} Gruppen · ${job.review.statistics.participants} Teilnehmer · ${job.review.statistics.targetClubParticipants} Oberhachinger</p>${identityText ? `<p><strong>Athletenidentität:</strong> ${escapeHtml(identityText)}</p>` : ""}${job.review.warnings.length ? `<ul>${job.review.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>` : `<p>Keine Warnungen.</p>`}</details>` : "";
    const approve = job.status === "REVIEW_REQUIRED" ? `<button class="button secondary" data-approve-extraction="${job.jobId}" type="button">Prüfen und freigeben</button>` : "";
    return `<li class="extraction-item"><span><strong>${escapeHtml(job.sourceName)}</strong><small>${escapeHtml(extractionLabels[job.status] ?? job.status)}${escapeHtml(review)}</small>${error}${reviewDetails}</span>${approve}</li>`;
  }).join("")}</ul>` : `<p>Noch keine wiederverwendbaren Renndaten erzeugt.</p>`;
  const active = jobs.some((job) => ["PENDING", "PROCESSING"].includes(job.status));
  const approved = jobs.filter((job) => job.status === "APPROVED").length;
  const athleteOptions = state.athletes.map((athlete) => `<option value="${athlete.id}">${escapeHtml(athlete.fullName)} · ${athlete.birthYear} · ${escapeHtml(athlete.club)}</option>`).join("");
  const registry = state.athletes.length ? `<details class="athlete-registry"><summary>Athletenkartei verwalten (${state.athletes.length})</summary><p>Nur verwenden, wenn dieselbe Person versehentlich mit zwei Kennungen angelegt wurde.</p><div class="identity-merge"><label>Doppelte Identität<select id="merge-source"><option value="">Bitte auswählen</option>${athleteOptions}</select></label><label>Behaltene Identität<select id="merge-target"><option value="">Bitte auswählen</option>${athleteOptions}</select></label><button class="button secondary" data-merge-athletes type="button">Identitäten zusammenführen</button></div></details>` : "";
  return `${list}<div class="card-actions"><button class="button secondary" data-extract-weekend type="button" ${active ? "disabled" : ""}>${active ? "PDFs werden ausgelesen …" : "Neue PDFs auslesen"}</button>${approved ? `<a class="button secondary" href="/api/v1/races" target="_blank">${approved} freigegebene Datensätze ansehen</a>` : ""}</div>${registry}`;
}

function renderDetail(weekend) {
  if (weekend.loadError) { dom.detail.innerHTML = `<section class="detail"><div class="detail-header"><div><span class="status-badge FEHLER">FEHLER</span><h2>${escapeHtml(weekend.title)}</h2><p>${escapeHtml(weekend.loadError)}</p></div></div></section>`; return; }
  const fragment = document.querySelector("#detail-template").content.cloneNode(true);
  const root = fragment.querySelector(".detail");
  root.querySelector(".status-badge").textContent = labels[weekend.status] ?? weekend.status;
  root.querySelector(".status-badge").classList.add(weekend.status);
  root.querySelector(".weekend-title").textContent = weekend.title;
  root.querySelector(".season").textContent = `Saison ${weekend.seasonId}${weekend.testMode ? " · Testmodus" : ""}${weekend.storageRoot ? ` · Externer Datenordner: ${weekend.storageRoot}` : ""}`;
  const headerActions = root.querySelector(".detail-actions");
  if (weekend.actions.reset) headerActions.innerHTML += actionButton("reset", "Testablauf neu starten", "secondary");
  if (weekend.actions.cancel) headerActions.innerHTML += actionButton("cancel", "Wochenende absagen", "secondary");
  if (weekend.actions.archive) headerActions.innerHTML += actionButton("archive", "Abschließen und archivieren", "secondary");

  const prepared = weekend.reports.preparation?.status === "BEREIT";
  const evaluated = weekend.status === "EVALUATED" || weekend.status === "ARCHIVED";
  const questionsBody = weekend.status === "DRAFT" ? `<textarea class="questions-editor" id="questions-editor" spellcheck="false">${escapeHtml(weekend.questions)}</textarea><div class="card-actions"><button class="button secondary" id="save-questions" type="button">Fragen speichern</button></div>` : `<p>Die veröffentlichten Fragen sind durch die Inhaltsversion geschützt.</p>`;
  const startBody = `${filesHtml(weekend.files.startLists, "Noch keine Startlisten abgelegt.")}<div class="card-actions">${uploadHtml("start-lists", ".pdf,application/pdf", true, "Startlisten auswählen", weekend.status === "DRAFT")}</div>`;
  const prepareBody = `${reportHtml(weekend.reports.preparation, "Prüfbericht zur Tipprunde")}<div class="card-actions">${weekend.actions.prepare ? actionButton("prepare", prepared ? "Erneut automatisch prüfen" : "Automatisch vorbereiten und prüfen") : ""}${weekend.actions.open ? actionButton("open", "Prüfung bestätigen und Tipprunde öffnen") : ""}</div>`;
  const submissionsBody = `${filesHtml(weekend.files.submissions, "Noch keine Tippabgaben vorhanden.")}<div class="card-actions">${uploadHtml("submissions", ".json,application/json", true, "Tippdateien auswählen", ["OPEN", "CLOSED"].includes(weekend.status))}${weekend.actions.close ? actionButton("close", "Tippabgabe jetzt schließen") : ""}</div>`;
  const resultsBody = `${filesHtml(weekend.files.results, "Noch keine Ergebnislisten abgelegt.")}<div class="card-actions">${uploadHtml("results", ".pdf,application/pdf", true, "Ergebnislisten auswählen", weekend.status === "CLOSED")}${weekend.actions.evaluate ? actionButton("evaluate", "Automatisch prüfen und auswerten") : ""}</div>`;
  const evaluationBody = `${reportHtml(weekend.reports.results, "Prüfbericht zu Ergebnissen und Tipps")}<div class="card-actions"><a class="button secondary" href="/tippspiel/#auswertung" target="_blank">Auswertung auf der Website prüfen</a></div>`;
  root.querySelector(".steps").innerHTML = [
    stepHtml("D", "PDF-Daten für weitere Projekte", "PDFs automatisch in strukturierte Renndaten umwandeln. Nur bestätigte Extraktionen werden über die allgemeine API veröffentlicht.", extractionHtml(weekend), false, false),
    stepHtml(1, "Startlisten ablegen", "Alle PDF-Startlisten des Wochenendes auswählen.", startBody, weekend.files.startLists.length > 0, weekend.status === "DRAFT"),
    stepHtml(2, "Fragen festlegen", "Vorschläge anpassen und speichern. Die Rennzuordnung wird beim Import geprüft.", questionsBody, prepared || weekend.status !== "DRAFT", weekend.status === "DRAFT"),
    stepHtml(3, "Automatisch vorbereiten und prüfen", "Starter, Rennen und Fragen werden verarbeitet. Öffnen ist erst bei einem grünen Bericht möglich.", prepareBody, ["OPEN", "CLOSED", "EVALUATED", "ARCHIVED"].includes(weekend.status), weekend.status === "DRAFT"),
    stepHtml(4, "Tippabgaben sammeln", "Die Website legt gültige Tipps hier automatisch ab. Der manuelle Upload bleibt nur für Sicherungsdateien verfügbar. Die neueste Abgabe pro Person zählt.", submissionsBody, ["CLOSED", "EVALUATED", "ARCHIVED"].includes(weekend.status), weekend.status === "OPEN"),
    stepHtml(5, "Ergebnislisten auswerten", "PDFs auswählen. Zuordnung, Statusregeln, Punkte und Saisonwertung laufen automatisch.", resultsBody, evaluated, weekend.status === "CLOSED"),
    stepHtml(6, "Ergebnis kontrollieren", "Prüfbericht und Website ansehen. Danach kann das Wochenende archiviert werden.", evaluationBody, weekend.status === "ARCHIVED", weekend.status === "EVALUATED"),
  ].join("");
  dom.detail.replaceChildren(fragment);
  bindDetailEvents();
}

function render() {
  const weekend = selectedWeekend();
  dom.empty.hidden = Boolean(weekend);
  dom.dashboard.hidden = !weekend;
  if (!weekend) return;
  renderList();
  renderDetail(weekend);
}

async function uploadFiles(category, files) {
  const weekend = selectedWeekend();
  setBusy(`${files.length} Datei${files.length === 1 ? "" : "en"} werden abgelegt ...`);
  try {
    for (const file of files) {
      await request(`/api/v1/weekends/${weekend.id}/files/${category}?filename=${encodeURIComponent(file.name)}`, { method: "POST", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file });
    }
    showNotice(`${files.length} Datei${files.length === 1 ? "" : "en"} erfolgreich abgelegt.`);
    await refresh(weekend.id);
    if (category === "results" && selectedWeekend()?.actions.evaluate) await runAction("evaluate");
    if (category === "start-lists" && selectedWeekend()?.actions.prepare && !/\[[A-ZÄÖÜ0-9 ]+\]/.test(selectedWeekend().questions)) await runAction("prepare");
  } catch (error) { showNotice(error.message, true); } finally { clearBusy(); }
}

async function runAction(action) {
  const weekend = selectedWeekend();
  const busyLabels = { prepare: "Startlisten und Fragen werden verarbeitet ...", evaluate: "Ergebnisse und Tipps werden ausgewertet ...", open: "Tipprunde wird geöffnet ...", close: "Tippabgabe wird geschlossen ...", archive: "Wochenende wird archiviert ...", cancel: "Wochenende wird abgesagt ...", reset: "Testwochenende wird zurückgesetzt ..." };
  setBusy(busyLabels[action]);
  try {
    const payload = await request(`/api/v1/weekends/${weekend.id}/actions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }) });
    showNotice(payload.message);
    await refresh(weekend.id);
  } catch (error) { showNotice(error.message, true); await refresh(weekend.id); } finally { clearBusy(); }
}

function confirmAction(action) {
  const content = {
    reset: ["Testablauf neu starten?", "Das Wochenende springt zurück zu Fragen festlegen. PDFs und Tippabgaben bleiben erhalten. Alte Auswertungsdateien werden entfernt."],
    open: ["Tipprunde wirklich öffnen?", "Bitte kontrolliere vorher den grünen Prüfbericht. Nach dem Öffnen sind Rennen, Starter und Fragen verbindlich und versionsgeschützt."],
    close: ["Tippabgabe jetzt schließen?", "Danach können keine Tipps mehr geändert werden. Vorhandene Tippdateien bleiben erhalten."],
    archive: ["Wochenende archivieren?", "Bitte kontrolliere vorher Prüfbericht, Punkte und Ranglisten auf der Website."],
    cancel: ["Rennwochenende absagen?", "Die Tipprunde wird abgesagt und kann danach nur noch archiviert werden."],
  }[action];
  state.pendingConfirmation = action; dom.confirmTitle.textContent = content[0]; dom.confirmText.textContent = content[1]; dom.confirmDialog.showModal();
}

function bindDetailEvents() {
  dom.detail.querySelectorAll("[data-upload]").forEach((input) => input.addEventListener("change", () => { if (input.files.length) uploadFiles(input.dataset.upload, Array.from(input.files)); }));
  dom.detail.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => ["open", "close", "archive", "cancel", "reset"].includes(button.dataset.action) ? confirmAction(button.dataset.action) : runAction(button.dataset.action)));
  document.querySelector("#save-questions")?.addEventListener("click", async () => {
    try { const id = selectedWeekend().id; const payload = await request(`/api/v1/weekends/${id}/questions`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: document.querySelector("#questions-editor").value }) }); showNotice(`${payload.message} Die automatische Prüfung startet jetzt.`); await refresh(id); if (selectedWeekend()?.actions.prepare) await runAction("prepare"); }
    catch (error) { showNotice(error.message, true); }
  });
  document.querySelector("[data-extract-weekend]")?.addEventListener("click", startWeekendExtraction);
  document.querySelector("[data-merge-athletes]")?.addEventListener("click", mergeAthletes);
  dom.detail.querySelectorAll("[data-approve-extraction]").forEach((button) => button.addEventListener("click", () => approveExtraction(button.dataset.approveExtraction)));
}

async function pollExtractions(weekendId, token) {
  for (let attempt = 0; attempt < 120 && token === state.extractionPoll; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 750));
    await refresh(weekendId);
    const date = weekendId.replace("tip-round-", "");
    if (!state.extractionJobs.some((job) => job.weekendDate === date && ["PENDING", "PROCESSING"].includes(job.status))) break;
  }
}

async function startWeekendExtraction() {
  const weekend = selectedWeekend();
  setBusy("PDFs werden automatisch ausgelesen ...");
  try {
    const payload = await request(`/api/v1/weekends/${weekend.id}/extractions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    showNotice(payload.message);
    const token = ++state.extractionPoll;
    clearBusy();
    await pollExtractions(weekend.id, token);
  } catch (error) { showNotice(error.message, true); clearBusy(); }
}

async function approveExtraction(jobId) {
  const weekend = selectedWeekend();
  try {
    const payload = await request(`/api/v1/extraction-jobs/${jobId}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    showNotice(payload.message);
    const token = ++state.extractionPoll;
    await pollExtractions(weekend.id, token);
  } catch (error) { showNotice(error.message, true); await refresh(weekend.id); }
}

async function mergeAthletes() {
  const sourceAthleteId = document.querySelector("#merge-source")?.value;
  const targetAthleteId = document.querySelector("#merge-target")?.value;
  if (!sourceAthleteId || !targetAthleteId || sourceAthleteId === targetAthleteId) {
    showNotice("Bitte zwei unterschiedliche Athletenidentitäten auswählen.", true);
    return;
  }
  if (!window.confirm("Sind beide Einträge wirklich dieselbe Person? Die zweite Identität wird künftig als gemeinsame Kennung verwendet.")) return;
  try {
    const payload = await request("/api/v1/athlete-identities/merge", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sourceAthleteId, targetAthleteId }) });
    showNotice(payload.message);
    await refresh(selectedWeekend()?.id);
  } catch (error) { showNotice(error.message, true); }
}

document.querySelector("#new-weekend-button").addEventListener("click", () => dom.newDialog.showModal());
document.querySelector("#refresh-button").addEventListener("click", () => refresh().catch((error) => showNotice(error.message, true)));
document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
dom.confirmButton.addEventListener("click", () => { const action = state.pendingConfirmation; dom.confirmDialog.close(); if (action) runAction(action); });
dom.newForm.addEventListener("submit", async (event) => {
  event.preventDefault(); const form = new FormData(dom.newForm); setBusy("Rennwochenende wird angelegt ...");
  try { const payload = await request("/api/v1/weekends", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ date: form.get("date"), title: form.get("title"), testMode: form.get("testMode") === "on" }) }); dom.newDialog.close(); dom.newForm.reset(); showNotice(payload.message); await refresh(payload.weekend.id); }
  catch (error) { showNotice(error.message, true); } finally { clearBusy(); }
});

refresh().catch((error) => showNotice(error.message, true));
