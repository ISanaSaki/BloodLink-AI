import { api } from "../api-client.js";
import { guard, initAppShell } from "../auth.js";
import { fetchManagedCenter } from "../backend-state.js";
import {
  componentMeta,
  faNum,
  fromDateTimeInput,
  remainingLabel,
  toDateTimeInput,
  urgencyMeta,
} from "../utils.js";
import { setButtonLoading, toast } from "../ui.js";

const user = guard("center_operator");
if (user) initAppShell();

let center = null;
const form = document.querySelector("#request-form");
const unitsInput = document.querySelector("#units-needed");
const expiryInput = document.querySelector("#expires-at");
const notesInput = document.querySelector("#request-notes");
const notesCount = document.querySelector("[data-notes-count]");
const submitButtons = [...form.querySelectorAll('button[type="submit"]')];

async function init() {
  center = await fetchManagedCenter();
  if (center) {
    document.querySelectorAll("[data-center-name]").forEach((el) => {
      el.textContent = center.name;
    });
  }

  setDefaultExpiry();
  bindEvents();
  updatePreview();
}

function setDefaultExpiry(minutes = 360) {
  expiryInput.value = toDateTimeInput(new Date(Date.now() + minutes * 60000));
  expiryInput.min = toDateTimeInput(new Date(Date.now() + 15 * 60000));
}

/* ---------- Preview ---------- */
function formValues() {
  const data = new FormData(form);
  return {
    component_type: data.get("component_type") || "",
    blood_group: data.get("blood_group") || "",
    rh_factor: data.get("rh_factor") || "",
    units_needed: clampUnits(data.get("units_needed")),
    urgency: data.get("urgency") || "routine",
    expires_at: data.get("expires_at") || "",
    notes: String(data.get("notes") || "").trim(),
  };
}

function updatePreview() {
  const values = formValues();
  const meta = values.component_type ? componentMeta(values.component_type) : null;
  const urgency = urgencyMeta(values.urgency);
  const blood = values.blood_group
    ? `${values.blood_group}${values.rh_factor === "negative" ? "−" : values.rh_factor === "positive" ? "+" : ""}`
    : "—";

  document.querySelector("[data-preview-blood]").textContent = blood;
  document.querySelector("[data-preview-type]").textContent = meta ? meta.label : "گروه خونی";
  document.querySelector("[data-preview-component]").textContent = meta ? meta.label : "انتخاب نشده";
  document.querySelector("[data-preview-units]").textContent = `${faNum(values.units_needed)} واحد`;
  document.querySelector("[data-preview-urgency]").textContent = urgency.label;
  document.querySelector("[data-preview-expiry]").textContent = values.expires_at
    ? remainingLabel(fromDateTimeInput(values.expires_at))
    : "تعیین نشده";

  const headline = meta
    ? `نیاز به ${faNum(values.units_needed)} واحد ${meta.label}`
    : "درخواست تازه";
  document.querySelector("[data-preview-headline]").textContent = headline;
  document.querySelector("[data-preview-desc]").textContent = meta
    ? `${urgency.label === "بحرانی" ? "نیاز بحرانی" : urgency.label === "فوری" ? "نیاز فوری" : "نیاز"} برای داوطلبان ${blood} در ${center?.name ?? "این مرکز"}؛ مهلت پاسخ تا ${values.expires_at ? remainingLabel(fromDateTimeInput(values.expires_at)) : "پایان روز"}.`
    : "فرآورده و گروه خونی را انتخاب کنید تا پیش‌نمایش کامل شود.";
}

function clampUnits(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 1;
  return Math.min(10, Math.max(1, Math.round(number)));
}

/* ---------- Validation ---------- */
function collectErrors(values) {
  const errors = [];
  if (!values.component_type) errors.push(["component_type", "نوع فرآورده را انتخاب کنید."]);
  if (!values.blood_group) errors.push(["blood_group", "گروه خونی بیمار را انتخاب کنید."]);
  if (!values.rh_factor) errors.push(["rh_factor", "عامل Rh را انتخاب کنید."]);
  if (!Number.isInteger(values.units_needed) || values.units_needed < 1) {
    errors.push(["units_needed", "تعداد واحد باید بین ۱ تا ۱۰ باشد."]);
  }
  if (!values.expires_at) {
    errors.push(["expires_at", "مهلت پاسخ را انتخاب کنید."]);
  } else {
    const iso = fromDateTimeInput(values.expires_at);
    if (!iso || new Date(iso).getTime() <= Date.now()) {
      errors.push(["expires_at", "مهلت پاسخ باید در آینده باشد."]);
    }
  }
  if (values.notes.length > 500) {
    errors.push(["notes", "یادداشت حداکثر می‌تواند ۵۰۰ نویسه باشد."]);
  }
  return errors;
}

const icon = (name) =>
  `<svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#${name}"></use></svg>`;

