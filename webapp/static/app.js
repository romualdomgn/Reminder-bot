const state = {
  tab: "reminders",
  userSubtab: "all_access",
  bootstrap: null,
  reminders: [],
};

const RECURRENCE_OPTIONS = [
  ["once", "Один раз"],
  ["daily", "🔁 Каждый день"],
  ["weekly", "🔁 Раз в неделю"],
  ["biweekly", "🔁 Каждые две недели"],
  ["monthly", "🔁 Ежемесячно"],
  ["yearly", "🔁 Ежегодно"],
];

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

async function refreshBootstrap() {
  const data = await apiRequest("/api/bootstrap");
  state.bootstrap = data;
  document.getElementById("clockLine").textContent = `Сейчас ${data.now.time}, ${data.now.date_ru}`;
  document.getElementById("tzLine").textContent = data.now.tz_label;

  const badge = document.getElementById("notifBadge");
  const count = data.counts.notifications || 0;
  badge.textContent = String(count);
  badge.classList.toggle("hidden", count === 0);
}

async function renderCurrentTab() {
  const content = document.getElementById("content");
  content.innerHTML = '<div class="empty">Загрузка…</div>';
  try {
    await refreshBootstrap();
    if (state.tab === "reminders") await renderReminders();
    else if (state.tab === "notifications") await renderNotifications();
    else if (state.tab === "users") await renderUsers();
    else if (state.tab === "settings") await renderSettings();
    else if (state.tab === "info") await renderInfo();
  } catch (err) {
    content.innerHTML = `<div class="card"><b>Доступ ограничен</b><div class="card-text">${escapeHtml(err.message)}</div></div>`;
  }
}

