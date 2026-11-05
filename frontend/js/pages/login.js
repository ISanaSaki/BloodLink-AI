import { api, ApiError, setToken } from "../api-client.js";
import { DEMO_OTP, TOKEN_KEY, USE_MOCK } from "../config.js";
import {
  afterLogin,
  dashboardFor,
  getDemoRole,
  getUser,
  isLoggedIn,
  saveSession,
  setDemoRole,
} from "../auth.js";
import { countdownClock, formatPhoneForDisplay, isValidIranPhone, normalizePhone } from "../utils.js";
import { clearFormErrors, setButtonLoading, showFieldErrors, toast } from "../ui.js";

const PURPOSES = {
  login: {
    eyebrow: "ورود امن",
    title: "به هم‌خون خوش آمدید",
    desc: "شماره موبایل‌تان را وارد کنید؛ کد تأیید کوتاه است و بعد از آن به پنل خودتان می‌روید.",
  },
  register: {
    eyebrow: "ثبت‌نام داوطلب",
    title: "دو دقیقه تا یک تصمیم بزرگ",
    desc: "با شماره موبایل ثبت‌نام کنید؛ بعد از ورود، گروه خونی و آمادگی‌تان را کامل می‌کنید.",
  },
};

const purpose = new URLSearchParams(location.search).get("purpose") === "register" ? "register" : "login";
const copy = PURPOSES[purpose];
document.querySelector("[data-intro-eyebrow]").textContent = copy.eyebrow;
document.querySelector("[data-intro-title]").textContent = copy.title;
document.querySelector("[data-intro-desc]").textContent = copy.desc;

/* Demo block */
const demoBlock = document.querySelector("[data-demo-block]");
const demoHint = document.querySelector("[data-demo-code-hint]");
if (USE_MOCK) {
  demoHint.hidden = false;
  demoHint.innerHTML = `در نسخه نمایشی، کد <b>${DEMO_OTP}</b> را وارد کنید.`;
  document.querySelectorAll("[data-demo-role]").forEach((btn) => {
    const active = btn.dataset.demoRole === getDemoRole();
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-pressed", String(active));
    btn.addEventListener("click", () => {
      setDemoRole(btn.dataset.demoRole);
      document.querySelectorAll("[data-demo-role]").forEach((item) => {
        const isActive = item === btn;
        item.classList.toggle("is-active", isActive);
        item.setAttribute("aria-pressed", String(isActive));
      });
    });
  });
} else {
  demoBlock?.remove();
}

/* Existing session banner */
const sessionNote = document.querySelector("#session-note");
if (sessionNote && isLoggedIn()) {
  const user = getUser();
  sessionNote.hidden = false;
  sessionNote.querySelector("[data-session-name]").textContent = user.name;
  sessionNote.querySelector("[data-session-continue]").href = dashboardFor(user.role);
  sessionNote.querySelector("[data-session-switch]").addEventListener("click", () => {
    setToken(null);
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem("blood_user");
    sessionNote.hidden = true;
    toast("از حساب خارج شدید. شماره دیگری وارد کنید.");
  });
}

/* ---------- Step 1: request OTP ---------- */
const requestForm = document.querySelector("#otp-request-form");
const verifyForm = document.querySelector("#otp-verify-form");
const phoneInput = document.querySelector("#phone");
const phoneField = phoneInput.closest(".field");
const requestButton = requestForm.querySelector("button[type=submit]");

let challengeId = "";
let currentPhone = "";
let deadlineIso = "";
let resendAt = 0;
let timerId = 0;
let submitting = false;

function setPhoneError(message) {
  phoneInput.setAttribute("aria-invalid", "true");
  const error = phoneField.querySelector(".field-error");
  error.innerHTML = `<svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#i-alert"></use></svg><span>${message}</span>`;
  error.classList.add("is-visible");
  phoneInput.focus();
}

const toEnglishDigits = (value) =>
  String(value)
    .replace(/[۰-۹]/g, (digit) => "۰۱۲۳۴۵۶۷۸۹".indexOf(digit))
    .replace(/[٠-٩]/g, (digit) => "٠١٢٣٤٥٦٧٨٩".indexOf(digit));

