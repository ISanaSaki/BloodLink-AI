export const BLOOD_GROUPS = ["A", "B", "AB", "O"];

export const RH_LABELS = {
  positive: "مثبت",
  negative: "منفی",
};

export const COMPONENTS = {
  red_cells: {
    label: "گلبول قرمز",
    short: "گلبول قرمز",
    icon: "i-drop",
    desc: "برای جراحی‌ها و کم‌خونی شدید",
  },
  platelets: {
    label: "پلاکت",
    short: "پلاکت",
    icon: "i-activity",
    desc: "برای بیماران با افت پلاکت",
  },
  plasma: {
    label: "پلاسما",
    short: "پلاسما",
    icon: "i-heart",
    desc: "برای سوختگی و اختلالات انعقادی",
  },
  whole_blood: {
    label: "خون کامل",
    short: "خون کامل",
    icon: "i-hospital",
    desc: "بر اساس نظر مرکز درمانی",
  },
};

export const URGENCY = {
  routine: { label: "معمولی", tag: "tag" },
  urgent: { label: "فوری", tag: "tag--amber" },
  critical: { label: "بحرانی", tag: "tag--coral" },
};

export const REQUEST_STATUS = {
  draft: "پیش‌نویس",
  active: "فعال",
  fulfilled: "تکمیل‌شده",
  cancelled: "لغوشده",
  expired: "منقضی",
};

export const NOTIFICATION_STATUS = {
  queued: "در صف ارسال",
  sent: "ارسال‌شده",
  delivered: "دریافت‌شده",
  failed: "ناموفق",
  cancelled: "لغوشده",
};

export const RESPONSE_LABELS = {
  interested: "می‌توانم شرکت کنم",
  unavailable: "در دسترس نیستم",
};

export const ELIGIBILITY_LABELS = {
  verified_data: "داده تأییدشده",
  needs_review: "نیازمند بررسی",
};

const numberFormatter = new Intl.NumberFormat("fa-IR");
const dateFormatter = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  year: "numeric",
  month: "long",
  day: "numeric",
});
const shortDateFormatter = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  month: "short",
  day: "numeric",
});
const timeFormatter = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  hour: "2-digit",
  minute: "2-digit",
});
const relativeFormatter = new Intl.RelativeTimeFormat("fa", { numeric: "auto" });

export function faNum(value, options = {}) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  if (options.style) {
    return new Intl.NumberFormat("fa-IR", options).format(Number(value));
  }
  return numberFormatter.format(Number(value));
}

export function faDate(iso, short = false) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return (short ? shortDateFormatter : dateFormatter).format(date);
}

export function faDateTime(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return `${dateFormatter.format(date)}، ${timeFormatter.format(date)}`;
}

export function faTime(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return timeFormatter.format(date);
}

export function relativeTime(iso) {
  if (!iso) return "";
  const diff = new Date(iso).getTime() - Date.now();
  const minutes = Math.round(diff / 60000);
  if (Math.abs(minutes) < 60) return relativeFormatter.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return relativeFormatter.format(hours, "hour");
  return relativeFormatter.format(Math.round(hours / 24), "day");
}

export function minutesLeft(iso) {
  if (!iso) return 0;
  return Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 60000));
}

export function remainingLabel(iso) {
  const totalMinutes = minutesLeft(iso);
  if (totalMinutes <= 0) return "پایان‌یافته";
  if (totalMinutes < 60) return `${faNum(totalMinutes)} دقیقه مانده`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (!minutes) return `${faNum(hours)} ساعت مانده`;
  return `${faNum(hours)} ساعت و ${faNum(minutes)} دقیقه مانده`;
}

const faDigits = (value) => String(value).replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);

export function countdownClock(iso) {
  const ms = Math.max(0, new Date(iso).getTime() - Date.now());
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${faDigits(String(minutes).padStart(2, "0"))}:${faDigits(String(seconds).padStart(2, "0"))}`;
}

export function normalizePhone(input) {
  const persian = "۰۱۲۳۴۵۶۷۸۹";
  const arabic = "٠١٢٣٤٥٦٧٨٩";
  const digits = String(input ?? "")
    .replace(/[۰-۹]/g, (d) => persian.indexOf(d))
    .replace(/[٠-٩]/g, (d) => arabic.indexOf(d))
    .replace(/[^\d+]/g, "");
  if (digits.startsWith("+98")) return digits;
  if (digits.startsWith("0098")) return `+98${digits.slice(4)}`;
  if (digits.startsWith("98") && digits.length === 12) return `+${digits}`;
  if (digits.startsWith("0")) return `+98${digits.slice(1)}`;
  if (digits.startsWith("9") && digits.length === 10) return `+98${digits}`;
  return digits;
}

export function isValidIranPhone(input) {
  const phone = normalizePhone(input);
  return /^\+989\d{9}$/.test(phone);
}

export function formatPhoneForDisplay(phone) {
  const normalized = normalizePhone(phone);
  if (!/^\+98\d{10}$/.test(normalized)) return normalized || "—";
  const local = normalized.slice(3);
  return `۰${local.slice(0, 3)} ${local.slice(3, 6)} ${local.slice(6)}`.replace(/\d/g, (d) =>
    "۰۱۲۳۴۵۶۷۸۹"[Number(d)],
  );
}

export function initials(name = "") {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "؟";
  if (parts.length === 1) return parts[0].slice(0, 2);
  return `${parts[0][0]}${parts[1][0]}`;
}

export function bloodLabel(group, rh) {
  if (!group) return "—";
  return `${group}${rh === "negative" ? "−" : "+"}`;
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export function debounce(fn, wait = 220) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function getParam(name, fallback = "") {
  return new URLSearchParams(window.location.search).get(name) ?? fallback;
}

export function toDateTimeInput(date = new Date()) {
  const d = new Date(date);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fromDateTimeInput(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

export function daysBetween(iso) {
  if (!iso) return null;
  const diff = Date.now() - new Date(iso).getTime();
  return Math.max(0, Math.floor(diff / 86400000));
}

export function urgencyMeta(value) {
  return URGENCY[value] ?? URGENCY.routine;
}

export function componentMeta(value) {
  return COMPONENTS[value] ?? COMPONENTS.red_cells;
}

export function statusLabel(value) {
  return REQUEST_STATUS[value] ?? value;
}

export function isRecent(iso, minutes = 30) {
  if (!iso) return false;
  return Date.now() - new Date(iso).getTime() < minutes * 60000;
}
