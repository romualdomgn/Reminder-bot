const state = {
  tab: "reminders",
  userSubtab: "all_access",
  bootstrap: null,
  reminders: [],
  usersData: null,
  renderToken: 0,
  abortCtrl: null,
};

const RECURRENCE_OPTIONS = [
  ["once", "1️⃣ Один раз"],
  ["daily", "🔁 Каждый день"],
  ["weekly", "🔁 Раз в неделю"],
  ["biweekly", "🔁 Каждые две недели"],
  ["monthly", "🔁 Ежемесячно"],
  ["yearly", "🔁 Ежегодно"],
];

function pad2(n) {
  return String(n).padStart(2, "0");
}

function getUserNowParts() {
  const offsetMins = Number(state.bootstrap?.now?.offset_minutes ?? 0);
  const shiftedMs = Date.now() + offsetMins * 60 * 1000;
  const d = new Date(shiftedMs);
  return {
    ms: shiftedMs,
    isoDate: d.toISOString().slice(0, 10),
    hour: d.getUTCHours(),
    minute: d.getUTCMinutes(),
    hhmm: `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`,
  };
}

function addMinutesToUserNow(minutes) {
  const now = getUserNowParts();
  const target = new Date(now.ms + minutes * 60 * 1000);
  return {
    date: target.toISOString().slice(0, 10),
    time: `${pad2(target.getUTCHours())}:${pad2(target.getUTCMinutes())}`,
  };
}

function addDaysIso(baseIso, days) {
  const [y, m, d] = baseIso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + days));
  return dt.toISOString().slice(0, 10);
}

function addMonthsIso(baseIso, months) {
  const [y, m, d] = baseIso.split("-").map(Number);
  const target = new Date(Date.UTC(y, m - 1 + months, 1));
  const lastDay = new Date(Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0)).getUTCDate();
  target.setUTCDate(Math.min(d, lastDay));
  return target.toISOString().slice(0, 10);
}

function formatInfoBodyHtml(rawText) {
  const escaped = escapeHtml(rawText);
  return escaped.replace(
    /(https?:\/\/[^\s<]+)|(^|[\s(])@([a-zA-Z0-9_]{3,32})\b/g,
    (_match, url, prefix, username) => {
      if (url) {
        const cleanUrl = url.replace(/[.,!?;:)]+$/, "");
        const trail = url.slice(cleanUrl.length);
        return `<a href="${cleanUrl}" class="info-link" data-ext-url="${cleanUrl}" target="_blank" rel="noopener noreferrer">${cleanUrl}</a>${trail}`;
      }
      const tgUrl = `https://t.me/${username}`;
      return `${prefix}<a href="${tgUrl}" class="info-link" data-tg-url="${tgUrl}" target="_blank" rel="noopener noreferrer">@${username}</a>`;
    }
  );
}

function bindSpoilerToggles(container) {
  container.querySelectorAll("tg-spoiler").forEach((sp) => {
    sp.onclick = () => sp.classList.toggle("revealed");
  });
}

function isTokenActive(token) {
  return token === undefined || token === state.renderToken;
}

async function refreshBootstrap(signal = undefined) {
  const data = await apiRequest("/api/bootstrap", signal ? { signal } : {});
  state.bootstrap = data;
  document.getElementById("clockLine").textContent = `Сейчас ${data.now.time}, ${data.now.date_ru}`;
  document.getElementById("tzLine").textContent = data.now.tz_label;

  const badge = document.getElementById("notifBadge");
  const count = data.counts.notifications || 0;
  badge.textContent = String(count);
  badge.classList.toggle("hidden", count === 0);
}

