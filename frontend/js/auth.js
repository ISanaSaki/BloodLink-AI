import { api, getToken, setToken } from "./api-client.js";
import { TOKEN_KEY } from "./config.js";
import { formatPhoneForDisplay, initials } from "./utils.js";

const USER_KEY = "blood_user";
const DEMO_ROLE_KEY = "blood_demo_role";
const PAGE = (name) => new URL(`../pages/${name}`, import.meta.url);

export const DASHBOARD_BY_ROLE = {
  donor: "donor-dashboard.html",
  center_operator: "center-dashboard.html",
};

export function dashboardFor(role) {
  return DASHBOARD_BY_ROLE[role] ?? "donor-dashboard.html";
}

export function setDemoRole(role) {
  sessionStorage.setItem(DEMO_ROLE_KEY, role === "center_operator" ? "center_operator" : "donor");
}

export function getDemoRole() {
  return sessionStorage.getItem(DEMO_ROLE_KEY) === "center_operator" ? "center_operator" : "donor";
}

export function saveSession({ access_token, user }) {
  setToken(access_token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  return user;
}

export function getUser() {
  try {
    return JSON.parse(sessionStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

export function updateUser(patch) {
  const next = { ...(getUser() || {}), ...patch };
  sessionStorage.setItem(USER_KEY, JSON.stringify(next));
  return next;
}

export function isLoggedIn() {
  return Boolean(getToken() && getUser());
}

export function logout() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
  location.replace(PAGE("login.html"));
}

export async function refreshUser() {
  const { data } = await api.get("/users/me");
  sessionStorage.setItem(USER_KEY, JSON.stringify(data));
  return data;
}

export function guard(requiredRole) {
  if (!isLoggedIn()) {
    const login = PAGE("login.html");
    login.searchParams.set("next", location.pathname.split("/").pop());
    location.replace(login);
    return null;
  }
  const user = getUser();
  if (requiredRole && user.role !== requiredRole) {
    location.replace(PAGE(dashboardFor(user.role)));
    return null;
  }
  return user;
}

export function afterLogin(user) {
  const next = new URLSearchParams(location.search).get("next");
  const safeNext = next && /^[a-z0-9-]+\.html$/i.test(next) ? next : "";
  if (safeNext && safeNext !== "login.html") {
    location.replace(new URL(safeNext, PAGE("")));
    return;
  }
  location.replace(PAGE(dashboardFor(user.role)));
}

export function displayName(user) {
  return user?.name || formatPhoneForDisplay(user?.phone) || "کاربر";
}

function avatarLabel(user) {
  if (user?.name) return initials(user.name);
  const digits = String(user?.phone ?? "").replace(/\D/g, "");
  if (!digits) return "؟";
  const lastTwo = digits.slice(-2).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
  return lastTwo;
}

export function initAppShell() {
  const user = getUser();
  if (!user) return null;

  document.querySelectorAll("[data-user-name]").forEach((el) => {
    el.textContent = displayName(user);
  });
  document.querySelectorAll("[data-user-avatar]").forEach((el) => {
    el.textContent = avatarLabel(user);
  });
  document.querySelectorAll("[data-user-role]").forEach((el) => {
    el.textContent = user.role === "center_operator" ? "کارشناس مرکز اهدای خون" : "داوطلب اهدای خون";
  });

  document.querySelectorAll("[data-logout]").forEach((btn) => {
    btn.addEventListener("click", logout);
  });

  return user;
}
