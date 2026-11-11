import { api } from "../api-client.js";
import { guard, initAppShell, updateUser } from "../auth.js";
import {
  bloodLabel,
  componentMeta,
  escapeHtml,
  faDate,
  faDateTime,
  faNum,
  minutesLeft,
  relativeTime,
  remainingLabel,
  statusLabel,
  urgencyMeta,
  ELIGIBILITY_LABELS,
  RESPONSE_LABELS,
} from "../utils.js";
import {
  closeDialog,
  initFilterChips,
  openDialog,
  setButtonLoading,
  toast,
} from "../ui.js";

const user = guard("center_operator");
if (user) initAppShell();

let center = null;
let requests = [];
let state = { filter: "all", search: "", sort: "newest" };
let activeRequestId = null;
let pendingAction = null;

const list = document.querySelector("[data-request-list]");
const emptyState = document.querySelector("[data-request-empty]");
const metaLabel = document.querySelector("[data-request-meta]");
const searchInput = document.querySelector("#request-search");
const sortSelect = document.querySelector("#request-sort");
const bellDot = document.querySelector("[data-bell-dot]");
const drawer = document.querySelector("#request-drawer");
const actionModal = document.querySelector("#request-action-modal");
const candidatesBody = document.querySelector("[data-candidates-body]");
const candidatesEmpty = document.querySelector("[data-candidates-empty]");
const responsesList = document.querySelector("[data-responses-list]");
const responsesEmpty = document.querySelector("[data-responses-empty]");
const drawerActions = document.querySelector("[data-drawer-actions]");
const confirmButton = document.querySelector("[data-action-confirm]");

const svg = (name, cls = "icon") =>
  `<svg class="${cls}" aria-hidden="true"><use href="../assets/icons/sprite.svg#${name}"></use></svg>`;

async function init() {
  await load();
  bindEvents();
  handleDeepLink();
}

async function load({ silent = false } = {}) {
  if (!silent) setListLoading();
  try {
    const meResponse = await api.get("/users/me");
    const requestResponse = await api.get("/blood-requests?page_size=100");
    const me = meResponse.data;
    center = me.center ?? null;
    updateUser(me);
    requests = requestResponse.data ?? [];
    renderCenter();
    renderMetrics();
    renderRequests();
  } catch (error) {
    renderError(error);
  }
}

function renderCenter() {
  if (!center) return;
  document.querySelectorAll("[data-center-name]").forEach((el) => {
    el.textContent = center.name;
  });
  document.title = `داشبورد ${center.name} | هم‌خون`;
}

/* ---------- Metrics ---------- */
function renderMetrics() {
  const active = requests.filter((request) => request.status === "active");
  const pending = active.filter((request) => !request.dispatch_id);
  const interested = requests.reduce((sum, request) => sum + (request.interested_count ?? 0), 0);
  const units = active.reduce((sum, request) => sum + Number(request.units_needed || 0), 0);

  setMetric("active", active.length);
  setMetric("pending", pending.length);
  setMetric("interested", interested);
  setMetric("units", units);

  const hint = document.querySelector('[data-metric-hint="active"]');
  if (hint) hint.textContent = active.length ? `${faNum(active.length)} در جریان` : "در حال پیگیری";
  const pendingHint = document.querySelector('[data-metric-hint="pending"]');
  if (pendingHint) pendingHint.textContent = pending.length ? "نیازمند اقدام" : "همه فراخوان شده";

  if (bellDot) bellDot.hidden = pending.length === 0;
}

function setMetric(name, value) {
  const el = document.querySelector(`[data-metric="${name}"]`);
  if (el) el.textContent = faNum(value);
}

/* ---------- Filters / sorting ---------- */
const MATCHERS = {
  all: () => true,
  active: (request) => request.status === "active",
  draft: (request) => request.status === "draft",
  urgent: (request) =>
    ["urgent", "critical"].includes(request.urgency) &&
    !["cancelled", "expired", "fulfilled"].includes(request.status),
  closed: (request) => ["fulfilled", "cancelled", "expired"].includes(request.status),
};