async function renderCurrentTab() {
  if (state.abortCtrl) {
    state.abortCtrl.abort();
  }
  const ctrl = new AbortController();
  state.abortCtrl = ctrl;
  const token = ++state.renderToken;
  const targetTab = state.tab;

  const content = document.getElementById("content");
  content.innerHTML = '<div class="empty">Загрузка…</div>';
  try {
    await refreshBootstrap(ctrl.signal);
    if (!isTokenActive(token) || state.tab !== targetTab) return;

    if (targetTab === "reminders") await renderReminders(ctrl.signal, token);
    else if (targetTab === "notifications") await renderNotifications(ctrl.signal, token);
    else if (targetTab === "users") await renderUsers(ctrl.signal, token);
    else if (targetTab === "settings") await renderSettings(ctrl.signal, token);
    else if (targetTab === "info") await renderInfo(ctrl.signal, token);
  } catch (err) {
    if (err?.name === "AbortError" || !isTokenActive(token)) return;
    const title = err?.status === 401 || err?.status === 403 ? "Доступ ограничен" : "Ошибка загрузки";
    content.innerHTML = `<div class="card"><b>${title}</b><div class="card-text">${escapeHtml(err.message)}</div></div>`;
  }
}

async function renderReminders(signal = undefined, token = undefined) {
  const data = await apiRequest("/api/reminders", signal ? { signal } : {});
  if (!isTokenActive(token)) return;

  const content = document.getElementById("content");
  const parts = ['<button id="createRemBtn" class="btn full">➕ Создать напоминание</button>'];

  if (!data.groups.length) {
    parts.push('<div class="empty">У вас пока нет активных напоминаний.</div>');
  } else {
    for (const grp of data.groups) {
      if (grp.title) parts.push(`<div class="group-title">${escapeHtml(grp.title)}</div>`);
      for (const item of grp.items) {
        const rec = item.recurrence_label ? `<div class="card-rec">${escapeHtml(item.recurrence_label)}</div>` : "";
        const bodyHtml = item.text_html || escapeHtml(item.text);
        parts.push(`
          <div class="card" data-rem-id="${item.id}">
            <div class="card-head">
              <div>
                <div class="card-dt">${escapeHtml(item.dt_label)}</div>
                ${rec}
              </div>
              <div class="card-actions">
                <button class="icon-btn js-edit-rem" data-id="${item.id}" title="Редактировать">✏️</button>
                <button class="icon-btn js-del-rem" data-id="${item.id}" title="Удалить">🗑</button>
              </div>
            </div>
            <div class="card-text">${bodyHtml}</div>
          </div>
        `);
      }
    }
  }

  content.innerHTML = parts.join("");
  bindSpoilerToggles(content);
  const flatItems = data.groups.flatMap((g) => g.items);
  state.reminders = flatItems;

  document.getElementById("createRemBtn").onclick = () => openReminderModal(null);
  content.querySelectorAll(".js-edit-rem").forEach((btn) => {
    btn.onclick = () => {
      const rem = flatItems.find((x) => x.id === Number(btn.dataset.id));
      if (rem) openReminderModal(rem);
    };
  });
  content.querySelectorAll(".js-del-rem").forEach((btn) => {
    let deleting = false;
    btn.onclick = async () => {
      if (deleting) return;
      deleting = true;
      btn.disabled = true;
      try {
        await apiRequest(`/api/reminders/${btn.dataset.id}`, { method: "DELETE" });
        await renderCurrentTab();
        showToast("Напоминание удалено", "↩️ Отменить", async () => {
          await apiRequest("/api/reminders/undo", { method: "POST" });
          await renderCurrentTab();
          showToast("Удаление отменено");
        }, 6000);
      } catch (err) {
        showToast(err.message);
        if (document.body.contains(btn)) btn.disabled = false;
      } finally {
        deleting = false;
      }
    };
  });
}