function showError(name, message) {
  const field = form.querySelector(`[data-field="${name}"]`) ?? form.querySelector(`[name="${name}"]`)?.closest(".field");
  if (!field) return;
  field.classList.add("option-error");
  form.querySelectorAll(`[name="${name}"]`).forEach((input) => input.setAttribute("aria-invalid", "true"));
  const error = field.querySelector(`[data-error-for="${name}"]`) ?? field.querySelector(".field-error");
  if (error) {
    error.innerHTML = `${icon("i-alert")}<span>${message}</span>`;
    error.classList.add("is-visible");
  }
  field.querySelector("input, textarea, select")?.focus({ preventScroll: false });
}

function clearError(name) {
  const field = form.querySelector(`[data-field="${name}"]`);
  if (!field) return;
  field.classList.remove("option-error");
  form.querySelectorAll(`[name="${name}"]`).forEach((input) => input.removeAttribute("aria-invalid"));
  const error = field.querySelector(`[data-error-for="${name}"]`) ?? field.querySelector(".field-error");
  error?.classList.remove("is-visible");
}

function clearErrors() {
  form.querySelectorAll(".option-error").forEach((field) => field.classList.remove("option-error"));
  form.querySelectorAll("[aria-invalid]").forEach((input) => input.removeAttribute("aria-invalid"));
  form.querySelectorAll(".field-error.is-visible").forEach((error) => error.classList.remove("is-visible"));
}

/* ---------- Submit ---------- */
async function submitRequest(event) {
  event.preventDefault();
  clearErrors();

  const values = formValues();
  const errors = collectErrors(values);
  if (errors.length) {
    errors.forEach(([name, message]) => showError(name, message));
    toast("چند فیلد نیاز به بازبینی دارد.", { type: "error", title: "اطلاعات کامل نیست" });
    return;
  }

  if (!center) {
    toast("اطلاعات مرکز دریافت نشد. دوباره تلاش کنید.", { type: "error" });
    return;
  }

  const mode = event.submitter?.value === "activate" ? "activate" : "draft";
  const clicked = event.submitter;
  setButtonLoading(clicked, true, "در حال ثبت…");
  submitButtons.filter((button) => button !== clicked).forEach((button) => (button.disabled = true));

  try {
    const { data: request } = await api.post("/blood-requests", {
      center_id: center.id,
      component_type: values.component_type,
      blood_group: values.blood_group,
      rh_factor: values.rh_factor,
      units_needed: values.units_needed,
      urgency: values.urgency,
      expires_at: fromDateTimeInput(values.expires_at),
      notes: values.notes,
    });

    if (mode === "activate") {
      await api.post(`/blood-requests/${request.id}/activate`);
    }

    toast(
      mode === "activate"
        ? "درخواست ثبت و فعال شد. در داشبورد می‌توانید فراخوان داوطلبان را آغاز کنید."
        : "درخواست به‌صورت پیش‌نویس ذخیره شد و پیامی ارسال نشد.",
      { title: mode === "activate" ? "درخواست فعال شد" : "پیش‌نویس ذخیره شد" },
    );

    setTimeout(() => {
      location.href = `center-dashboard.html?highlight=${encodeURIComponent(request.id)}&created=1`;
    }, 700);
  } catch (error) {
    setButtonLoading(clicked, false);
    submitButtons.forEach((button) => (button.disabled = false));
    if (error.details?.length) {
      error.details.forEach((detail) => showError(detail.field, detail.message));
    }
    toast(error.message || "ثبت درخواست ممکن نشد.", { type: "error", title: "خطا در ثبت" });
  }
}

/* ---------- Events ---------- */
function bindEvents() {
  form.addEventListener("submit", submitRequest);

  form.addEventListener("input", (event) => {
    const name = event.target.name;
    if (name) clearError(name);
    if (name === "units_needed") {
      const next = clampUnits(event.target.value);
      if (event.target.value !== "" && Number(event.target.value) !== next) {
        event.target.value = next;
      }
    }
    updatePreview();
  });

  form.addEventListener("change", (event) => {
    if (event.target.name) clearError(event.target.name);
    updatePreview();
  });

  unitsInput.addEventListener("blur", () => {
    unitsInput.value = clampUnits(unitsInput.value);
    updatePreview();
  });

  document.querySelectorAll("[data-step]").forEach((button) => {
    button.addEventListener("click", () => {
      const next = clampUnits(Number(unitsInput.value || 1) + Number(button.dataset.step));
      unitsInput.value = next;
      updatePreview();
    });
  });

  document.querySelectorAll("[data-expiry-minutes]").forEach((chip) => {
    chip.addEventListener("click", () => {
      setDefaultExpiry(Number(chip.dataset.expiryMinutes));
      clearError("expires_at");
      updatePreview();
    });
  });

  notesInput.addEventListener("input", () => {
    notesCount.textContent = `${faNum(notesInput.value.length)} از ۵۰۰`;
  });
}

if (user) init();