function matchesSearch(request) {
  if (!state.search) return true;
  const meta = componentMeta(request.component_type);
  const urgency = urgencyMeta(request.urgency);
  const haystack = [
    bloodLabel(request.blood_group, request.rh_factor),
    meta.label,
    request.notes,
    statusLabel(request.status),
    urgency.label,
    request.center?.name,
    request.units_needed,
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(state.search.toLowerCase());
}

function filteredRequests() {
  const items = requests.filter((request) => MATCHERS[state.filter](request) && matchesSearch(request));
  const urgencyRank = { critical: 0, urgent: 1, routine: 2 };
  const sorted = [...items];
  if (state.sort === "urgency") {
    sorted.sort(
      (a, b) =>
        (urgencyRank[a.urgency] ?? 3) - (urgencyRank[b.urgency] ?? 3) ||
        new Date(b.created_at) - new Date(a.created_at),
    );
  } else if (state.sort === "expiry") {
    sorted.sort((a, b) => {
      const closedA = ["fulfilled", "cancelled", "expired"].includes(a.status) ? 1 : 0;
      const closedB = ["fulfilled", "cancelled", "expired"].includes(b.status) ? 1 : 0;
      return closedA - closedB || new Date(a.expires_at) - new Date(b.expires_at);
    });
  } else {
    sorted.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  }
  return sorted;
}

/* ---------- Request cards ---------- */
function renderRequests() {
  if (!list) return;
  const items = filteredRequests();
  renderFilterCounts();

  metaLabel.textContent = `${faNum(items.length)} از ${faNum(requests.length)} درخواست`;

  if (!items.length) {
    list.innerHTML = "";
    list.hidden = true;
    emptyState.hidden = false;
    return;
  }

  list.hidden = false;
  emptyState.hidden = true;
  list.innerHTML = items.map(requestCard).join("");
}

function renderFilterCounts() {
  Object.entries(MATCHERS).forEach(([key, matcher]) => {
    const el = document.querySelector(`[data-filter-count="${key}"]`);
    if (el) el.textContent = faNum(requests.filter(matcher).length);
  });
}

function requestCard(request) {
  const meta = componentMeta(request.component_type);
  const urgency = urgencyMeta(request.urgency);
  const blood = bloodLabel(request.blood_group, request.rh_factor);
  const isLive = ["active", "draft"].includes(request.status);
  const left = minutesLeft(request.expires_at);
  const deadline = isLive
    ? `<span class="countdown${left <= 30 ? " is-near" : ""}" data-card-expiry="${request.expires_at}">${svg("i-clock")}${remainingLabel(request.expires_at)}</span>`
    : `<span class="tiny muted">${request.status === "fulfilled" ? faDate(request.expires_at, true) : "پایان‌یافته"}</span>`;

  const quickAction =
    request.status === "draft"
      ? `<button class="btn btn--soft" type="button" data-quick-action="activate" data-id="${request.id}">${svg("i-play")}<span class="btn__label">فعال‌سازی</span></button>`
      : request.status === "active" && !request.dispatch_id
        ? `<button class="btn btn--primary" type="button" data-quick-action="dispatch" data-id="${request.id}">${svg("i-send")}<span class="btn__label">فراخوان</span></button>`
        : "";

  return `
    <article class="request-card" data-request-card="${request.id}">
      <div class="request-card__main">
        <span class="blood-badge${request.status === "active" ? "" : " blood-badge--quiet"}">${escapeHtml(blood)}</span>
        <div class="request-card__heading">
          <div>
            <div class="request-card__title">${escapeHtml(meta.label)} ${escapeHtml(blood)}</div>
            <div class="request-card__sub">
              <span class="status-pill status-pill--${request.status}">${escapeHtml(statusLabel(request.status))}</span>
              ${request.dispatch_id ? `<span class="tag tag--success">فراخوان آغاز شده</span>` : ""}
              <span>${svg("i-clock")}${escapeHtml(relativeTime(request.created_at))}</span>
            </div>
          </div>
          <span class="tag ${urgency.tag}">${urgency.label}</span>
        </div>
      </div>

      <div class="fact">
        <span class="fact__label">تعداد مورد نیاز</span>
        <span class="fact__value fact__value--num">${faNum(request.units_needed)} واحد</span>
      </div>

      <div class="fact">
        <span class="fact__label">مهلت پاسخ</span>
        <span class="fact__value">${deadline}</span>
      </div>

      <div class="fact">
        <span class="fact__label">پاسخ / کاندید</span>
        <span class="fact__value fact__value--num">${faNum(request.interested_count ?? 0)} / ${faNum(request.candidates_count ?? 0)}</span>
      </div>

      <div class="request-card__actions">
        <button class="btn btn--ghost" type="button" data-open-request="${request.id}">
          ${svg("i-arrow-left")}<span class="btn__label">جزئیات</span>
        </button>
        ${quickAction}
      </div>
    </article>
  `;
}

/* ---------- Drawer ---------- */
function findRequest(id) {
  return requests.find((request) => request.id === id) ?? null;
}

async function openDrawer(request) {
  activeRequestId = request.id;
  renderDrawer(request);
  openDialog(drawer);
  await loadDrawerPanels(request);
}

function renderDrawer(request) {
  const meta = componentMeta(request.component_type);
  const urgency = urgencyMeta(request.urgency);
  const blood = bloodLabel(request.blood_group, request.rh_factor);

  document.querySelector("[data-drawer-badge]").textContent = blood;
  document.querySelector("[data-drawer-title]").textContent = `${meta.label} ${blood}`;
  document.querySelector("[data-drawer-tags]").innerHTML = `
    <span class="status-pill status-pill--${request.status}">${escapeHtml(statusLabel(request.status))}</span>
    <span class="tag ${urgency.tag}">${urgency.label}</span>
  `;
  document.querySelector("[data-drawer-sub]").textContent =
    `ثبت ${relativeTime(request.created_at)} · ${center?.name ?? "مرکز اهدای خون"}`;

  document.querySelector("[data-drawer-summary]").innerHTML = `
    <div class="drawer-summary__item"><span>فرآورده</span><b>${escapeHtml(meta.label)}</b></div>
    <div class="drawer-summary__item"><span>تعداد مورد نیاز</span><b>${faNum(request.units_needed)} واحد</b></div>
    <div class="drawer-summary__item"><span>مهلت پاسخ</span><b>${escapeHtml(remainingLabel(request.expires_at))}</b></div>
    <div class="drawer-summary__item"><span>پاسخ مثبت</span><b>${faNum(request.interested_count ?? 0)} داوطلب</b></div>
  `;

  renderTimeline(request);
  renderDrawerNotes(request);
  renderDrawerActions(request);
}

function renderTimeline(request) {
  const closed = ["fulfilled", "cancelled", "expired"].includes(request.status);
  const steps = [
    {
      label: "ثبت درخواست",
      time: request.created_at,
      done: true,
      current: false,
    },
    {
      label: "فعال‌سازی",
      time: request.activated_at,
      done: Boolean(request.activated_at),
      current: request.status === "draft",
    },
    {
      label: "فراخوان داوطلبان",
      time: request.dispatched_at,
      done: Boolean(request.dispatched_at),
      current: request.status === "active" && !request.dispatch_id,
    },
    {
      label: request.status === "fulfilled" ? "تأمین و تکمیل" : closed ? "پایان درخواست" : "پاسخ و پیگیری",
      time: null,
      done: request.status === "fulfilled",
      current: request.status === "active" && Boolean(request.dispatch_id),
      hint:
        request.status === "active" && request.dispatch_id
          ? "در حال دریافت پاسخ"
          : request.status === "fulfilled"
            ? "درخواست تأمین شد"
            : closed
              ? "پایان‌یافته"
              : null,
    },
  ];

  document.querySelector("[data-drawer-timeline]").innerHTML = steps
    .map((step, index) => {
      const className = step.done ? "is-done" : step.current ? "is-current" : "";
      const dot = step.done
        ? svg("i-check")
        : `<span>${faNum(index + 1)}</span>`;
      return `
        <div class="timeline__step ${className}">
          <span class="timeline__dot">${dot}</span>
          <b>${step.label}</b>
          <span>${step.time ? escapeHtml(faDateTime(step.time)) : step.hint ?? (step.current ? "در انتظار اقدام" : "—")}</span>
        </div>
      `;
    })
    .join("");
}

function renderDrawerNotes(request) {
  document.querySelector("[data-drawer-notes]").innerHTML = `
    ${svg("i-info")}
    <div>
      <b>یادداشت مرکز</b>
      <p>${request.notes ? escapeHtml(request.notes) : "برای این درخواست یادداشتی ثبت نشده است."}</p>
    </div>
  `;
}

function renderDrawerActions(request) {
  const cancel = ["draft", "active"].includes(request.status)
    ? `<button class="btn btn--ghost" type="button" data-drawer-action="cancel">${svg("i-x")}<span class="btn__label">لغو درخواست</span></button>`
    : "";

  if (request.status === "draft") {
    drawerActions.innerHTML = `
      <button class="btn btn--primary" type="button" data-drawer-action="activate">${svg("i-play")}<span class="btn__label">فعال‌سازی درخواست</span></button>
      ${cancel}
    `;
  } else if (request.status === "active" && !request.dispatch_id) {
    drawerActions.innerHTML = `
      <button class="btn btn--primary" type="button" data-drawer-action="dispatch">${svg("i-send")}<span class="btn__label">آغاز فراخوان</span></button>
      ${cancel}
    `;
  } else if (request.status === "active") {
    drawerActions.innerHTML = `
      <span class="drawer-state">${svg("i-check")} فراخوان در جریان است؛ پاسخ‌ها را از تب «پاسخ داوطلبان» ببینید.</span>
      ${cancel}
    `;
  } else {
    drawerActions.innerHTML = `
      <span class="drawer-state">${svg("i-lock")} این درخواست در وضعیت نهایی است و قابل تغییر نیست.</span>
      <button class="btn btn--soft" type="button" data-close-dialog>بستن</button>
    `;
  }
}

async function loadDrawerPanels(request) {
  candidatesBody.innerHTML = `<tr><td colspan="6"><div class="skeleton" style="height: 42px"></div></td></tr>`;
  responsesList.innerHTML = `<div class="skeleton" style="height: 54px; margin-block-end: 0.5rem"></div><div class="skeleton" style="height: 54px"></div>`;
  candidatesEmpty.hidden = true;
  responsesEmpty.hidden = true;
  setDrawerTab("candidates");

  try {
    const [candidateResponse, responseResponse] = await Promise.all([
      api.get(`/blood-requests/${request.id}/candidates`),
      api.get(`/blood-requests/${request.id}/responses`),
    ]);
    const candidates = candidateResponse.data ?? [];
    const responses = responseResponse.data ?? [];

    renderCandidates(candidates, request);
    renderResponses(responses);

    document.querySelector('[data-drawer-tab="candidates"]').textContent = `کاندیدها (${faNum(candidates.length)})`;
    document.querySelector('[data-drawer-tab="responses"]').textContent = `پاسخ داوطلبان (${faNum(responses.length)})`;
  } catch (error) {
    candidatesBody.innerHTML = "";
    responsesList.innerHTML = "";
    candidatesEmpty.hidden = false;
    candidatesEmpty.textContent = error.message || "دریافت کاندیدها ممکن نشد.";
  }
}

function renderCandidates(candidates, request) {
  if (!candidates.length) {
    candidatesBody.innerHTML = "";
    candidatesEmpty.hidden = false;
    candidatesEmpty.textContent = request.dispatch_id
      ? "برای این فراخوان، کاندیدی ثبت نشده است."
      : "هنوز فراخوانی آغاز نشده است؛ پس از آغاز فراخوان، نزدیک‌ترین داوطلبان اینجا فهرست می‌شوند.";
    return;
  }

  candidatesEmpty.hidden = true;
  candidatesBody.innerHTML = candidates
    .map((candidate) => {
      const verified = candidate.eligibility_check_status === "verified_data";
      const firstBatch = candidate.dispatch_stage === "first_batch";
      return `
        <tr>
          <td><span class="rank-badge">${faNum(candidate.rank)}</span></td>
          <td>
            <span class="donor-ref">
              <span class="avatar avatar--sm avatar--ink"><svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#i-user"></use></svg></span>
              ${escapeHtml(candidate.donor_reference)}
            </span>
          </td>
          <td class="fact__value--num">${faNum(candidate.distance_km)} کیلومتر</td>
          <td class="fact__value--num">${faNum(candidate.eta_minutes)} دقیقه</td>
          <td>
            <span class="tag ${verified ? "tag--success" : "tag--amber"}">${ELIGIBILITY_LABELS[candidate.eligibility_check_status] ?? "نیازمند بررسی"}</span>
          </td>
          <td>
            <span class="tag ${firstBatch ? "tag--outline" : "tag--muted"}">${firstBatch ? "دسته اول" : "ذخیره"}</span>
          </td>
        </tr>
      `;
    })
    .join("");
}

function renderResponses(responses) {
  if (!responses.length) {
    responsesList.innerHTML = "";
    responsesEmpty.hidden = false;
    responsesEmpty.textContent = "هنوز پاسخی از داوطلبان ثبت نشده است.";
    return;
  }

  responsesEmpty.hidden = true;
  responsesList.innerHTML = responses
    .map((response) => {
      const interested = response.response === "interested";
      return `
        <div class="response-item">
          <span class="avatar avatar--sm avatar--ink"><svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#i-user"></use></svg></span>
          <div class="response-item__body">
            <div class="response-item__title">
              داوطلب ${escapeHtml(response.donor_reference)}
              <span class="tag ${interested ? "tag--success" : "tag--muted"}">${RESPONSE_LABELS[response.response] ?? response.response}</span>
            </div>
            <div class="response-item__meta">
              پاسخ ${escapeHtml(relativeTime(response.responded_at))}
              ${response.eta_minutes ? ` · زمان رسیدن تقریبی ${faNum(response.eta_minutes)} دقیقه` : ""}
            </div>
          </div>
        </div>
      `;
    })
    .join("");
}

function setDrawerTab(name) {
  document.querySelectorAll("[data-drawer-tab]").forEach((tab) => {
    const active = tab.dataset.drawerTab === name;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-drawer-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.drawerPanel !== name;
  });
}

/* ---------- Actions ---------- */
const ACTION_COPY = {
  activate: {
    eyebrow: "فعال‌سازی درخواست",
    confirm: "بله، فعال شود",
    tone: "primary",
    note: "تا زمان آغاز فراخوان، هیچ پیامی برای داوطلبان ارسال نمی‌شود.",
    desc: "درخواست از حالت پیش‌نویس خارج می‌شود و برای فراخوان داوطلبان آماده خواهد بود.",
  },
  cancel: {
    eyebrow: "لغو درخواست",
    confirm: "بله، لغو شود",
    tone: "danger",
    note: "این عملیات قابل بازگشت نیست. پیام‌های بی‌پاسخ مرتبط با این درخواست نیز لغو می‌شوند.",
    desc: "پیش از لغو، مطمئن شوید نیاز مرکز از مسیر دیگری تأمین شده است.",
  },
  dispatch: {
    eyebrow: "آغاز فراخوان",
    confirm: "آغاز فراخوان",
    tone: "primary",
    note: "پس از آغاز، امکان فراخوان دوباره برای این درخواست وجود ندارد؛ اما پاسخ‌ها همچنان ثبت می‌شوند.",
    desc: "نزدیک‌ترین داوطلبان واجد شرایط بر اساس فاصله و زمان رسیدن انتخاب می‌شوند. دسته اول فوراً پیام می‌گیرد و بقیه به‌عنوان ذخیره می‌مانند.",
  },
};

function openActionModal(request, action) {
  const copy = ACTION_COPY[action];
  if (!copy) return;
  pendingAction = { id: request.id, action };
  const blood = bloodLabel(request.blood_group, request.rh_factor);
  const meta = componentMeta(request.component_type);
  const urgency = urgencyMeta(request.urgency);

  document.querySelector("[data-action-eyebrow]").textContent = copy.eyebrow;
  document.querySelector("[data-action-title]").textContent = `درخواست ${meta.label} ${blood}؟`;
  document.querySelector("[data-action-desc]").textContent = copy.desc;
  document.querySelector("[data-action-note]").innerHTML = `${svg("i-shield")}<span>${copy.note}</span>`;

  document.querySelector("[data-action-preview]").innerHTML = `
    <div class="action-preview__item"><span>گروه خونی</span><b>${escapeHtml(blood)}</b></div>
    <div class="action-preview__item"><span>فرآورده</span><b>${escapeHtml(meta.label)}</b></div>
    <div class="action-preview__item"><span>تعداد</span><b>${faNum(request.units_needed)} واحد</b></div>
    <div class="action-preview__item"><span>فوریت</span><b>${urgency.label}</b></div>
  `;

  confirmButton.classList.toggle("btn--danger", copy.tone === "danger");
  confirmButton.classList.toggle("btn--primary", copy.tone !== "danger");
  confirmButton.querySelector(".btn__label").textContent = copy.confirm;
  openDialog(actionModal);
}

async function executeAction() {
  if (!pendingAction) return;
  const { id, action } = pendingAction;
  const request = findRequest(id);
  setButtonLoading(confirmButton, true, "در حال انجام…");

  try {
    if (action === "dispatch") {
      const response = await api.post(`/blood-requests/${id}/dispatch`);
      const data = response.data;
      if (request) {
        request.dispatch_id = data.dispatch_id;
        request.dispatched_at = new Date().toISOString();
        request.candidate_count = data.candidate_count;
        request.candidates_count = data.candidate_count;
        request.first_batch_size = data.first_batch_size;
      }
      toast(
        `فراخوان برای ${faNum(data.candidate_count)} داوطلب در صف قرار گرفت؛ ${faNum(data.first_batch_size)} نفر اول فوراً پیام می‌گیرند.`,
        { title: "فراخوان آغاز شد" },
      );
    } else if (action === "activate") {
      await api.post(`/blood-requests/${id}/activate`);
      if (request) {
        request.status = "active";
        request.activated_at = new Date().toISOString();
      }
      toast("درخواست فعال شد و آماده فراخوان است.", { title: "درخواست فعال شد" });
    } else if (action === "cancel") {
      await api.post(`/blood-requests/${id}/cancel`);
      if (request) request.status = "cancelled";
      toast("درخواست لغو شد و پیام‌های بی‌پاسخ آن بسته شد.", { title: "درخواست لغو شد" });
    }

    closeDialog(actionModal);
    pendingAction = null;
    renderMetrics();
    renderRequests();

    if (request && (drawer.open || action === "dispatch")) {
      renderDrawer(request);
      if (action === "dispatch") {
        openDrawer(request);
      } else {
        await loadDrawerPanels(request);
      }
    }
  } catch (error) {
    toast(error.message || "انجام این عملیات ممکن نشد.", { type: "error" });
  } finally {
    setButtonLoading(confirmButton, false);
  }
}

/* ---------- Events ---------- */
function bindEvents() {
  initFilterChips(document.querySelector("[data-filter-group]"), (filter) => {
    state.filter = filter;
    renderRequests();
  });

  let searchTimer;
  searchInput?.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.search = searchInput.value.trim();
      renderRequests();
    }, 180);
  });

  sortSelect?.addEventListener("change", () => {
    state.sort = sortSelect.value;
    renderRequests();
  });

  list?.addEventListener("click", (event) => {
    const open = event.target.closest("[data-open-request]");
    if (open) {
      const request = findRequest(open.dataset.openRequest);
      if (request) openDrawer(request);
      return;
    }
    const quick = event.target.closest("[data-quick-action]");
    if (quick) {
      const request = findRequest(quick.dataset.id);
      if (request) openActionModal(request, quick.dataset.quickAction);
    }
  });

  drawerActions?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-drawer-action]");
    if (!button) return;
    const request = findRequest(activeRequestId);
    if (request) openActionModal(request, button.dataset.drawerAction);
  });

  document.querySelector(".drawer-tabs")?.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-drawer-tab]");
    if (tab) setDrawerTab(tab.dataset.drawerTab);
  });

  confirmButton?.addEventListener("click", executeAction);

  document.querySelector("[data-refresh]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setButtonLoading(button, true, "به‌روزرسانی…");
    await load({ silent: true });
    setButtonLoading(button, false);
    toast("فهرست درخواست‌ها به‌روز شد.", { duration: 2400 });
  });

  setInterval(() => {
    document.querySelectorAll("[data-card-expiry]").forEach((el) => {
      el.lastChild.textContent = remainingLabel(el.dataset.cardExpiry);
      el.classList.toggle("is-near", minutesLeft(el.dataset.cardExpiry) <= 30);
    });
  }, 30000);
}

