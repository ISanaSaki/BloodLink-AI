import { api, ApiError } from "../api-client.js";
import { guard, initAppShell, updateUser } from "../auth.js";
import {
  cacheAvailability,
  cacheDonorProfile,
  getCachedAvailability,
  getCachedDonorProfile,
} from "../backend-state.js";
import {
  componentMeta,
  daysBetween,
  escapeHtml,
  faDate,
  faNum,
  faTime,
  minutesLeft,
  relativeTime,
  remainingLabel,
  urgencyMeta,
  bloodLabel,
  RESPONSE_LABELS,
} from "../utils.js";
import { toast, setButtonLoading } from "../ui.js";

const user = guard("donor");
if (user) {
  initAppShell();
  init();
}

let me = null;
let notifications = [];
let availability = null;

const list = document.querySelector("[data-notification-list]");
const emptyState = document.querySelector("[data-notif-empty]");
const notifMeta = document.querySelector("[data-notif-meta]");
const bellDot = document.querySelector("[data-bell-dot]");
const availCard = document.querySelector("[data-availability-card]");
const availSwitch = document.querySelector("[data-availability-switch]");
const availLabel = document.querySelector("[data-availability-label]");
const availDesc = document.querySelector("[data-availability-desc]");
const availTimes = document.querySelector("[data-availability-times]");
const timeEditor = document.querySelector("[data-time-editor]");
const timeError = document.querySelector("[data-time-error]");
const fromInput = document.querySelector("#available-from");
const untilInput = document.querySelector("#available-until");

async function init() {
  try {
    const [meResponse, notifResponse] = await Promise.all([
      api.get("/users/me"),
      api.get("/notifications"),
    ]);
    me = meResponse.data;
    notifications = notifResponse.data ?? [];
    // The contract has no GET endpoints for these; restore what the user saved earlier.
    me.donor_profile = me.donor_profile ?? getCachedDonorProfile() ?? null;
    me.availability = me.availability ?? getCachedAvailability() ?? null;
    cacheDonorProfile(me.donor_profile);
    cacheAvailability(me.availability);
    updateUser(me);
    renderProfile();
    renderAvailability();
    renderNotifications();
    startClock();
  } catch (error) {
    renderNotificationsError(error);
  }
}

/* ---------- Profile / welcome ---------- */
function renderProfile() {
  const profile = me?.donor_profile ?? null;

  const blood = profile ? bloodLabel(profile.blood_group, profile.rh_factor) : "ثبت نشده";
  document.querySelectorAll("[data-blood-group]").forEach((el) => (el.textContent = blood));
  const eyebrow = document.querySelector("[data-blood-eyebrow]");
  if (eyebrow) eyebrow.textContent = profile ? `گروه خونی ${blood}` : "گروه خونی ثبت نشده";

  const last = document.querySelector("[data-last-donation]");
  if (last) last.textContent = faDate(profile?.last_donation_date) || "ثبت نشده";

  const ago = document.querySelector("[data-last-donation-ago]");
  if (ago) {
    const days = daysBetween(profile?.last_donation_date);
    ago.textContent = days === null ? "آخرین اهدای ثبت‌شده" : `آخرین اهدا، ${faNum(days)} روز پیش`;
  }

  const checks = profile
    ? [profile.blood_group, profile.rh_factor, profile.last_donation_date, profile.sms_consent]
    : [];
  const percent = profile ? Math.round((checks.filter(Boolean).length / checks.length) * 100) : 0;
  const ring = document.querySelector("[data-profile-ring]");
  if (ring) ring.style.setProperty("--p", percent);
  const percentText = document.querySelector("[data-profile-percent]");
  if (percentText) percentText.textContent = `${faNum(percent)}٪`;
}

