import { faNum } from "./utils.js";

const prefersReduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function icon(name) {
  return `<svg class="icon" aria-hidden="true"><use href="../assets/icons/sprite.svg#${name}"></use></svg>`;
}

/* ---------- Toasts ---------- */
let toastStack;

export function toast(message, { type = "success", title = "", duration = 4200 } = {}) {
  if (!toastStack) {
    toastStack = document.createElement("div");
    toastStack.className = "toast-stack";
    toastStack.setAttribute("role", "status");
    toastStack.setAttribute("aria-live", "polite");
    document.body.append(toastStack);
  }

  const el = document.createElement("div");
  el.className = `toast${type === "error" ? " toast--error" : ""}`;
  el.innerHTML = `
    <span class="toast__icon">${icon(type === "error" ? "i-alert" : "i-check")}</span>
    <span class="toast__body">
      ${title ? `<strong>${title}</strong> ` : ""}
      <span>${message}</span>
    </span>
    <button class="toast__close" type="button" aria-label="بستن پیام">${icon("i-x")}</button>
  `;

  const dismiss = () => {
    el.classList.add("is-leaving");
    el.addEventListener("animationend", () => el.remove(), { once: true });
    setTimeout(() => el.remove(), 500);
  };

  el.querySelector(".toast__close").addEventListener("click", dismiss);
  toastStack.append(el);
  setTimeout(dismiss, duration);
  return el;
}

/* ---------- Forms ---------- */
export function clearFormErrors(form) {
  form.querySelectorAll("[aria-invalid]").forEach((field) => field.removeAttribute("aria-invalid"));
  form.querySelectorAll(".field-error.is-visible").forEach((el) => el.classList.remove("is-visible"));
}

export function showFieldErrors(form, details = []) {
  clearFormErrors(form);
  let firstField = null;
  details.forEach(({ field, message }) => {
    const input = form.querySelector(`[name="${field}"]`);
    if (!input) return;
    input.setAttribute("aria-invalid", "true");
    let error = input.closest(".field")?.querySelector(".field-error");
    if (!error) {
      error = document.createElement("p");
      error.className = "field-error";
      input.closest(".field")?.append(error);
    }
    error.innerHTML = `${icon("i-alert")}<span>${message}</span>`;
    error.classList.add("is-visible");
    firstField ??= input;
  });
  firstField?.focus({ preventScroll: false });
}

export function setButtonLoading(button, loading, label) {
  if (!button) return;
  if (loading) {
    button.dataset.originalLabel ??= button.innerHTML;
    button.classList.add("is-loading");
    button.disabled = true;
    if (label) {
      const text = button.querySelector(".btn__label");
      if (text) text.textContent = label;
    }
    if (!button.querySelector(".btn__spinner")) {
      const spinner = document.createElement("span");
      spinner.className = "btn__spinner";
      spinner.setAttribute("aria-hidden", "true");
      button.prepend(spinner);
    }
  } else {
    button.classList.remove("is-loading");
    button.disabled = false;
    if (button.dataset.originalLabel) {
      button.innerHTML = button.dataset.originalLabel;
      delete button.dataset.originalLabel;
    }
  }
}

export function formToObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

/* ---------- Dialogs ---------- */
export function openDialog(target) {
  const dialog = typeof target === "string" ? document.querySelector(target) : target;
  if (!dialog) return null;
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
  return dialog;
}

export function closeDialog(target) {
  const dialog = typeof target === "string" ? document.querySelector(target) : target;
  dialog?.close?.();
}

function initDialogs() {
  document.addEventListener("click", (event) => {
    const opener = event.target.closest("[data-open-dialog]");
    if (opener) {
      event.preventDefault();
      openDialog(opener.dataset.openDialog);
      return;
    }
    const closer = event.target.closest("[data-close-dialog]");
    if (closer) {
      event.preventDefault();
      closeDialog(closer.closest("dialog"));
      return;
    }
    if (event.target instanceof HTMLDialogElement && event.target.hasAttribute("data-backdrop-close")) {
      const rect = event.target.getBoundingClientRect();
      const outside =
        event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom;
      if (outside) event.target.close();
    }
  });

  document.querySelectorAll("dialog[data-backdrop-close]").forEach((dialog) => {
    dialog.addEventListener("click", (event) => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      const outside =
        event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom;
      if (outside) dialog.close();
    });
  });
}