function openReminderModal(rem, prefillHtml = "") {
  const isEdit = Boolean(rem);
  const nowParts = getUserNowParts();
  const todayIso = nowParts.isoDate;
  const defDate = isEdit ? rem.date : state.bootstrap.quick_default.date;
  const defTime = isEdit ? rem.time : state.bootstrap.quick_default.time;
  const defRec = isEdit ? rem.recurrence : "once";
  const defHtml = isEdit ? (rem.text_html || escapeHtml(rem.text)) : prefillHtml;
  const showEveningChip = nowParts.hour < 19;

  const recOpts = RECURRENCE_OPTIONS.map(
    ([val, lbl]) => `<option value="${val}" ${val === defRec ? "selected" : ""}>${lbl}</option>`
  ).join("");

  const eveningBtnHtml = showEveningChip
    ? '<button type="button" class="chip" data-qtime="evening">🌆 Сегодня вечером</button>'
    : "";

  openModal(`
    <div class="modal-title">${isEdit ? "✏️ Редактирование напоминания" : "➕ Новое напоминание"}</div>
    <label>Текст напоминания</label>
    <div id="remToolbar" class="rte-toolbar">
      <button type="button" class="rte-btn" data-fmt="bold" title="Жирный"><b>B</b></button>
      <button type="button" class="rte-btn" data-fmt="italic" title="Курсив"><i>I</i></button>
      <button type="button" class="rte-btn" data-fmt="underline" title="Подчёркнутый"><u>U</u></button>
      <button type="button" class="rte-btn" data-fmt="strikeThrough" title="Зачёркнутый"><s>S</s></button>
      <button type="button" class="rte-btn" data-fmt="code" title="Моноширинный">&lt;/&gt;</button>
      <button type="button" class="rte-btn" data-fmt="spoiler" title="Спойлер">🙈</button>
      <button type="button" class="rte-btn" data-fmt="clear" title="Очистить стиль">Tₓ</button>
    </div>
    <div id="remEditor" class="rte-editor" contenteditable="true" data-placeholder="Что нужно напомнить?"></div>
    <label>Быстрый выбор времени</label>
    <div class="chips" id="quickTimeChips">
      <button type="button" class="chip" data-qtime="15m">⏱ Через 15 мин</button>
      <button type="button" class="chip" data-qtime="1h">⏱ Через час</button>
      ${eveningBtnHtml}
      <button type="button" class="chip" data-qtime="morning">🌅 Завтра утром</button>
    </div>
    <label>Быстрый выбор даты</label>
    <div class="chips">
      <button type="button" class="chip" data-qdate="today">Сегодня</button>
      <button type="button" class="chip" data-qdate="1d">Завтра</button>
      <button type="button" class="chip" data-qdate="1w">Неделя</button>
      <button type="button" class="chip" data-qdate="1m">Месяц</button>
      <button type="button" class="chip" data-qdate="1y">Год</button>
    </div>
    <div class="grid2">
      <div>
        <label>Дата</label>
        <input id="remDate" type="date" min="${todayIso}" value="${defDate}" />
      </div>
      <div>
        <label>Время</label>
        <input id="remTime" type="time" value="${defTime}" />
      </div>
    </div>
    <label>Периодичность</label>
    <select id="remRec">${recOpts}</select>
    <div class="row-actions" style="margin-top:14px">
      <button id="saveRemBtn" class="btn" style="flex:1">Сохранить</button>
      <button id="cancelModalBtn" class="btn secondary">Отмена</button>
    </div>
  `);

  const editorApi = initRichTextEditor("remEditor", "remToolbar", defHtml);
  if (editorApi && typeof editorApi.destroy === "function") {
    setModalCleanup(() => editorApi.destroy());
  }
  document.getElementById("cancelModalBtn").onclick = closeModal;

  const qdateChips = Array.from(document.querySelectorAll("[data-qdate]"));
  const qtimeChips = Array.from(document.querySelectorAll("[data-qtime]"));
  const dateInput = document.getElementById("remDate");
  const timeInput = document.getElementById("remTime");

  const quickDatesMap = {
    today: state.bootstrap.quick_default.date,
    "1d": addDaysIso(todayIso, 1),
    "1w": addDaysIso(todayIso, 7),
    "1m": addMonthsIso(todayIso, 1),
    "1y": addMonthsIso(todayIso, 12),
  };

  function setActiveQuickChip(activeCode) {
    qdateChips.forEach((chip) => {
      chip.classList.toggle("active-blue", chip.dataset.qdate === activeCode);
    });
  }

  function setActiveQuickTimeChip(activeCode) {
    qtimeChips.forEach((chip) => {
      chip.classList.toggle("active-blue", chip.dataset.qtime === activeCode);
    });
  }

  qtimeChips.forEach((chip) => {
    chip.onclick = () => {
      const code = chip.dataset.qtime;
      const freshNow = getUserNowParts();
      dateInput.min = freshNow.isoDate;

      let chosenDate = freshNow.isoDate;
      let chosenTime = "15:00";

      if (code === "15m") {
        const res = addMinutesToUserNow(15);
        chosenDate = res.date;
        chosenTime = res.time;
      } else if (code === "1h") {
        const res = addMinutesToUserNow(60);
        chosenDate = res.date;
        chosenTime = res.time;
      } else if (code === "evening") {
        if (freshNow.hour >= 19) {
          chip.classList.add("hidden");
          setActiveQuickTimeChip("");
          showToast("Время 19:00 сегодня уже прошло");
          return;
        }
        chosenDate = freshNow.isoDate;
        chosenTime = "19:00";
      } else if (code === "morning") {
        chosenDate = addDaysIso(freshNow.isoDate, 1);
        chosenTime = "09:00";
      }

      dateInput.value = chosenDate;
      timeInput.value = chosenTime;
      setActiveQuickTimeChip(code);
      setActiveQuickChip("");
    };
  });

  qdateChips.forEach((chip) => {
    chip.onclick = () => {
      const code = chip.dataset.qdate;
      setActiveQuickChip(code);
      setActiveQuickTimeChip("");
      if (code === "today") {
        dateInput.value = state.bootstrap.quick_default.date;
        timeInput.value = state.bootstrap.quick_default.time;
      } else {
        dateInput.value = quickDatesMap[code];
        timeInput.value = "15:00";
      }
    };
  });

  dateInput.addEventListener("input", () => {
    setActiveQuickTimeChip("");
    const matched = Object.entries(quickDatesMap).find(([, iso]) => iso === dateInput.value);
    setActiveQuickChip(matched ? matched[0] : "");
  });

  timeInput.addEventListener("input", () => {
    setActiveQuickTimeChip("");
  });

  const saveBtn = document.getElementById("saveRemBtn");
  let saving = false;
  saveBtn.onclick = async () => {
    if (saving) return;
    const plain = editorApi ? editorApi.getPlainText() : "";
    const text = editorApi ? editorApi.getHtml() : "";
    const date = dateInput.value;
    const time = timeInput.value;
    const recurrence = document.getElementById("remRec").value;
    if (!plain || !text) return showToast("Введите текст напоминания");
    if (!date || !time) return showToast("Укажите дату и время");

    saving = true;
    saveBtn.disabled = true;
    saveBtn.textContent = "Сохранение…";
    try {
      if (isEdit) {
        await apiRequest(`/api/reminders/${rem.id}`, {
          method: "PATCH",
          body: JSON.stringify({ text, date, time, recurrence }),
        });
        showToast("Напоминание обновлено");
      } else {
        await apiRequest("/api/reminders", {
          method: "POST",
          body: JSON.stringify({ text, date, time, recurrence }),
        });
        showToast("Напоминание создано");
      }
      closeModal();
      state.tab = "reminders";
      syncActiveTabUI();
      await renderCurrentTab();
    } catch (err) {
      showToast(err.message);
    } finally {
      saving = false;
      if (document.body.contains(saveBtn)) {
        saveBtn.disabled = false;
        saveBtn.textContent = "Сохранить";
      }
    }
  };
}

