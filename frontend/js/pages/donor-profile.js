import { api } from "../api-client.js";
import { guard, initAppShell, updateUser } from "../auth.js";
import {
  bloodLabel,
  faDate,
  faNum,
  formatPhoneForDisplay,
  RH_LABELS,
} from "../utils.js";
import { clearFormErrors, setButtonLoading, showFieldErrors, toast } from "../ui.js";

const user = guard("donor");
if (user) {
  initAppShell();
  init();
}

const form = document.querySelector("#profile-form");
const consents = { sms_consent: true, location_consent: true };
let me = null;

async function init() {
  try {
    const { data } = await api.get("/users/me");
    me = data;
    updateUser(me);
    populate();
  } catch (error) {
    toast(error.message || "دریافت پروفایل ناموفق بود.", { type: "error" });
  }
}

function profilePercent(profile) {
  const checks = [profile.blood_group, profile.rh_factor, profile.last_donation_date, profile.sms_consent];
  return Math.round((checks.filter(Boolean).length / checks.length) * 100);
}

function populate() {
  const profile = me?.donor_profile;
  if (!profile) return;

  form.querySelectorAll('input[name="blood_group"]').forEach((input) => {
    input.checked = input.value === profile.blood_group;
  });
  form.querySelectorAll('input[name="rh_factor"]').forEach((input) => {
    input.checked = input.value === profile.rh_factor;
  });

  const lastDonation = document.querySelector("#last-donation");
  lastDonation.value = profile.last_donation_date ? String(profile.last_donation_date).slice(0, 10) : "";
  lastDonation.max = new Date().toISOString().slice(0, 10);

  consents.sms_consent = Boolean(profile.sms_consent);
  consents.location_consent = Boolean(profile.location_consent);
  form.querySelectorAll("[data-consent]").forEach((button) => {
    button.setAttribute("aria-checked", String(consents[button.dataset.consent]));
  });

  renderSummary(profile);
  updatePhones();
}

function renderSummary(profile) {
  const blood = bloodLabel(profile.blood_group, profile.rh_factor);
  const percent = profilePercent(profile);

  document.querySelectorAll("[data-summary-blood]").forEach((el) => (el.textContent = blood));
  const rh = document.querySelector("[data-summary-rh]");
  if (rh) rh.textContent = RH_LABELS[profile.rh_factor] ?? "—";
  const last = document.querySelector("[data-summary-last]");
  if (last) last.textContent = faDate(profile.last_donation_date) || "ثبت نشده";
  const sms = document.querySelector("[data-summary-sms]");
  if (sms) sms.textContent = profile.sms_consent ? "فعال" : "غیرفعال";
  const location = document.querySelector("[data-summary-location]");
  if (location) location.textContent = profile.location_consent ? "فعال" : "غیرفعال";

  const ring = document.querySelector("[data-profile-ring]");
  if (ring) ring.style.setProperty("--p", percent);
  const percentText = document.querySelector("[data-profile-percent]");
  if (percentText) percentText.textContent = `${faNum(percent)}٪`;
  const completion = document.querySelector("[data-completion-text]");
  if (completion) {
    completion.textContent =
      percent === 100
        ? "همه‌ی اطلاعات لازم برای دریافت فراخوان ثبت شده است."
        : "برای دریافت فراخوان دقیق‌تر، اطلاعات خونی و رضایت‌ها را کامل کنید.";
  }

  const verified = document.querySelector("[data-verified-note]");
  const verifiedText = document.querySelector("[data-verified-text]");
  if (verified) verified.classList.toggle("verified-note--wait", !profile.blood_type_verified);
  if (verifiedText) {
    verifiedText.textContent = profile.blood_type_verified ? "گروه خونی تأییدشده" : "در انتظار تأیید مرکز";
  }
}

function updatePhones() {
  const phone = formatPhoneForDisplay(me?.phone || user?.phone);
  document.querySelectorAll("[data-user-phone]").forEach((el) => (el.textContent = phone));
}

form.querySelectorAll("[data-consent]").forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.dataset.consent;
    consents[key] = !consents[key];
    button.setAttribute("aria-checked", String(consents[key]));
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearFormErrors(form);

  const data = new FormData(form);
  const bloodGroup = data.get("blood_group");
  const rhFactor = data.get("rh_factor");
  const details = [];

  if (!bloodGroup) details.push({ field: "blood_group", message: "گروه خونی را انتخاب کنید." });
  if (!rhFactor) details.push({ field: "rh_factor", message: "عامل Rh را انتخاب کنید." });
  if (details.length) {
    showFieldErrors(form, details);
    return;
  }

  const payload = {
    blood_group: bloodGroup,
    rh_factor: rhFactor,
    last_donation_date: data.get("last_donation_date") || null,
    sms_consent: consents.sms_consent,
    location_consent: consents.location_consent,
  };

  const button = form.querySelector("button[type=submit]");
  setButtonLoading(button, true, "در حال ذخیره…");
  try {
    const { data: updated } = await api.patch("/donors/me/profile", payload);
    me.donor_profile = { ...me.donor_profile, ...updated };
    updateUser({ donor_profile: me.donor_profile });
    renderSummary(me.donor_profile);
    toast("اطلاعات پروفایل شما با موفقیت ذخیره شد.", { title: "ذخیره شد" });
  } catch (error) {
    if (error.details?.length) showFieldErrors(form, error.details);
    else toast(error.message || "ذخیره تغییرات ناموفق بود.", { type: "error" });
  } finally {
    setButtonLoading(button, false);
  }
});