/* ---------- Header / menu ---------- */
function initHeader() {
  const header = document.querySelector(".site-head, .app-head");
  if (!header) return;
  const onScroll = () => header.classList.toggle("is-scrolled", window.scrollY > 22);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  document.querySelectorAll("[data-menu-open]").forEach((btn) => {
    btn.addEventListener("click", () => openDialog(btn.dataset.menuOpen));
  });
  document.querySelectorAll(".mobile-menu a[href]").forEach((link) => {
    link.addEventListener("click", () => closeDialog(link.closest("dialog")));
  });
}

/* ---------- Scroll reveal ---------- */
let revealObserver;

export function observeReveal(scope = document) {
  if (prefersReduced()) {
    scope.querySelectorAll("[data-reveal]").forEach((el) => el.classList.add("is-in"));
    return;
  }
  revealObserver ??= new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-in");
        revealObserver.unobserve(entry.target);
      });
    },
    { threshold: 0.14, rootMargin: "0px 0px -6% 0px" },
  );
  scope.querySelectorAll("[data-reveal]:not(.is-in)").forEach((el) => revealObserver.observe(el));
}

/* ---------- Counters ---------- */
function initCounters() {
  const counters = document.querySelectorAll("[data-count]");
  if (!counters.length) return;

  const render = (el, value) => {
    const decimals = Number(el.dataset.decimals || 0);
    el.textContent = faNum(value.toFixed(decimals)) + (el.dataset.suffix || "");
  };

  if (prefersReduced()) {
    counters.forEach((el) => render(el, Number(el.dataset.count)));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const el = entry.target;
        observer.unobserve(el);
        const target = Number(el.dataset.count);
        const duration = Number(el.dataset.duration || 1500);
        const start = performance.now();
        const tick = (now) => {
          const progress = Math.min(1, (now - start) / duration);
          const eased = 1 - Math.pow(1 - progress, 3);
          render(el, target * eased);
          if (progress < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      });
    },
    { threshold: 0.5 },
  );

  counters.forEach((el) => observer.observe(el));
}

/* ---------- Accordion ---------- */
function initAccordions() {
  document.querySelectorAll("[data-accordion]").forEach((group) => {
    const single = group.dataset.accordion !== "multi";
    group.querySelectorAll(".faq-item__q, [data-accordion-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const item = button.closest(".faq-item") || button.parentElement;
        const willOpen = !item.classList.contains("is-open");
        if (single) {
          group.querySelectorAll(".is-open").forEach((open) => {
            open.classList.remove("is-open");
            open.querySelector("[aria-expanded]")?.setAttribute("aria-expanded", "false");
          });
        }
        item.classList.toggle("is-open", willOpen);
        button.setAttribute("aria-expanded", String(willOpen));
      });
    });
  });
}

/* ---------- Parallax (pointer + scroll) ---------- */
function initParallax() {
  if (prefersReduced()) return;
  const layers = document.querySelectorAll("[data-parallax]");
  if (!layers.length) return;

  let raf = 0;
  const update = () => {
    raf = 0;
    const viewport = window.innerHeight;
    layers.forEach((layer) => {
      const rect = layer.getBoundingClientRect();
      const speed = Number(layer.dataset.parallax) || 0.08;
      const offset = (rect.top + rect.height / 2 - viewport / 2) * -speed;
      layer.style.setProperty("--parallax-y", `${offset.toFixed(1)}px`);
    });
  };
  const schedule = () => {
    if (!raf) raf = requestAnimationFrame(update);
  };
  update();
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule);
}

/* ---------- Generic filter chips ---------- */
export function initFilterChips(scope = document, onChange) {
  scope.querySelectorAll("[data-filter-group]").forEach((group) => {
    group.addEventListener("click", (event) => {
      const chip = event.target.closest("[data-filter]");
      if (!chip) return;
      group.querySelectorAll("[data-filter]").forEach((item) => {
        const active = item === chip;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      onChange?.(chip.dataset.filter, group);
    });
  });
}

/* ---------- Anchor smooth scroll ---------- */
function initAnchors() {
  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener("click", (event) => {
      const id = link.getAttribute("href");
      if (!id || id === "#") return;
      const target = document.querySelector(id);
      if (!target) return;
      event.preventDefault();
      target.scrollIntoView({ behavior: prefersReduced() ? "auto" : "smooth", block: "start" });
      history.replaceState(null, "", id);
    });
  });
}

/* ---------- Boot ---------- */
let booted = false;

export function initUI() {
  if (booted) return;
  booted = true;
  initDialogs();
  initHeader();
  initCounters();
  initAccordions();
  initParallax();
  initAnchors();
  observeReveal();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initUI, { once: true });
} else {
  initUI();
}