async function renderNotifications(signal = undefined, token = undefined) {
  const data = await apiRequest("/api/notifications", signal ? { signal } : {});
  if (!isTokenActive(token)) return;

  const content = document.getElementById("content");
  if (!data.items.length) {
    content.innerHTML = '<div class="empty">Нет непрочитанных уведомлений.</div>';
    return;
  }

  content.innerHTML = data.items.map((n) => `
    <div class="card" data-notif-card="${n.id}">
      ${n.recurrence_label ? `<div class="card-rec">${escapeHtml(n.recurrence_label)}</div>` : ""}
      <div class="card-text">${n.text_html || escapeHtml(n.text)}</div>
      <div class="row-actions">
        <button class="btn small secondary js-n-repeat" data-id="${n.id}">🔁 Повторить</button>
        <button class="btn small secondary js-n-snooze-toggle" data-id="${n.id}">⏳ Отложить</button>
        <button class="btn small secondary js-n-ack" data-id="${n.id}">✅ Прочитано</button>
      </div>
      <div id="snooze-${n.id}" class="chips hidden" style="margin-top:8px">
        <button class="chip js-n-snooze" data-id="${n.id}" data-int="5m">5 мин</button>
        <button class="chip js-n-snooze" data-id="${n.id}" data-int="30m">30 мин</button>
        <button class="chip js-n-snooze" data-id="${n.id}" data-int="1h">1 час</button>
        <button class="chip js-n-snooze" data-id="${n.id}" data-int="1d">1 день</button>
      </div>
    </div>
  `).join("");
  bindSpoilerToggles(content);

  content.querySelectorAll(".js-n-snooze-toggle").forEach((b) => {
    b.onclick = () => {
      const panel = document.getElementById(`snooze-${b.dataset.id}`);
      const isNowHidden = panel.classList.toggle("hidden");
      b.classList.toggle("active-blue", !isNowHidden);
    };
  });

  content.querySelectorAll(".js-n-ack").forEach((b) => {
    b.onclick = async () => {
      const card = b.closest(".card");
      const actionBtns = card ? Array.from(card.querySelectorAll(".row-actions button")) : [b];
      actionBtns.forEach((btn) => {
        btn.classList.toggle("active-blue", btn === b);
        btn.disabled = true;
      });
      try {
        await Promise.all([
          apiRequest(`/api/notifications/${b.dataset.id}/ack`, { method: "POST" }),
          new Promise((resolve) => setTimeout(resolve, 250)),
        ]);
        showToast("Прочитано");
        await renderCurrentTab();
      } catch (err) {
        actionBtns.forEach((btn) => {
          btn.classList.remove("active-blue");
          btn.disabled = false;
        });
        showToast(err.message);
      }
    };
  });

  content.querySelectorAll(".js-n-snooze").forEach((b) => {
    b.onclick = async () => {
      const group = document.getElementById(`snooze-${b.dataset.id}`);
      const buttons = group ? Array.from(group.querySelectorAll(".js-n-snooze")) : [b];
      buttons.forEach((btn) => {
        btn.classList.toggle("active-blue", btn === b);
        btn.disabled = true;
      });
      try {
        const [res] = await Promise.all([
          apiRequest(`/api/notifications/${b.dataset.id}/snooze`, {
            method: "POST",
            body: JSON.stringify({ interval: b.dataset.int }),
          }),
          new Promise((resolve) => setTimeout(resolve, 250)),
        ]);
        showToast(`Отложено на ${res.label}`);
        await renderCurrentTab();
      } catch (err) {
        buttons.forEach((btn) => {
          btn.classList.remove("active-blue");
          btn.disabled = false;
        });
        showToast(err.message);
      }
    };
  });

  content.querySelectorAll(".js-n-repeat").forEach((b) => {
    b.onclick = async () => {
      const card = b.closest(".card");
      const actionBtns = card ? Array.from(card.querySelectorAll(".row-actions button")) : [b];
      actionBtns.forEach((btn) => {
        btn.classList.toggle("active-blue", btn === b);
        btn.disabled = true;
      });
      try {
        const [res] = await Promise.all([
          apiRequest(`/api/notifications/${b.dataset.id}/repeat`, { method: "POST" }),
          new Promise((resolve) => setTimeout(resolve, 250)),
        ]);
        await refreshBootstrap();
        openReminderModal(null, res.text_html || escapeHtml(res.text));
      } catch (err) {
        actionBtns.forEach((btn) => {
          btn.classList.remove("active-blue");
          btn.disabled = false;
        });
        showToast(err.message);
      }
    };
  });
}

