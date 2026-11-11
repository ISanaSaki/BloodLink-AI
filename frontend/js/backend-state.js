import { api } from "./api-client.js";

const DONOR_PROFILE_KEY = "blood_donor_profile";
const AVAILABILITY_KEY = "blood_availability";
const CENTER_KEY = "blood_center";
const DISPATCH_KEY = "blood_dispatched";

function readJson(key) {
  try {
    return JSON.parse(sessionStorage.getItem(key) || "null");
  } catch {
    return null;
  }
}

function writeJson(key, value) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage may be unavailable */
  }
}

export function getCachedDonorProfile() {
  return readJson(DONOR_PROFILE_KEY);
}

export function cacheDonorProfile(profile) {
  if (profile) writeJson(DONOR_PROFILE_KEY, profile);
}

export function getCachedAvailability() {
  return readJson(AVAILABILITY_KEY);
}

export function cacheAvailability(availability) {
  if (availability) writeJson(AVAILABILITY_KEY, availability);
}

export function getCachedCenter() {
  return readJson(CENTER_KEY);
}

export function cacheCenter(center) {
  if (center) writeJson(CENTER_KEY, center);
}

export function getDispatchState(requestId) {
  return readJson(DISPATCH_KEY)?.[requestId] ?? null;
}

export function markDispatched(requestId, dispatchId) {
  const state = readJson(DISPATCH_KEY) ?? {};
  state[requestId] = { dispatch_id: dispatchId, dispatched_at: new Date().toISOString() };
  writeJson(DISPATCH_KEY, state);
}

/**
 * The contract has no "my centre" endpoint; find the centre the current operator owns
 * by listing active centres and checking each detail (is_verified is only present for
 * the admin or the owning operator). Falls back to the first active centre.
 */
export async function fetchManagedCenter() {
  const cached = getCachedCenter();
  if (cached) return cached;

  try {
    const { data: centers } = await api.get("/centers?page_size=100");
    if (!centers?.length) return null;

    const managed = [];
    await Promise.all(
      centers.map(async (center) => {
        try {
          const { data: detail } = await api.get(`/centers/${center.id}`);
          if (detail && "is_verified" in detail) managed.push(detail);
        } catch {
          /* inactive or inaccessible centre: skip */
        }
      }),
    );

    const chosen = managed[0] ?? centers[0];
    cacheCenter(chosen);
    return chosen;
  } catch {
    return null;
  }
}