phoneInput.addEventListener("input", () => {
  let digits = toEnglishDigits(phoneInput.value).replace(/\D/g, "");
  if (digits.startsWith("98") && digits.length === 12) digits = `0${digits.slice(2)}`;
  phoneInput.value = digits.slice(0, 11);
  phoneInput.removeAttribute("aria-invalid");
  phoneField.querySelector(".field-error").classList.remove("is-visible");
});

requestForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearFormErrors(requestForm);
  const phone = normalizePhone(phoneInput.value);
  if (!isValidIranPhone(phone)) {
    setPhoneError("شماره موبایل را به شکل ۰۹۱۲۱۲۳۴۵۶۷ وارد کنید.");
    return;
  }

  setButtonLoading(requestButton, true, "در حال ارسال کد…");
  try {
    const { data } = await api.post("/auth/otp/request", { phone, purpose }, { auth: false });
    challengeId = data.challenge_id;
    currentPhone = phone;
    deadlineIso = new Date(Date.now() + data.expires_in_seconds * 1000).toISOString();
    resendAt = Date.now() + data.resend_after_seconds * 1000;

    document.querySelector("[data-phone-display]").textContent = formatPhoneForDisplay(phone);
    requestForm.hidden = true;
    verifyForm.hidden = false;
    resetOtp();
    startTimer();
    toast("کد تأیید ارسال شد. پیامک‌هایتان را ببینید.", { type: "success" });
    verifyForm.querySelector(".otp-input")?.focus();
  } catch (error) {
    if (error instanceof ApiError && error.details?.length) {
      showFieldErrors(requestForm, error.details);
    } else {
      setPhoneError(error.message || "ارسال کد ناموفق بود. دوباره تلاش کنید.");
    }
    setButtonLoading(requestButton, false);
  }
});

/* ---------- Step 2: verify ---------- */
const otpRow = verifyForm.querySelector("[data-otp-row]");
const otpInputs = [...otpRow.querySelectorAll(".otp-input")];
const otpError = verifyForm.querySelector("#otp-error");
const verifyButton = verifyForm.querySelector("button[type=submit]");
const timerText = verifyForm.querySelector("[data-otp-timer-text]");
const timerBox = verifyForm.querySelector("[data-otp-timer]");
const resendButtons = [...verifyForm.querySelectorAll("[data-resend]")];

function resetOtp() {
  otpInputs.forEach((input) => {
    input.value = "";
    input.classList.remove("is-filled");
    input.removeAttribute("aria-invalid");
  });
  otpError.classList.remove("is-visible");
  otpRow.classList.remove("is-invalid");
}

function otpValue() {
  return otpInputs.map((input) => input.value).join("");
}

function showOtpError(message) {
  otpError.innerHTML = `<svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#i-alert"></use></svg><span>${message}</span>`;
  otpError.classList.add("is-visible");
  otpInputs.forEach((input) => input.setAttribute("aria-invalid", "true"));
  otpRow.classList.remove("is-invalid");
  void otpRow.offsetWidth;
  otpRow.classList.add("is-invalid");
  otpInputs[0]?.focus();
  otpInputs[0]?.select();
}

function startTimer() {
  clearInterval(timerId);
  const tick = () => {
    const remaining = new Date(deadlineIso).getTime() - Date.now();
    timerText.textContent = countdownClock(deadlineIso);
    timerBox.classList.toggle("is-near", remaining < 30000);

    const resendLeft = Math.max(0, Math.ceil((resendAt - Date.now()) / 1000));
    resendButtons.forEach((btn) => {
      btn.disabled = resendLeft > 0;
      const label = btn.querySelector("span");
      if (label) {
        label.textContent = resendLeft > 0 ? `ارسال دوباره تا ${countdownClock(new Date(resendAt).toISOString())}` : "ارسال دوباره کد";
      }
    });

    if (remaining <= 0) {
      clearInterval(timerId);
      timerText.textContent = "۰۰:۰۰";
      verifyButton.disabled = true;
      showOtpError("زمان کد تأیید تمام شد. کد تازه بگیرید.");
    }
  };
  tick();
  timerId = setInterval(tick, 500);
}