function renderUsersView(data) {
  const isAdmin = Boolean(data.is_admin);
  const list = isAdmin ? (data[state.userSubtab] || []) : (data.invited_users || []);
  const content = document.getElementById("content");

  const emptyText = isAdmin
    ? "Список пуст."
    : "Вы пока не добавили других пользователей.";

  const listHtml = !list.length
    ? `<div class="empty">${emptyText}</div>`
    : list.map((u, idx) => `
      <div class="card">
        <div class="card-head">
          <div>
            <div><b>${idx + 1}. ${escapeHtml(u.name)}</b> ${u.is_admin ? "👑" : ""}</div>
            <div class="card-rec">ID: ${u.user_id}${u.created_at ? ` • ${escapeHtml(u.created_at)}` : ""}</div>
            ${u.invited_by ? `<div class="card-rec">Добавил: ${escapeHtml(u.inviter_name || u.invited_by)}</div>` : ""}
          </div>
          <div class="card-actions">
            <button class="icon-btn js-u-edit" data-id="${u.user_id}" data-name="${escapeHtml(u.name)}" title="Переименовать">✏️</button>
            ${u.is_admin ? "" : `<button class="icon-btn js-u-del" data-id="${u.user_id}" data-name="${escapeHtml(u.name)}" title="Удалить">🗑</button>`}
          </div>
        </div>
      </div>
    `).join("");

  const headerBlock = isAdmin
    ? `
      <div class="subtabs">
        <button class="subtab ${state.userSubtab === "all_access" ? "active" : ""}" data-sub="all_access">Все (${data.all_access.length})</button>
        <button class="subtab ${state.userSubtab === "my_users" ? "active" : ""}" data-sub="my_users">Мои (${data.my_users.length})</button>
        <button class="subtab ${state.userSubtab === "other_users" ? "active" : ""}" data-sub="other_users">От других (${data.other_users.length})</button>
      </div>
    `
    : `<div class="group-title">Добавленные вами пользователи (${list.length})</div>`;

  content.innerHTML = `
    <button id="addUserBtn" class="btn full">➕ Добавить нового пользователя</button>
    ${headerBlock}
    ${listHtml}
  `;

  content.querySelectorAll(".subtab").forEach((b) => {
    b.onclick = () => {
      state.userSubtab = b.dataset.sub;
      renderUsersView(data);
    };
  });

  document.getElementById("addUserBtn").onclick = () => {
    openModal(`
      <div class="modal-title">➕ Добавить пользователя</div>
      <label>Telegram ID (только цифры, узнать в @userinfobot)</label>
      <input id="newUserId" type="number" inputmode="numeric" placeholder="123456789" />
      <label>Имя пользователя</label>
      <input id="newUserName" type="text" maxlength="100" placeholder="Иван" />
      <div class="row-actions" style="margin-top:14px">
        <button id="saveUserBtn" class="btn" style="flex:1">Добавить</button>
        <button id="cancelModalBtn" class="btn secondary">Отмена</button>
      </div>
    `);
    document.getElementById("cancelModalBtn").onclick = closeModal;
    const saveUserBtn = document.getElementById("saveUserBtn");
    let submitting = false;
    saveUserBtn.onclick = async () => {
      if (submitting) return;
      const uid = Number(document.getElementById("newUserId").value);
      const name = document.getElementById("newUserName").value.trim();
      if (!uid || uid <= 0 || !name) return showToast("Заполните ID и имя");
      submitting = true;
      saveUserBtn.disabled = true;
      try {
        await apiRequest("/api/users", { method: "POST", body: JSON.stringify({ user_id: uid, name }) });
        closeModal();
        showToast("Пользователь добавлен");
        await renderCurrentTab();
      } catch (err) {
        showToast(err.message);
      } finally {
        submitting = false;
        if (document.body.contains(saveUserBtn)) saveUserBtn.disabled = false;
      }
    };
  };

  content.querySelectorAll(".js-u-edit").forEach((b) => {
    b.onclick = () => {
      openModal(`
        <div class="modal-title">✏️ Изменить имя</div>
        <label>Новое имя для ID ${b.dataset.id}</label>
        <input id="editUserName" type="text" maxlength="100" value="${escapeHtml(b.dataset.name)}" />
        <div class="row-actions" style="margin-top:14px">
          <button id="saveRenameBtn" class="btn" style="flex:1">Сохранить</button>
          <button id="cancelModalBtn" class="btn secondary">Отмена</button>
        </div>
      `);
      document.getElementById("cancelModalBtn").onclick = closeModal;
      const saveRenameBtn = document.getElementById("saveRenameBtn");
      let submitting = false;
      saveRenameBtn.onclick = async () => {
        if (submitting) return;
        const name = document.getElementById("editUserName").value.trim();
        if (!name) return showToast("Введите имя");
        submitting = true;
        saveRenameBtn.disabled = true;
        try {
          await apiRequest(`/api/users/${b.dataset.id}`, {
            method: "PATCH",
            body: JSON.stringify({ name }),
          });
          closeModal();
          showToast("Имя обновлено");
          await renderCurrentTab();
        } catch (err) {
          showToast(err.message);
        } finally {
          submitting = false;
          if (document.body.contains(saveRenameBtn)) saveRenameBtn.disabled = false;
        }
      };
    };
  });

  content.querySelectorAll(".js-u-del").forEach((b) => {
    b.onclick = () => {
      openModal(`
        <div class="modal-title">🗑 Удалить пользователя?</div>
        <div class="card-text"><b>${escapeHtml(b.dataset.name)}</b> (ID: ${b.dataset.id}) потеряет доступ к боту.</div>
        <div class="row-actions" style="margin-top:14px">
          <button id="confirmDelUserBtn" class="btn danger" style="flex:1">Удалить</button>
          <button id="cancelModalBtn" class="btn secondary">Отмена</button>
        </div>
      `);
      document.getElementById("cancelModalBtn").onclick = closeModal;
      const confirmBtn = document.getElementById("confirmDelUserBtn");
      let submitting = false;
      confirmBtn.onclick = async () => {
        if (submitting) return;
        submitting = true;
        confirmBtn.disabled = true;
        try {
          await apiRequest(`/api/users/${b.dataset.id}`, { method: "DELETE" });
          closeModal();
          showToast("Пользователь удалён");
          await renderCurrentTab();
        } catch (err) {
          showToast(err.message);
        } finally {
          submitting = false;
          if (document.body.contains(confirmBtn)) confirmBtn.disabled = false;
        }
      };
    };
  });
}

