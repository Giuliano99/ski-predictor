let user = null;

async function request(url, options = {}) {
  if (options.method && options.method !== "GET" && user?.csrfToken) options.headers = { ...(options.headers || {}), "X-CSRF-Token":user.csrfToken };
  const response = await fetch(url, options); let body = {};
  try { body = await response.json(); } catch { body = {}; }
  if (response.status === 401 || response.status === 403) { window.location.replace(`/login/?next=${encodeURIComponent(window.location.pathname)}`); throw new Error("Bitte anmelden."); }
  if (!response.ok) throw new Error(body.error?.message || `Fehler ${response.status}`);
  return body;
}

request("/api/v1/auth/me").then((identity) => { user = identity.user; });
