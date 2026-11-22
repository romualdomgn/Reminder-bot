const tg = window.Telegram?.WebApp || null;
if (tg) {
  tg.ready();
  tg.expand();
}

function getInitData() {
  return tg?.initData || "";
}

async function apiRequest(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-Telegram-Init-Data": getInitData(),
    ...(options.headers || {}),
  };
  const resp = await fetch(path, { ...options, headers });
  let data = null;
  try {
    data = await resp.json();
  } catch (_) {}

  if (!resp.ok) {
    const msg = data?.detail || `Ошибка сервера (${resp.status})`;
    const err = new Error(msg);
    err.status = resp.status;
    throw err;
  }
  return data;
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

let toastTimer = null;
function showToast(text, actionLabel = "", actionCb = null, duration = 3500) {
  const el = document.getElementById("toast");
  el.innerHTML = "";
  const span = document.createElement("span");
  span.textContent = text;
  el.appendChild(span);

  if (actionLabel && actionCb) {
    const btn = document.createElement("button");
    btn.className = "btn small";
    btn.textContent = actionLabel;
    btn.onclick = async () => {
      el.classList.add("hidden");
      await actionCb();
    };
    el.appendChild(btn);
  }

  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), duration);
}

function openModal(htmlContent) {
  const backdrop = document.getElementById("modalBackdrop");
  const card = document.getElementById("modalCard");
  card.innerHTML = htmlContent;
  backdrop.classList.remove("hidden");
}

function closeModal() {
  document.getElementById("modalBackdrop").classList.add("hidden");
  document.getElementById("modalCard").innerHTML = "";
}

document.getElementById("modalBackdrop").addEventListener("click", (e) => {
  if (e.target.id === "modalBackdrop") closeModal();
});
