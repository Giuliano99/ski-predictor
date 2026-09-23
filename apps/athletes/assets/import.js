const state = { user: null, jobs: [], documents: [], pollToken: 0 };
const kinds = { DSV_RANKING: "DSV-Rangliste", DSV_RACE_COUNT: "Rennanzahl-Liste" };
const statuses = { PENDING: "Wartet", PROCESSING: "Wird ausgelesen", REVIEW_REQUIRED: "Prüfung nötig", APPROVED: "Freigegeben", SUPERSEDED: "Durch neuere Version ersetzt", FAILED: "Fehlgeschlagen" };
const dom = {
  form: document.querySelector("#import-form"), season: document.querySelector("#import-season"), category: document.querySelector("#import-category"),
  file: document.querySelector("#import-file"), selectedFile: document.querySelector("#selected-file"), jobs: document.querySelector("#import-jobs"), actions: document.querySelector("#import-actions"),
  notice: document.querySelector("#notice"), status: document.querySelector("#import-status"), busy: document.querySelector("#busy"), busyLabel: document.querySelector("#busy-label"), logout: document.querySelector("#logout-button"),
};

function escapeHtml(value) { const node = document.createElement("div"); node.textContent = String(value ?? ""); return node.innerHTML; }
function showNotice(message, error = false) { dom.notice.textContent = message; dom.notice.classList.toggle("error", error); dom.notice.hidden = false; }
function setBusy(label) { dom.busyLabel.textContent = label; dom.busy.hidden = false; }
function clearBusy() { dom.busy.hidden = true; }

async function request(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && state.user?.csrfToken) options.headers = { ...(options.headers || {}), "X-CSRF-Token": state.user.csrfToken };
  const response = await fetch(url, options); let body = {};
  try { body = await response.json(); } catch { body = {}; }
  if (response.status === 401 || response.status === 403) { window.location.replace("/login/?next=/athleten/import.html"); throw new Error("Bitte anmelden."); }
  if (!response.ok) throw new Error(body.error?.message || body.error || `Fehler ${response.status}`);
  return body;
}

function relevantJobs() {
  return state.jobs.filter((job) => Object.hasOwn(kinds, job.documentKind)).filter((job, index, all) => all.findIndex((candidate) => candidate.documentId === job.documentId) === index);
}

function render() {
  const jobs = relevantJobs();
  const documents = state.documents.filter((document) => Object.hasOwn(kinds, document.kind));
  const documentById = Object.fromEntries(documents.map((document) => [document.documentId, document]));
  const pendingDocuments = documents.filter((document) => !jobs.some((job) => job.documentId === document.documentId));
  const jobHtml = jobs.map((job) => {
    const document = documentById[job.documentId]; const statistics = job.review?.statistics || {}; const warnings = job.review?.warnings || [];
    const details = job.review ? `<details><summary>Prüfbericht ansehen</summary><div class="import-stats"><span>${statistics.sections || 0} Abschnitte</span><span>${statistics.entries || 0} Einträge</span><span>${statistics.uniqueAthletes || 0} Athleten</span><span>${statistics.targetClubUniqueAthletes || 0} Oberhachinger</span></div>${warnings.length ? `<ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>` : `<p>Keine Warnungen. Saison und Stichtag wurden erkannt.</p>`}</details>` : "";
    const action = job.status === "REVIEW_REQUIRED" ? `<button class="secondary-button" data-approve="${job.jobId}" type="button">Geprüft und freigeben</button>` : job.status === "FAILED" ? `<button class="secondary-button" data-extract="${job.documentId}" type="button">Erneut auslesen</button>` : "";
    return `<article class="import-job ${job.status}"><div><strong>${escapeHtml(job.sourceName)}</strong><small>${escapeHtml(kinds[job.documentKind])} · Saison ${escapeHtml(job.seasonId || document?.seasonId || "unbekannt")} · ${escapeHtml(statuses[job.status] || job.status)}</small>${job.error ? `<small class="job-error">${escapeHtml(job.error)}</small>` : ""}</div>${action}${details}</article>`;
  }).join("");
  const pendingHtml = pendingDocuments.map((document) => `<article class="import-job"><div><strong>${escapeHtml(document.originalName)}</strong><small>${escapeHtml(kinds[document.kind])} · Saison ${escapeHtml(document.seasonId || "unbekannt")} · Noch nicht ausgelesen</small></div><button class="secondary-button" data-extract="${document.documentId}" type="button">Jetzt auslesen</button></article>`).join("");
  dom.jobs.innerHTML = jobHtml || pendingHtml ? `${jobHtml}${pendingHtml}` : "<p>Noch keine DSV-Ranglisten oder Rennanzahl-Listen importiert.</p>";
  const ready = jobs.filter((job) => job.status === "REVIEW_REQUIRED" && job.review?.status === "BEREIT" && !(job.review?.warnings || []).length).length;
  const active = jobs.some((job) => ["PENDING", "PROCESSING"].includes(job.status));
  dom.status.textContent = active ? "LÄUFT" : ready ? "PRÜFEN" : "BEREIT";
  dom.status.className = `status-badge ${active ? "PROCESSING" : ready ? "REVIEW_REQUIRED" : "APPROVED"}`;
  dom.actions.innerHTML = ready ? `<button class="primary-button" id="approve-ready" type="button">${ready} grüne Prüfung${ready === 1 ? "" : "en"} freigeben</button>` : "";
  dom.jobs.querySelectorAll("[data-approve]").forEach((button) => button.addEventListener("click", () => approve(button.dataset.approve)));
  dom.jobs.querySelectorAll("[data-extract]").forEach((button) => button.addEventListener("click", () => extract(button.dataset.extract)));
  document.querySelector("#approve-ready")?.addEventListener("click", approveReady);
}