async function renderUsers(signal = undefined, token = undefined) {
  const data = await apiRequest("/api/users", signal ? { signal } : {});
  if (!isTokenActive(token)) return;
  state.usersData = data;
  renderUsersView(data);
}

async function renderSettings(signal = undefined, token = undefined) {
  const data = await apiRequest("/api/settings", signal ? { signal } : {});
  if (!isTokenActive(token)) return;

  const content = document.getElementById("content");
  const chips = data.presets.map((p) => `
    <button class="chip js-tz-btn ${p.offset_minutes === data.offset_minutes ? "active" : ""}" data-mins="${p.offset_minutes}">
      ${escapeHtml(p.label)}
    </button>
  `).join("");

  content.innerHTML = `
    <div class="card">
      <div class="card-dt">🕒 Текущее время бота</div>
      <div class="card-text">${escapeHtml(data.current_dt)} — ${escapeHtml(data.tz_label)}</div>
      <div class="row-actions">
        <button id="autoTzBtn" class="btn small" style="flex:1">📱 Взять пояс с устройства</button>
      </div>
    </div>
    <div class="card">
      <div class="card-dt">Синхронизация по времени устройства</div>
      <label>Введите текущее время (ЧЧ:ММ)</label>
      <div class="grid2">
        <input id="manualTimeInput" type="time" />
        <button id="manualTimeBtn" class="btn">Применить</button>
      </div>
    </div>
    <div class="card">
      <div class="card-dt">Часовые пояса</div>
      <div class="chips">${chips}</div>
    </div>
  `;

  let tzUpdating = false;
  async function submitTzUpdate(payload, successMsg, triggerBtn) {
    if (tzUpdating) return;
    tzUpdating = true;
    if (triggerBtn) triggerBtn.disabled = true;
    try {
      await apiRequest("/api/settings/tz", { method: "POST", body: JSON.stringify(payload) });
      showToast(successMsg);
      await renderCurrentTab();
    } catch (err) {
      showToast(err.message);
    } finally {
      tzUpdating = false;
      if (triggerBtn && document.body.contains(triggerBtn)) triggerBtn.disabled = false;
    }
  }

  const autoTzBtn = document.getElementById("autoTzBtn");
  autoTzBtn.onclick = () => {
    const offsetMinutes = -new Date().getTimezoneOffset();
    submitTzUpdate({ offset_minutes: offsetMinutes }, "Часовой пояс синхронизирован с устройством", autoTzBtn);
  };

  const manualTimeBtn = document.getElementById("manualTimeBtn");
  manualTimeBtn.onclick = () => {
    const val = document.getElementById("manualTimeInput").value;
    if (!val) return showToast("Укажите время ЧЧ:ММ");
    submitTzUpdate({ device_time: val }, "Время обновлено", manualTimeBtn);
  };

  content.querySelectorAll(".js-tz-btn").forEach((b) => {
    b.onclick = () => {
      submitTzUpdate({ offset_minutes: Number(b.dataset.mins) }, "Часовой пояс обновлён", b);
    };
  });
}