/* ---------- Availability ---------- */
function renderAvailability() {
  availability = me?.availability ?? null;
  const isAvailable = availability?.status === "available";

  availCard?.classList.toggle("is-available", isAvailable);
  if (availSwitch) {
    availSwitch.setAttribute("aria-checked", String(isAvailable));
    availSwitch.disabled = false;
  }
  if (availLabel) availLabel.textContent = isAvailable ? "آماده‌ی اهدا هستم" : "فعلاً آماده نیستم";
  if (availDesc) {
    availDesc.textContent = isAvailable
      ? "فراخوان‌های هم‌خوان با گروه خونی شما برایتان ارسال می‌شود."
      : "در این بازه فراخوانی برای شما ارسال نمی‌شود؛ هر وقت خواستید دوباره روشن کنید.";
  }
  if (availTimes) {
    availTimes.textContent =
      isAvailable && availability?.available_from && availability?.available_until
        ? `از ${faTime(availability.available_from)} تا ${faTime(availability.available_until)}`
        : "بازه‌ای اعلام نشده";
  }

  if (isAvailable && availability?.available_from) {
    fromInput.value = toTimeValue(availability.available_from);
    untilInput.value = toTimeValue(availability.available_until);
  } else if (!fromInput.value) {
    const now = new Date();
    fromInput.value = toTimeValue(now.toISOString());
    untilInput.value = toTimeValue(new Date(now.getTime() + 4 * 3600 * 1000).toISOString());
  }
}

function toTimeValue(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function timeToIso(value, nextDay = false) {
  const [hours, minutes] = value.split(":").map(Number);
  const date = new Date();
  date.setHours(hours, minutes, 0, 0);
  if (nextDay) date.setDate(date.getDate() + 1);
  return date.toISOString();
}

availSwitch?.addEventListener("click", async () => {
  if (availSwitch.disabled) return;
  const currentStatus = availability?.status === "available" ? "available" : "unavailable";
  const nextStatus = currentStatus === "available" ? "unavailable" : "available";
  availSwitch.disabled = true;
  availSwitch.setAttribute("aria-busy", "true");

  const now = new Date();
  const from = availability?.available_from && new Date(availability.available_from) > now
    ? availability.available_from
    : now.toISOString();
  const until = availability?.available_until && new Date(availability.available_until) > now
    ? availability.available_until
    : new Date(now.getTime() + 4 * 3600 * 1000).toISOString();

  try {
    const { data } = await api.patch("/donors/me/availability", {
      status: nextStatus,
      // The contract rejects time fields for `unavailable`; send them only when available.
      ...(nextStatus === "available" ? { available_from: from, available_until: until } : {}),
    });
    availability = data;
    me.availability = data;
    cacheAvailability(data);
    renderAvailability();
    toast(nextStatus === "available" ? "آمادگی شما فعال شد." : "وضعیت آمادگی موقتاً غیرفعال شد.", {
      title: "وضعیت به‌روزرسانی شد",
    });
  } catch (error) {
    toast(error.message || "به‌روزرسانی وضعیت ناموفق بود.", { type: "error" });
  } finally {
    availSwitch.disabled = false;
    availSwitch.removeAttribute("aria-busy");
  }
});

document.querySelector("[data-edit-times]")?.addEventListener("click", (event) => {
  const open = !timeEditor.classList.contains("is-open");
  timeEditor.classList.toggle("is-open", open);
  event.currentTarget.setAttribute("aria-expanded", String(open));
  if (open) {
    timeEditor.scrollIntoView({ behavior: "smooth", block: "nearest" });
    fromInput.focus();
  }
});

document.querySelector("[data-cancel-times]")?.addEventListener("click", () => {
  timeEditor.classList.remove("is-open");
  document.querySelector("[data-edit-times]")?.setAttribute("aria-expanded", "false");
  timeError.classList.remove("is-visible");
});

timeEditor?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = timeEditor.querySelector("button[type=submit]");
  if (!fromInput.value || !untilInput.value) {
    showTimeError("ساعت شروع و پایان را وارد کنید.");
    return;
  }
  if (fromInput.value === untilInput.value) {
    showTimeError("پایان بازه باید بعد از شروع باشد.");
    return;
  }

  const overnight = untilInput.value < fromInput.value;
  const payload = {
    status: "available",
    available_from: timeToIso(fromInput.value),
    available_until: timeToIso(untilInput.value, overnight),
  };

  setButtonLoading(submit, true, "در حال ذخیره…");
  try {
    const { data } = await api.patch("/donors/me/availability", payload);
    availability = data;
    me.availability = data;
    cacheAvailability(data);
    renderAvailability();
    timeEditor.classList.remove("is-open");
    document.querySelector("[data-edit-times]")?.setAttribute("aria-expanded", "false");
    toast("بازه‌ی آمادگی شما ذخیره شد.");
  } catch (error) {
    if (error.details?.length) showTimeError(error.details[0].message);
    else toast(error.message || "ذخیره بازه ناموفق بود.", { type: "error" });
  } finally {
    setButtonLoading(submit, false);
  }
});