otpInputs.forEach((input, index) => {
  input.addEventListener("input", () => {
    const digit = toEnglishDigits(input.value).replace(/\D/g, "").slice(-1);
    input.value = digit;
    input.classList.toggle("is-filled", Boolean(input.value));
    input.removeAttribute("aria-invalid");
    otpError.classList.remove("is-visible");

    if (input.value && index < otpInputs.length - 1) otpInputs[index + 1].focus();
    if (otpValue().length === otpInputs.length) {
      verifyButton.disabled = false;
      setTimeout(() => verifyForm.requestSubmit(), 180);
    }
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Backspace" && !input.value && index > 0) {
      otpInputs[index - 1].focus();
      otpInputs[index - 1].value = "";
      otpInputs[index - 1].classList.remove("is-filled");
    }
    if (event.key === "ArrowLeft" && index < otpInputs.length - 1) otpInputs[index + 1].focus();
    if (event.key === "ArrowRight" && index > 0) otpInputs[index - 1].focus();
  });

  input.addEventListener("paste", (event) => {
    const text = event.clipboardData?.getData("text") ?? "";
    const digits = toEnglishDigits(text).replace(/\D/g, "");
    if (!digits) return;
    event.preventDefault();
    digits.split("").slice(0, otpInputs.length - index).forEach((digit, offset) => {
      const target = otpInputs[index + offset];
      target.value = digit;
      target.classList.add("is-filled");
    });
    otpInputs[Math.min(index + digits.length, otpInputs.length - 1)].focus();
    if (otpValue().length === otpInputs.length) setTimeout(() => verifyForm.requestSubmit(), 120);
  });
});

verifyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (submitting) return;

  const code = otpValue();
  if (code.length !== 6) {
    showOtpError("کد شش‌رقمی کامل را وارد کنید.");
    return;
  }

  submitting = true;
  setButtonLoading(verifyButton, true, "در حال بررسی…");
  try {
    const { data } = await api.post(
      "/auth/otp/verify",
      { phone: currentPhone, challenge_id: challengeId, code },
      { auth: false },
    );
    saveSession(data);
    clearInterval(timerId);
    toast(`خوش آمدید ${data.user.name}`, { title: "ورود موفق" });
    setTimeout(() => afterLogin(data.user), 500);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      showOtpError(error.message || "کد منقضی شده است. کد تازه بگیرید.");
      verifyButton.disabled = true;
      resendAt = 0;
      startTimer();
    } else if (error instanceof ApiError && error.details?.some((item) => item.field === "code")) {
      showOtpError(error.details.find((item) => item.field === "code").message);
      resetOtp();
      otpInputs[0].focus();
    } else if (error instanceof ApiError && error.status === 429) {
      showOtpError("تعداد تلاش‌ها زیاد شد. کمی بعد دوباره امتحان کنید.");
    } else {
      showOtpError(error.message || "تأیید کد ناموفق بود.");
    }
    submitting = false;
    setButtonLoading(verifyButton, false);
  }
});

resendButtons.forEach((btn) => {
  btn.addEventListener("click", async () => {
    if (Date.now() < resendAt || submitting) return;
    resendButtons.forEach((item) => (item.disabled = true));
    try {
      const { data } = await api.post("/auth/otp/request", { phone: currentPhone, purpose }, { auth: false });
      challengeId = data.challenge_id;
      deadlineIso = new Date(Date.now() + data.expires_in_seconds * 1000).toISOString();
      resendAt = Date.now() + data.resend_after_seconds * 1000;
      verifyButton.disabled = false;
      resetOtp();
      startTimer();
      otpInputs[0].focus();
      toast("کد تازه برای شما ارسال شد.");
    } catch (error) {
      toast(error.message || "ارسال دوباره کد ناموفق بود.", { type: "error" });
      resendAt = 0;
      startTimer();
    }
  });
});

verifyForm.querySelector("[data-edit-phone]").addEventListener("click", () => {
  clearInterval(timerId);
  resetOtp();
  verifyForm.hidden = true;
  requestForm.hidden = false;
  setButtonLoading(requestButton, false);
  phoneInput.focus();
  phoneInput.select();
});