async function renderReminders() {
  const data = await apiRequest("/api/reminders");
  const content = document.getElementById("content");
  const parts = ['<button id="createRemBtn" class="btn full">➕ Создать напоминание</button>'];

  if (!data.groups.length) {
    parts.push('<div class="empty">У вас пока нет активных напоминаний.</div>');
  } else {
    for (const grp of data.groups) {
      if (grp.title) parts.push(`<div class="group-title">${escapeHtml(grp.title)}</div>`);
      for (const item of grp.items) {
        const rec = item.recurrence_label ? `<div class="card-rec">${escapeHtml(item.recurrence_label)}</div>` : "";
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
            <div class="card-text">${escapeHtml(item.text)}</div>
          </div>
        `);
      }
    }
  }

  content.innerHTML = parts.join("");
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
    btn.onclick = async () => {
      try {
        await apiRequest(`/api/reminders/${btn.dataset.id}`, { method: "DELETE" });
        await renderReminders();
        await refreshBootstrap();
        showToast("Напоминание удалено", "↩️ Отменить", async () => {
          await apiRequest("/api/reminders/undo", { method: "POST" });
          await renderReminders();
          await refreshBootstrap();
          showToast("Удаление отменено");
        }, 6000);
      } catch (err) {
        showToast(err.message);
      }
    };
  });
}

function openReminderModal(rem, prefillText = "") {
  const isEdit = Boolean(rem);
  const todayIso = state.bootstrap.now.iso_date;
  const defDate = isEdit ? rem.date : state.bootstrap.quick_default.date;
  const defTime = isEdit ? rem.time : state.bootstrap.quick_default.time;
  const defRec = isEdit ? rem.recurrence : "once";
  const defText = isEdit ? rem.text : prefillText;

  const recOpts = RECURRENCE_OPTIONS.map(
    ([val, lbl]) => `<option value="${val}" ${val === defRec ? "selected" : ""}>${lbl}</option>`
  ).join("");

  openModal(`
    <div class="modal-title">${isEdit ? "✏️ Редактирование напоминания" : "➕ Новое напоминание"}</div>
    <label>Текст напоминания</label>
    <textarea id="remText" placeholder="Что нужно напомнить?">${escapeHtml(defText)}</textarea>
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

  document.getElementById("cancelModalBtn").onclick = closeModal;
  document.querySelectorAll("[data-qdate]").forEach((chip) => {
    chip.onclick = () => {
      const code = chip.dataset.qdate;
      const dateInput = document.getElementById("remDate");
      const timeInput = document.getElementById("remTime");
      if (code === "today") {
        dateInput.value = state.bootstrap.quick_default.date;
        timeInput.value = state.bootstrap.quick_default.time;
      } else {
        dateInput.value =
          code === "1d" ? addDaysIso(todayIso, 1) :
          code === "1w" ? addDaysIso(todayIso, 7) :
          code === "1m" ? addMonthsIso(todayIso, 1) :
          addMonthsIso(todayIso, 12);
        timeInput.value = "15:00";
      }
    };
  });

  document.getElementById("saveRemBtn").onclick = async () => {
    const text = document.getElementById("remText").value.trim();
    const date = document.getElementById("remDate").value;
    const time = document.getElementById("remTime").value;
    const recurrence = document.getElementById("remRec").value;
    if (!text) return showToast("Введите текст напоминания");

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
    }
  };
}

async function renderNotifications() {
  const data = await apiRequest("/api/notifications");
  const content = document.getElementById("content");
  if (!data.items.length) {
    content.innerHTML = '<div class="empty">Нет непрочитанных уведомлений.</div>';
    return;
  }

  content.innerHTML = data.items.map((n) => `
    <div class="card">
      ${n.recurrence_label ? `<div class="card-rec">${escapeHtml(n.recurrence_label)}</div>` : ""}
      <div class="card-text">${escapeHtml(n.text)}</div>
      <div class="row-actions">
        <button class="btn small secondary js-n-repeat" data-id="${n.id}">🔁 Повторить</button>
        <button class="btn small secondary js-n-snooze-toggle" data-id="${n.id}">⏳ Отложить</button>
        <button class="btn small js-n-ack" data-id="${n.id}">✅ Прочитано</button>
      </div>
      <div id="snooze-${n.id}" class="chips hidden" style="margin-top:8px">
        <button class="chip js-n-snooze" data-id="${n.id}" data-int="5m">5 мин</button>
        <button class="chip js-n-snooze" data-id="${n.id}" data-int="30m">30 мин</button>
        <button class="chip js-n-snooze" data-id="${n.id}" data-int="1h">1 час</button>
        <button class="chip js-n-snooze" data-id="${n.id}" data-int="1d">1 день</button>
      </div>
    </div>
  `).join("");

  content.querySelectorAll(".js-n-snooze-toggle").forEach((b) => {
    b.onclick = () => document.getElementById(`snooze-${b.dataset.id}`).classList.toggle("hidden");
  });
  content.querySelectorAll(".js-n-ack").forEach((b) => {
    b.onclick = async () => {
      await apiRequest(`/api/notifications/${b.dataset.id}/ack`, { method: "POST" });
      showToast("Прочитано");
      await renderCurrentTab();
    };
  });
  content.querySelectorAll(".js-n-snooze").forEach((b) => {
    b.onclick = async () => {
      const res = await apiRequest(`/api/notifications/${b.dataset.id}/snooze`, {
        method: "POST",
        body: JSON.stringify({ interval: b.dataset.int }),
      });
      showToast(`Отложено на ${res.label}`);
      await renderCurrentTab();
    };
  });
  content.querySelectorAll(".js-n-repeat").forEach((b) => {
    b.onclick = async () => {
      const res = await apiRequest(`/api/notifications/${b.dataset.id}/repeat`, { method: "POST" });
      await refreshBootstrap();
      openReminderModal(null, res.text);
    };
  });
}

async function renderUsers() {
  const data = await apiRequest("/api/users");
  const list = data[state.userSubtab] || [];
  const content = document.getElementById("content");

  const listHtml = !list.length
    ? '<div class="empty">Список пуст.</div>'
    : list.map((u, idx) => `
      <div class="card">
        <div class="card-head">
          <div>
            <div><b>${idx + 1}. ${escapeHtml(u.name)}</b> ${u.is_admin ? "👑" : ""}</div>
            <div class="card-rec">ID: ${u.user_id} • ${escapeHtml(u.created_at)}</div>
            ${u.invited_by ? `<div class="card-rec">Добавил: ${escapeHtml(u.inviter_name || u.invited_by)}</div>` : ""}
          </div>
          <div class="card-actions">
            <button class="icon-btn js-u-edit" data-id="${u.user_id}" data-name="${escapeHtml(u.name)}">✏️</button>
            ${u.is_admin ? "" : `<button class="icon-btn js-u-del" data-id="${u.user_id}" data-name="${escapeHtml(u.name)}">🗑</button>`}
          </div>
        </div>
      </div>
    `).join("");

  content.innerHTML = `
    <button id="addUserBtn" class="btn full">➕ Добавить нового пользователя</button>
    <div class="subtabs">
      <button class="subtab ${state.userSubtab === "all_access" ? "active" : ""}" data-sub="all_access">Все (${data.all_access.length})</button>
      <button class="subtab ${state.userSubtab === "my_users" ? "active" : ""}" data-sub="my_users">Мои (${data.my_users.length})</button>
      <button class="subtab ${state.userSubtab === "other_users" ? "active" : ""}" data-sub="other_users">От других (${data.other_users.length})</button>
    </div>
    ${listHtml}
  `;

  content.querySelectorAll(".subtab").forEach((b) => {
    b.onclick = () => {
      state.userSubtab = b.dataset.sub;
      renderUsers();
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
    document.getElementById("saveUserBtn").onclick = async () => {
      const uid = Number(document.getElementById("newUserId").value);
      const name = document.getElementById("newUserName").value.trim();
      if (!uid || !name) return showToast("Заполните ID и имя");
      try {
        await apiRequest("/api/users", { method: "POST", body: JSON.stringify({ user_id: uid, name }) });
        closeModal();
        showToast("Пользователь добавлен");
        await renderUsers();
      } catch (err) {
        showToast(err.message);
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
      document.getElementById("saveRenameBtn").onclick = async () => {
        const name = document.getElementById("editUserName").value.trim();
        if (!name) return showToast("Введите имя");
        await apiRequest(`/api/users/${b.dataset.id}`, { method: "PATCH", body: JSON.stringify({ name }) });
        closeModal();
        showToast("Имя обновлено");
        await renderUsers();
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
      document.getElementById("confirmDelUserBtn").onclick = async () => {
        await apiRequest(`/api/users/${b.dataset.id}`, { method: "DELETE" });
        closeModal();
        showToast("Пользователь удалён");
        await renderUsers();
      };
    };
  });
}

async function renderSettings() {
  const data = await apiRequest("/api/settings");
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

  document.getElementById("autoTzBtn").onclick = async () => {
    const offsetMinutes = -new Date().getTimezoneOffset();
    await apiRequest("/api/settings/tz", { method: "POST", body: JSON.stringify({ offset_minutes: offsetMinutes }) });
    showToast("Часовой пояс синхронизирован с устройством");
    await renderCurrentTab();
  };

  document.getElementById("manualTimeBtn").onclick = async () => {
    const val = document.getElementById("manualTimeInput").value;
    if (!val) return showToast("Укажите время ЧЧ:ММ");
    await apiRequest("/api/settings/tz", { method: "POST", body: JSON.stringify({ device_time: val }) });
    showToast("Время обновлено");
    await renderCurrentTab();
  };

  content.querySelectorAll(".js-tz-btn").forEach((b) => {
    b.onclick = async () => {
      await apiRequest("/api/settings/tz", {
        method: "POST",
        body: JSON.stringify({ offset_minutes: Number(b.dataset.mins) }),
      });
      showToast("Часовой пояс обновлён");
      await renderCurrentTab();
    };
  });
}

async function renderInfo() {
  const data = await apiRequest("/api/info");
  const content = document.getElementById("content");
  content.innerHTML = data.cards.map((c) => `
    <div class="card">
      <div class="card-dt">${escapeHtml(c.title)}</div>
      <div class="card-text">${escapeHtml(c.body)}</div>
    </div>
  `).join("");
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