function showTimeError(message) {
  timeError.innerHTML = `<svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#i-alert"></use></svg><span>${escapeHtml(message)}</span>`;
  timeError.classList.add("is-visible");
}

/* ---------- Notifications ---------- */
function renderNotifications() {
  if (!list) return;
  list.hidden = false;

  const active = notifications.filter((item) => item.status !== "cancelled");
  if (!active.length) {
    list.innerHTML = "";
    list.hidden = true;
    emptyState.hidden = false;
    notifMeta.textContent = "بدون فراخوان فعال";
    bellDot.hidden = true;
    return;
  }

  list.innerHTML = active.map(notificationTemplate).join("");
  emptyState.hidden = true;

  const pending = active.filter((item) => !item.response && new Date(item.expires_at) > new Date()).length;
  notifMeta.textContent = pending
    ? `${faNum(pending)} فراخوان در انتظار پاسخ`
    : `${faNum(active.length)} فراخوان ثبت‌شده`;
  bellDot.hidden = pending === 0;
}

function notificationTemplate(notification) {
  const meta = componentMeta(notification.component_type);
  const urgency = urgencyMeta(notification.urgency);
  const blood = bloodLabel(notification.blood_group, notification.rh_factor);
  const answered = Boolean(notification.response);
  const expired = new Date(notification.expires_at) <= new Date();
  const tone = notification.urgency === "critical" ? "critical" : notification.urgency === "urgent" ? "urgent" : "";
  const title = `${notification.urgency === "critical" ? "نیاز فوری" : "فراخوان"} به ${meta.label} ${blood}`;
  const centerName = notification.center_name ?? "مرکز اهدای خون";
  const desc = `${centerName} برای بیماران نیازمند، به ${meta.label} ${blood} نیاز دارد.`;

  const metaItems = [
    `<span><svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#i-pin"></use></svg>${escapeHtml(centerName)}</span>`,
    `<span><svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#i-clock"></use></svg>${escapeHtml(relativeTime(notification.created_at))}</span>`,
  ].join("");

  const footer = answered
    ? `<span class="answered-banner"><svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#i-check"></use></svg>پاسخ شما: ${RESPONSE_LABELS[notification.response.response] ?? notification.response.response}</span>
       <span class="tiny muted">${escapeHtml(relativeTime(notification.response.responded_at))}</span>`
    : expired
      ? `<span class="countdown is-near"><svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#i-clock"></use></svg>مهلت پاسخ تمام شد</span>`
      : `<span class="countdown" data-countdown="${notification.expires_at}"><svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#i-clock"></use></svg>${remainingLabel(notification.expires_at)}</span>
         <div class="notification__actions">
           <button class="btn btn--primary btn--sm" type="button" data-respond="interested" data-id="${notification.id}">
             <svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#i-check"></use></svg>
             <span class="btn__label">می‌توانم شرکت کنم</span>
           </button>
           <button class="btn btn--ghost btn--sm" type="button" data-respond="unavailable" data-id="${notification.id}">
             <span class="btn__label">در دسترس نیستم</span>
           </button>
         </div>`;

  return `
    <article class="notification${tone ? ` notification--${tone}` : ""}${answered ? " is-answered" : ""}" data-notification="${notification.id}">
      <span class="notification__icon">
        <svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#${meta.icon}"></use></svg>
      </span>
      <div>
        <div class="notification__head">
          <span class="notification__title">${escapeHtml(title)}</span>
          <span class="tag ${urgency.tag}">${urgency.label}</span>
        </div>
        <p class="notification__desc">${escapeHtml(desc)}</p>
        <div class="notification__meta">${metaItems}</div>
        <div class="notification__foot">${footer}</div>
      </div>
    </article>
  `;
}