/* ---------- Deep link from request form ---------- */
function handleDeepLink() {
  const params = new URLSearchParams(location.search);
  const highlight = params.get("highlight");
  const created = params.get("created");
  if (!highlight) return;

  history.replaceState(null, "", location.pathname);
  const request = findRequest(highlight);
  if (request) openDrawer(request);
  if (created) {
    toast(
      request?.status === "active"
        ? "درخواست ثبت و فعال شد؛ حالا می‌توانید فراخوان داوطلبان را آغاز کنید."
        : "درخواست به‌صورت پیش‌نویس ثبت شد.",
      { title: "درخواست جدید ثبت شد" },
    );
  }
}

/* ---------- States ---------- */
function setListLoading() {
  if (!list) return;
  list.hidden = false;
  emptyState.hidden = true;
  list.innerHTML = Array.from(
    { length: 3 },
    () => `<div class="skeleton" style="height: 96px; border-radius: 22px"></div>`,
  ).join("");
  metaLabel.textContent = "در حال دریافت…";
}

function renderError(error) {
  if (!list) return;
  list.hidden = true;
  emptyState.hidden = false;
  emptyState.innerHTML = `
    <span class="empty-state__art">${svg("i-alert")}</span>
    <h3>دریافت درخواست‌ها ممکن نشد</h3>
    <p>${escapeHtml(error.message || "ارتباط با سرور برقرار نشد.")}</p>
    <button class="btn btn--soft" type="button" data-retry>تلاش دوباره</button>
  `;
  metaLabel.textContent = "خطا در دریافت";
  emptyState.querySelector("[data-retry]")?.addEventListener("click", () => load());
}

if (user) init();
