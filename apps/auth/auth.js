const params = new URLSearchParams(window.location.search);
const requestedNext = params.get("next") || "/tippspiel/";
const nextUrl = requestedNext.startsWith("/spielleiter/") || requestedNext.startsWith("/tippspiel/") ? requestedNext : "/tippspiel/";
const message = document.querySelector("#message");
const loginForm = document.querySelector("#login-form");
const registerForm = document.querySelector("#register-form");

document.querySelectorAll("[data-tab]").forEach((button) => button.addEventListener("click", () => {
  const register = button.dataset.tab === "register";
  document.querySelectorAll("[data-tab]").forEach((item) => item.classList.toggle("active", item === button));
  loginForm.hidden = register;
  registerForm.hidden = !register;
  message.textContent = "";
}));

async function submit(form, endpoint) {
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  message.textContent = "Bitte warten ...";
  try {
    const payload = Object.fromEntries(new FormData(form));
    const response = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error?.message || "Die Anmeldung ist fehlgeschlagen.");
    if (nextUrl.startsWith("/spielleiter/") && body.user?.role !== "GAME_MASTER") {
      throw new Error("Dieses Konto hat keinen Spielleiterzugriff.");
    }
    window.location.replace(nextUrl);
  } catch (error) {
    message.textContent = error.message;
    button.disabled = false;
  }
}

loginForm.addEventListener("submit", (event) => { event.preventDefault(); submit(loginForm, "/api/v1/auth/login"); });
registerForm.addEventListener("submit", (event) => { event.preventDefault(); submit(registerForm, "/api/v1/auth/register"); });