list?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-respond]");
  if (!button) return;

  const id = button.dataset.id;
  const response = button.dataset.respond;
  const card = button.closest("[data-notification]");
  const label = button.querySelector(".btn__label");
  const original = label?.textContent;

  setButtonLoading(button, true, "در حال ثبت…");
  try {
    await api.post(`/notifications/${id}/response`, { response });
    const item = notifications.find((notification) => notification.id === id);
    if (item) {
      item.response = { response, responded_at: new Date().toISOString() };
    }
    card.querySelector(".notification__foot").innerHTML = `
      <span class="answered-banner"><svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#i-check"></use></svg>پاسخ شما: ${RESPONSE_LABELS[response]}</span>
      <span class="tiny muted">همین حالا</span>
    `;
    card.classList.add("is-answered");
    renderNotificationsMeta();
    toast(
      response === "interested"
        ? "پاسخ شما ثبت شد. مرکز اهدای خون برای هماهنگی با شما تماس می‌گیرد."
        : "ممنون که اطلاع دادید. فراخوان بعدی را برایتان می‌فرستیم.",
      { title: "پاسخ ثبت شد" },
    );
  } catch (error) {
    setButtonLoading(button, false);
    if (label && original) label.textContent = original;
    toast(error.message || "ثبت پاسخ ناموفق بود.", { type: "error" });
    if (error instanceof ApiError && error.status === 409) {
      init();
    }
  }
});

function renderNotificationsMeta() {
  const active = notifications.filter((item) => item.status !== "cancelled");
  const pending = active.filter((item) => !item.response && new Date(item.expires_at) > new Date()).length;
  notifMeta.textContent = pending
    ? `${faNum(pending)} فراخوان در انتظار پاسخ`
    : `${faNum(active.length)} فراخوان ثبت‌شده`;
  bellDot.hidden = pending === 0;
}

function renderNotificationsError(error) {
  if (!list) return;
  list.innerHTML = `
    <div class="empty-state">
      <span class="empty-state__art"><svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#i-alert"></use></svg></span>
      <h3>دریافت فراخوان‌ها ممکن نشد</h3>
      <p>${escapeHtml(error.message || "ارتباط با سرور برقرار نشد.")}</p>
      <button class="btn btn--soft" type="button" data-retry>تلاش دوباره</button>
    </div>
  `;
  notifMeta.textContent = "خطا در دریافت";
  list.querySelector("[data-retry]")?.addEventListener("click", () => {
    list.innerHTML = `<div class="skeleton" style="height: 168px; border-radius: 22px"></div>`;
    init();
  });
}

/* ---------- Live countdowns ---------- */
let clockId = 0;

function startClock() {
  clearInterval(clockId);
  clockId = setInterval(() => {
    document.querySelectorAll("[data-countdown]").forEach((el) => {
      const iso = el.dataset.countdown;
      const left = minutesLeft(iso);
      el.lastChild.textContent = remainingLabel(iso);
      el.classList.toggle("is-near", left <= 20);
    });
  }, 30000);
}
