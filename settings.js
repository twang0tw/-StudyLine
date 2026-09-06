const token = localStorage.getItem("studyline_auth_token");
const userCacheKey = "studyline_auth_user";
const headers = { "Content-Type": "application/json", ...(token ? { "X-User-Token": token } : {}) };
const api = async (path, options = {}) => { const response = await fetch(path, { ...options, headers: { ...headers, ...(options.headers || {}) }, body: options.body ? JSON.stringify(options.body) : undefined }); const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Request failed"); return data; };
const form = document.querySelector("#profileForm");
async function load() {
  if (!token) { document.querySelector(".settings-card").innerHTML = '<h3>Sign in required</h3><p class="muted">Please sign in before opening settings.</p>'; return; }
  try { const { user } = await api("/api/auth/me"); document.querySelector("#name").value = user.name || ""; document.querySelector("#email").value = user.email || ""; document.querySelector("#roles").textContent = `Roles: ${(user.roles || []).join(", ") || "student"}`; document.querySelector("#settingsUser").textContent = user.name || user.email; const p = user.preferences || {}; document.querySelector("#emailNotifications").checked = !!p.emailNotifications; document.querySelector("#compactMode").checked = !!p.compactMode; localStorage.setItem(userCacheKey, JSON.stringify(user)); } catch (error) { document.querySelector("#saveMessage").textContent = error.message; }
}
form.addEventListener("submit", async (event) => { event.preventDefault(); const message = document.querySelector("#saveMessage"); message.textContent = "Saving…"; try { const { user } = await api("/api/auth/profile", { method: "PATCH", body: { name: document.querySelector("#name").value, preferences: { emailNotifications: document.querySelector("#emailNotifications").checked, compactMode: document.querySelector("#compactMode").checked } } }); localStorage.setItem(userCacheKey, JSON.stringify(user)); document.querySelector("#settingsUser").textContent = user.name; message.textContent = "Saved"; } catch (error) { message.textContent = error.message; } });
load();