async function refresh() {
  const [jobPayload, documentPayload] = await Promise.all([request("/api/v1/extraction-jobs"), request("/api/v1/documents?limit=500")]);
  state.jobs = jobPayload.items; state.documents = documentPayload.items; render();
}

async function poll(token) {
  for (let attempt = 0; attempt < 160 && token === state.pollToken; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 750)); await refresh();
    if (!relevantJobs().some((job) => ["PENDING", "PROCESSING"].includes(job.status))) break;
  }
}

async function upload(event) {
  event.preventDefault(); const file = dom.file.files?.[0];
  if (!file) { showNotice("Bitte eine PDF-Datei auswählen.", true); return; }
  setBusy("PDF wird gespeichert und ausgelesen");
  try {
    const url = `/api/v1/athlete-data/files/${encodeURIComponent(dom.category.value)}?seasonId=${encodeURIComponent(dom.season.value)}&filename=${encodeURIComponent(file.name)}`;
    const payload = await request(url, { method:"POST", headers:{ "Content-Type":file.type || "application/pdf" }, body:file });
    showNotice(payload.message); dom.form.reset(); setDefaultSeason(); dom.selectedFile.textContent = "Noch keine Datei ausgewählt."; clearBusy(); await poll(++state.pollToken);
  } catch (error) { showNotice(error.message, true); clearBusy(); await refresh(); }
}

async function extract(documentId) {
  setBusy("PDF wird ausgelesen");
  try { const payload = await request(`/api/v1/documents/${documentId}/extract`, { method:"POST", headers:{ "Content-Type":"application/json" }, body:"{}" }); showNotice(payload.created ? "Die automatische Prüfung wurde gestartet." : "Es liegt bereits eine aktuelle Prüfung vor."); clearBusy(); await poll(++state.pollToken); }
  catch (error) { showNotice(error.message, true); clearBusy(); await refresh(); }
}

async function approve(jobId) {
  if (!window.confirm("Hast du Saison, Stichtag, Anzahl der Einträge und Warnungen kontrolliert?")) return;
  try { const payload = await request(`/api/v1/extraction-jobs/${jobId}/approve`, { method:"POST", headers:{ "Content-Type":"application/json" }, body:"{}" }); showNotice(payload.message); await refresh(); }
  catch (error) { showNotice(error.message, true); }
}

async function approveReady() {
  if (!window.confirm("Alle grünen Prüfberichte gemeinsam freigeben?")) return;
  setBusy("Geprüfte Daten werden freigegeben");
  try { const payload = await request("/api/v1/athlete-data/extractions/approve-ready", { method:"POST", headers:{ "Content-Type":"application/json" }, body:"{}" }); showNotice(payload.message); await refresh(); }
  catch (error) { showNotice(error.message, true); } finally { clearBusy(); }
}

function setDefaultSeason() { const now = new Date(); const start = now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1; dom.season.value = `${start}-${start + 1}`; }
async function initialize() { try { const identity = await request("/api/v1/auth/me"); state.user = identity.user; setDefaultSeason(); await refresh(); } catch (error) { showNotice(error.message, true); } }

dom.form.addEventListener("submit", upload);
dom.file.addEventListener("change", () => { dom.selectedFile.textContent = dom.file.files?.[0]?.name || "Noch keine Datei ausgewählt."; });
document.querySelector("#refresh-button").addEventListener("click", () => refresh().catch((error) => showNotice(error.message, true)));
dom.logout.addEventListener("click", async () => { try { await request("/api/v1/auth/logout", { method:"POST" }); } finally { window.location.replace("/login/"); } });
initialize();