async function renderInfo(signal = undefined, token = undefined) {
  const data = await apiRequest("/api/info", signal ? { signal } : {});
  if (!isTokenActive(token)) return;

  const content = document.getElementById("content");
  content.innerHTML = data.cards.map((c) => `
    <div class="card">
      <div class="card-dt">${escapeHtml(c.title)}</div>
      <div class="card-text">${formatInfoBodyHtml(c.body)}</div>
    </div>
  `).join("");

  content.querySelectorAll(".info-link").forEach((link) => {
    link.onclick = (e) => {
      if (!tg) return;
      e.preventDefault();
      if (link.dataset.tgUrl && typeof tg.openTelegramLink === "function") {
        tg.openTelegramLink(link.dataset.tgUrl);
      } else if (link.dataset.extUrl && typeof tg.openLink === "function") {
        tg.openLink(link.dataset.extUrl);
      } else {
        window.open(link.href, "_blank", "noopener,noreferrer");
      }
    };
  });
}

function syncActiveTabUI() {
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.tab === state.tab);
  });
}

document.querySelectorAll(".tab").forEach((t) => {
  t.onclick = () => {
    state.tab = t.dataset.tab;
    syncActiveTabUI();
    renderCurrentTab();
  };
});

document.getElementById("refreshBtn").onclick = () => renderCurrentTab();

renderCurrentTab();
