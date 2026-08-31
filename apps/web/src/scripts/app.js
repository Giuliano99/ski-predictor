const athletes = [
  { name: "Marco Odermatt", country: "SUI" },
  { name: "Vincent Kriechmayr", country: "AUT" },
  { name: "Dominik Paris", country: "ITA" },
  { name: "Aleksander Aamodt Kilde", country: "NOR" },
  { name: "Cyprien Sarrazin", country: "FRA" },
  { name: "Franjo von Allmen", country: "SUI" },
];

const leaders = [
  { name: "Lena B.", initials: "LB", detail: "8 richtige Tipps", points: 184, color: "#be6c52" },
  { name: "Max S.", initials: "MS", detail: "7 richtige Tipps", points: 176, color: "#376c91" },
  { name: "Sophie K.", initials: "SK", detail: "7 richtige Tipps", points: 169, color: "#657e59" },
  { name: "Du", initials: "GG", detail: "5 richtige Tipps", points: 142, color: "#0d6e59" },
  { name: "Jonas R.", initials: "JR", detail: "5 richtige Tipps", points: 138, color: "#80689a" },
];

const races = [
  { date: "28. Januar · 11:30", place: "Schladming", country: "Österreich", type: "Riesenslalom", flag: "at", deadline: "Tippende in 6 Tagen" },
  { date: "02. Februar · 10:15", place: "Crans-Montana", country: "Schweiz", type: "Abfahrt Damen", flag: "ch", deadline: "Tippende in 11 Tagen" },
  { date: "08. Februar · 12:00", place: "Garmisch", country: "Deutschland", type: "Super-G", flag: "de", deadline: "Tippende in 17 Tagen" },
];

const picks = [1, 2, 3].map((place, index) => {
  const select = document.querySelector(`#pick-${place}`);
  select.innerHTML = `<option value="">Fahrer auswählen</option>` + athletes.map((athlete) =>
    `<option value="${athlete.name}" ${index === place - 1 ? "" : ""}>${athlete.name} · ${athlete.country}</option>`
  ).join("");
  return select;
});

document.querySelector("#leaderboard-list").innerHTML = leaders.map((leader, index) => `
  <li>
    <span class="rank">${index + 1}</span>
    <span class="avatar" style="background:${leader.color}">${leader.initials}</span>
    <span class="person"><strong>${leader.name}</strong><span>${leader.detail}</span></span>
    <span class="score">${leader.points} <small>Pkt.</small></span>
  </li>
`).join("");

document.querySelector("#race-list").innerHTML = races.map((race) => `
  <article class="race-card">
    <div class="race-card-top"><span class="race-date">${race.date}</span><span class="status">Offen</span></div>
    <div class="location"><span class="flag flag-${race.flag}" aria-hidden="true"></span><div><strong>${race.place}</strong><span>${race.country}</span></div></div>
    <div class="race-card-bottom"><span>${race.type} · ${race.deadline}</span><button type="button" data-race="${race.place}">Tippen →</button></div>
  </article>
`).join("");

const formMessage = document.querySelector("#form-message");
const toast = document.querySelector("#toast");

document.querySelector("#save-prediction").addEventListener("click", () => {
  const values = picks.map((select) => select.value);
  const complete = values.every(Boolean);
  const unique = new Set(values).size === values.length;

  if (!complete) {
    formMessage.textContent = "Bitte besetze alle drei Plätze.";
    formMessage.classList.add("error");
    return;
  }
  if (!unique) {
    formMessage.textContent = "Jeder Fahrer darf nur einmal gewählt werden.";
    formMessage.classList.add("error");
    return;
  }

  formMessage.textContent = "Dein Demo Tipp ist für dieses Rennen gespeichert.";
  formMessage.classList.remove("error");
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2600);
});

picks.forEach((select) => select.addEventListener("change", () => {
  formMessage.textContent = "Du kannst deinen Tipp bis zum Tippende ändern.";
  formMessage.classList.remove("error");
}));

document.querySelectorAll("[data-race]").forEach((button) => button.addEventListener("click", () => {
  document.querySelector("#tipp").scrollIntoView({ behavior: "smooth" });
  formMessage.textContent = `${button.dataset.race} ist im MVP noch mit denselben Demo Fahrern verknüpft.`;
}));

let remainingMinutes = 2 * 24 * 60 + 14 * 60 + 37;
window.setInterval(() => {
  remainingMinutes = Math.max(0, remainingMinutes - 1);
  document.querySelector("#days").textContent = String(Math.floor(remainingMinutes / 1440)).padStart(2, "0");
  document.querySelector("#hours").textContent = String(Math.floor((remainingMinutes % 1440) / 60)).padStart(2, "0");
  document.querySelector("#minutes").textContent = String(remainingMinutes % 60).padStart(2, "0");
}, 60_000);
