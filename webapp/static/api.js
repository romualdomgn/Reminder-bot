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
  const fetchOpts = { ...options, headers };
  let resp;
  try {
    resp = await fetch(path, fetchOpts);
  } catch (err) {
    if (err && err.name === "AbortError") throw err;
    const netErr = new Error("Ошибка сети. Проверьте подключение и попробуйте снова.");
    netErr.status = 0;
    throw netErr;
  }

  let data = null;
  try {
    data = await resp.json();
  } catch (_) {}

  if (!resp.ok) {
    let msg = `Ошибка сервера (${resp.status})`;
    if (typeof data?.detail === "string" && data.detail) {
      msg = data.detail;
    } else if (Array.isArray(data?.detail) && data.detail.length) {
      msg = data.detail.map((item) => item?.msg || "").filter(Boolean).join("; ") || msg;
    }
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
      btn.disabled = true;
      el.classList.add("hidden");
      try {
        await actionCb();
      } catch (err) {
        showToast(err?.message || "Не удалось выполнить действие");
      }
    };
    el.appendChild(btn);
  }

  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), duration);
}

let modalCleanupFn = null;

function setModalCleanup(fn) {
  modalCleanupFn = typeof fn === "function" ? fn : null;
}

function runModalCleanup() {
  if (modalCleanupFn) {
    try {
      modalCleanupFn();
    } catch (_) {}
    modalCleanupFn = null;
  }
}

function openModal(htmlContent) {
  runModalCleanup();
  const backdrop = document.getElementById("modalBackdrop");
  const card = document.getElementById("modalCard");
  card.innerHTML = htmlContent;
  backdrop.classList.remove("hidden");
}

function closeModal() {
  runModalCleanup();
  document.getElementById("modalBackdrop").classList.add("hidden");
  document.getElementById("modalCard").innerHTML = "";
}

document.getElementById("modalBackdrop").addEventListener("click", (e) => {
  if (e.target.id === "modalBackdrop") closeModal();
});
