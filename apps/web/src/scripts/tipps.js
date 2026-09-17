const dom = {
  accountName: document.querySelector("#account-name"),
  logoutButton: document.querySelector("#logout-button"),
  intro: document.querySelector("#page-intro"),
  count: document.querySelector("#submission-count"),
  list: document.querySelector("#submission-list"),
  visibilityNote: document.querySelector("#visibility-note"),
  visibilityTitle: document.querySelector("#visibility-title"),
  visibilityCopy: document.querySelector("#visibility-copy"),
};

let authUser;

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function formatDate(value) {
  if (!value) return "Zeitpunkt unbekannt";
  return new Date(value).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
}

function formatDeadline(value) {
  if (!value) return "dem Abgabeschluss";
  return new Date(value).toLocaleString("de-DE", { dateStyle: "long", timeStyle: "short" });
}

function answerLabel(answer, question, athletes) {
  const athleteName = (id) => athletes.get(id)?.displayName ?? id;
  if (Array.isArray(answer)) return answer.map((id, index) => `${index + 1}. ${athleteName(id)}`).join(" · ");
  if (["ATHLETE", "HEAD_TO_HEAD"].includes(question.type)) return athleteName(answer);
  return String(answer ?? "Keine Antwort");
}

async function initialize() {
  try {
    const authResponse = await fetch("/api/v1/auth/me");
    if (!authResponse.ok) {
      window.location.replace("/login/?next=/tippspiel/tipps.html");
      return;
    }
    const auth = await authResponse.json();
    authUser = auth.user;
    dom.accountName.textContent = authUser.displayName;
    dom.logoutButton.hidden = auth.authentication !== "required";

    const roundResponse = await fetch("/api/v1/predictor/rounds/current");
    if (!roundResponse.ok) throw new Error("Die aktuelle Tipprunde konnte nicht geladen werden.");
    const round = await roundResponse.json();
    const submissionsResponse = await fetch(`/api/v1/predictor/rounds/${encodeURIComponent(round.id)}/submissions`);
    if (!submissionsResponse.ok) throw new Error("Die Tipps der Mitspieler konnten nicht geladen werden.");
    const payload = await submissionsResponse.json();
    const athletes = new Map((round.athletes ?? []).map((athlete) => [athlete.id, athlete]));
    const questions = new Map((round.questions ?? []).map((question) => [question.id, question]));

    dom.intro.textContent = `${round.title} · ${round.questions.length} Fragen`;
    if (payload.visible === false) {
      dom.count.textContent = "Noch gesperrt";
      dom.visibilityNote.classList.add("is-locked");
      dom.visibilityTitle.textContent = "Tipps bleiben bis zum Abgabeschluss geheim";
      dom.visibilityCopy.textContent = `Freigabe nach Schließung der Tippabgabe am ${formatDeadline(payload.closesAt)}.`;
      dom.list.innerHTML = '<section class="community-locked"><span aria-hidden="true">🔒</span><h2>Noch nicht sichtbar</h2><p>Damit niemand durch fremde Tipps beeinflusst wird, werden alle Abgaben erst nach dem Abgabeschluss gemeinsam freigeschaltet.</p><a class="button button-dark" href="index.html#tipp">Meinen Tipp abgeben</a></section>';
      return;
    }
    dom.visibilityNote.classList.remove("is-locked");
    dom.visibilityTitle.textContent = "Für alle Mitspieler sichtbar";
    dom.visibilityCopy.textContent = "Gezeigt wird pro Person nur die zuletzt gespeicherte Abgabe der aktuellen Tipprunde.";
    dom.count.textContent = `${payload.total} ${payload.total === 1 ? "Tipp" : "Tipps"}`;
    if (!payload.items.length) {
      dom.list.innerHTML = '<p class="empty-state">Noch niemand hat für diese Tipprunde einen Tipp gespeichert.</p>';
      return;
    }
    dom.list.innerHTML = payload.items.map((submission) => {
      const rows = round.questions.map((question, index) => {
        const score = submission.evaluation?.questions?.[question.id];
        const scoreLabel = score ? (score.status === "SCORED" ? `${score.points} / ${score.maximumPoints}` : "Annulliert") : "Offen";
        return `<li><span class="community-question-number">${String(index + 1).padStart(2, "0")}</span><div><small>${escapeHtml(question.prompt)}</small><strong>${escapeHtml(answerLabel(submission.answers[question.id], questions.get(question.id), athletes))}</strong>${score?.scoreExplanation ? `<p class="community-score-explanation">${escapeHtml(score.scoreExplanation)}</p>` : ""}</div><span class="community-question-score${score?.status === "SCORED" ? " is-scored" : ""}">${escapeHtml(scoreLabel)}<small>Punkte</small></span></li>`;
      }).join("");
      const total = submission.evaluation ? `<div class="community-total"><strong>${submission.evaluation.weekendPoints}</strong><span>von ${submission.evaluation.maximumWeekendPoints}<br />Punkten</span></div>` : '<div class="community-total is-open"><span>Noch nicht<br />ausgewertet</span></div>';
      return `<article class="community-card${submission.player.id === authUser.id ? " is-current-user" : ""}"><header><div class="community-avatar">${escapeHtml(submission.player.displayName.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase())}</div><div><h2>${escapeHtml(submission.player.displayName)}${submission.player.id === authUser.id ? ' <span class="self-label">Du</span>' : ""}</h2><p>Gespeichert ${escapeHtml(formatDate(submission.submittedAt))}</p></div>${total}</header><ol>${rows}</ol></article>`;
    }).join("");
  } catch (error) {
    dom.list.innerHTML = `<p class="empty-state error-state">${escapeHtml(error.message)}</p>`;
  }
}

dom.logoutButton.addEventListener("click", async () => {
  await fetch("/api/v1/auth/logout", { method: "POST", headers: { "X-CSRF-Token": authUser.csrfToken } });
  window.location.replace("/login/");
});

initialize();
