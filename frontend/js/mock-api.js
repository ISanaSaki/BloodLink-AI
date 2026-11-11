import { DEMO_LATENCY, DEMO_OTP } from "./config.js";
import { normalizePhone, isValidIranPhone, sleep } from "./utils.js";

const DB_KEY = "hambkhoon_demo_db_v3";
const ROLE_KEY = "blood_demo_role";

export class MockApiError extends Error {
  constructor(status, code, message, details = []) {
    super(message);
    this.name = "MockApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = crypto.randomUUID();
  }

  toPayload() {
    return {
      error: {
        code: this.code,
        message: this.message,
        details: this.details,
        request_id: this.requestId,
      },
    };
  }
}

let memoryDb = null;

const nowPlus = (minutes) => new Date(Date.now() + minutes * 60000).toISOString();
const nowMinus = (minutes) => new Date(Date.now() - minutes * 60000).toISOString();
const daysAgo = (days) => new Date(Date.now() - days * 86400000).toISOString();
const id = () => crypto.randomUUID();

function seedDatabase() {
  const centers = [
    {
      id: "c1000000-0000-4000-8000-000000000001",
      name: "مرکز اهدای خون وصال شیراز",
      address: "شیراز، بلوار زند، جنب درمانگاه وصال",
      latitude: 29.6182,
      longitude: 52.5311,
      phone: "+987136234567",
      opening_hours: "۸:۰۰ تا ۲۰:۰۰",
      is_active: true,
      is_verified: true,
    },
    {
      id: "c1000000-0000-4000-8000-000000000002",
      name: "مرکز اهدای خون ونک تهران",
      address: "تهران، خیابان ونک، کوچه صانعی، پلاک ۱۴",
      latitude: 35.7571,
      longitude: 51.4102,
      phone: "+982188776655",
      opening_hours: "۷:۳۰ تا ۱۹:۳۰",
      is_active: true,
      is_verified: true,
    },
    {
      id: "c1000000-0000-4000-8000-000000000003",
      name: "مرکز اهدای خون اصفهان",
      address: "اصفهان، خیابان چهارباغ بالا، جنب بیمارستان امین",
      latitude: 32.6408,
      longitude: 51.6672,
      phone: "+983136654433",
      opening_hours: "۸:۰۰ تا ۱۸:۰۰",
      is_active: true,
      is_verified: true,
    },
  ];

  const users = [
    {
      id: "d2000000-0000-4000-8000-000000000001",
      phone: "+989121234567",
      name: "سارا محمدی",
      role: "donor",
      is_active: true,
      created_at: "2025-08-12T09:15:00Z",
    },
    {
      id: "e2000000-0000-4000-8000-000000000002",
      phone: "+989121234568",
      name: "امیر رضایی",
      role: "center_operator",
      center_id: centers[0].id,
      is_active: true,
      created_at: "2025-06-02T08:20:00Z",
    },
  ];

  const donorProfiles = [
    {
      id: "d1000000-0000-4000-8000-000000000001",
      user_id: users[0].id,
      blood_group: "O",
      rh_factor: "positive",
      blood_type_verified: true,
      last_donation_date: "2026-07-18",
      sms_consent: true,
      location_consent: true,
    },
  ];

  const availability = [
    {
      id: id(),
      donor_id: donorProfiles[0].id,
      status: "available",
      available_from: nowMinus(45),
      available_until: nowPlus(260),
      updated_at: nowMinus(30),
    },
  ];

  const bloodRequests = [
    {
      id: "a1000000-0000-4000-8000-000000000001",
      center_id: centers[0].id,
      component_type: "red_cells",
      blood_group: "O",
      rh_factor: "positive",
      units_needed: 2,
      urgency: "critical",
      status: "active",
      expires_at: nowPlus(52),
      notes: "بیمار تصادفی در بخش اورژانس؛ هماهنگی با سوپروایزر انجام شده است.",
      created_by: users[1].id,
      created_at: nowMinus(21),
      activated_at: nowMinus(19),
      dispatch_id: id(),
      dispatched_at: nowMinus(12),
      candidate_count: 8,
      first_batch_size: 5,
    },
    {
      id: "a1000000-0000-4000-8000-000000000002",
      center_id: centers[0].id,
      component_type: "platelets",
      blood_group: "A",
      rh_factor: "positive",
      units_needed: 1,
      urgency: "urgent",
      status: "active",
      expires_at: nowPlus(138),
      notes: "بیمار تحت شیمی‌درمانی؛ نیاز به پلاکت آفرزیس.",
      created_by: users[1].id,
      created_at: nowMinus(41),
      activated_at: nowMinus(38),
      dispatch_id: null,
      dispatched_at: null,
      candidate_count: 0,
      first_batch_size: 5,
    },
    {
      id: "a1000000-0000-4000-8000-000000000003",
      center_id: centers[0].id,
      component_type: "whole_blood",
      blood_group: "B",
      rh_factor: "negative",
      units_needed: 3,
      urgency: "routine",
      status: "draft",
      expires_at: nowPlus(420),
      notes: "ذخیره احتیاطی برای روزهای آینده.",
      created_by: users[1].id,
      created_at: nowMinus(9),
      activated_at: null,
      dispatch_id: null,
      dispatched_at: null,
      candidate_count: 0,
      first_batch_size: 5,
    },
    {
      id: "a1000000-0000-4000-8000-000000000004",
      center_id: centers[0].id,
      component_type: "plasma",
      blood_group: "AB",
      rh_factor: "positive",
      units_needed: 2,
      urgency: "routine",
      status: "fulfilled",
      expires_at: daysAgo(2),
      notes: "درخواست تکمیل‌شده هفته گذشته.",
      created_by: users[1].id,
      created_at: daysAgo(3),
      activated_at: daysAgo(3),
      dispatch_id: id(),
      dispatched_at: daysAgo(3),
      candidate_count: 6,
      first_batch_size: 4,
    },
    {
      id: "a1000000-0000-4000-8000-000000000005",
      center_id: centers[0].id,
      component_type: "red_cells",
      blood_group: "O",
      rh_factor: "negative",
      units_needed: 1,
      urgency: "urgent",
      status: "cancelled",
      expires_at: nowPlus(90),
      notes: "پس از تأمین از مرکز همکار لغو شد.",
      created_by: users[1].id,
      created_at: daysAgo(1),
      activated_at: daysAgo(1),
      dispatch_id: null,
      dispatched_at: null,
      candidate_count: 0,
      first_batch_size: 5,
    },
  ];

  const notifications = [
    {
      id: "b1000000-0000-4000-8000-000000000001",
      request_id: bloodRequests[0].id,
      donor_id: donorProfiles[0].id,
      channel: "sms",
      status: "delivered",
      idempotency_key: `dispatch:${bloodRequests[0].id}:donor-1`,
      provider_message_id: "mock-88421",
      eta_minutes: 11,
      distance_km: 2.4,
      created_at: nowMinus(12),
      expires_at: nowPlus(52),
      response: null,
      responded_at: null,
    },
    {
      id: "b1000000-0000-4000-8000-000000000002",
      request_id: bloodRequests[1].id,
      donor_id: donorProfiles[0].id,
      channel: "sms",
      status: "delivered",
      idempotency_key: `dispatch:${bloodRequests[1].id}:donor-1`,
      provider_message_id: "mock-88390",
      eta_minutes: 18,
      distance_km: 4.8,
      created_at: nowMinus(31),
      expires_at: nowPlus(138),
      response: "interested",
      responded_at: nowMinus(22),
    },
    {
      id: "b1000000-0000-4000-8000-000000000003",
      request_id: bloodRequests[3].id,
      donor_id: donorProfiles[0].id,
      channel: "sms",
      status: "delivered",
      idempotency_key: `dispatch:${bloodRequests[3].id}:donor-1`,
      provider_message_id: "mock-87112",
      eta_minutes: 24,
      distance_km: 6.1,
      created_at: daysAgo(3),
      expires_at: daysAgo(2),
      response: "unavailable",
      responded_at: daysAgo(3),
    },
  ];

  const donorResponses = [
    {
      id: "f1000000-0000-4000-8000-000000000001",
      notification_id: notifications[1].id,
      request_id: bloodRequests[1].id,
      donor_reference: "D-1042",
      response: "interested",
      responded_at: nowMinus(22),
      eta_minutes: 18,
    },
    {
      id: "f1000000-0000-4000-8000-000000000002",
      notification_id: notifications[2].id,
      request_id: bloodRequests[3].id,
      donor_reference: "D-1042",
      response: "unavailable",
      responded_at: daysAgo(3),
      eta_minutes: 24,
    },
    {
      id: "f1000000-0000-4000-8000-000000000003",
      notification_id: "b1000000-0000-4000-8000-000000000011",
      request_id: bloodRequests[0].id,
      donor_reference: "D-1187",
      response: "interested",
      responded_at: nowMinus(7),
      eta_minutes: 14,
    },
    {
      id: "f1000000-0000-4000-8000-000000000004",
      notification_id: "b1000000-0000-4000-8000-000000000012",
      request_id: bloodRequests[0].id,
      donor_reference: "D-1233",
      response: "interested",
      responded_at: nowMinus(5),
      eta_minutes: 9,
    },
  ];

  const candidateRefs = [
    ["D-1042", 9, 1.8, "verified_data"],
    ["D-1187", 11, 2.4, "verified_data"],
    ["D-1233", 14, 3.1, "verified_data"],
    ["D-1301", 17, 3.8, "verified_data"],
    ["D-1408", 21, 4.6, "needs_review"],
    ["D-1522", 24, 5.2, "verified_data"],
    ["D-1604", 28, 6.3, "verified_data"],
    ["D-1711", 33, 7.4, "needs_review"],
  ];

  const candidates = {
    [bloodRequests[0].id]: candidateRefs.map(([ref, eta, distance, eligibility], index) => ({
      donor_id: id(),
      donor_reference: ref,
      eta_minutes: eta,
      distance_km: distance,
      eligibility_check_status: eligibility,
      dispatch_stage: index < 5 ? 1 : 2,
    })),
    [bloodRequests[3].id]: candidateRefs.slice(0, 6).map(([ref, eta, distance, eligibility]) => ({
      donor_id: id(),
      donor_reference: ref,
      eta_minutes: eta,
      distance_km: distance,
      eligibility_check_status: eligibility,
      dispatch_stage: 1,
    })),
  };

  return {
    version: 2,
    centers,
    users,
    donor_profiles: donorProfiles,
    donor_locations: [
      {
        id: id(),
        donor_id: donorProfiles[0].id,
        latitude: 29.6105,
        longitude: 52.5312,
        updated_at: nowMinus(20),
      },
    ],
    availability,
    blood_requests: bloodRequests,
    notifications,
    donor_responses: donorResponses,
    candidates,
    sessions: {},
    challenges: [],
    audit_logs: [],
  };
}

function refreshDemoClock(db) {
  const now = Date.now();
  const activeRequests = db.blood_requests.filter((request) => request.status === "active");
  activeRequests.forEach((request, index) => {
    if (new Date(request.expires_at).getTime() < now) {
      request.expires_at = nowPlus(75 + index * 60);
    }
  });

  db.notifications.forEach((notification, index) => {
    if (notification.response) return;
    if (new Date(notification.expires_at).getTime() < now) {
      notification.expires_at = nowPlus(38 + index * 45);
      notification.created_at = nowMinus(4 + index * 8);
      const request = db.blood_requests.find((item) => item.id === notification.request_id);
      if (request && request.status === "active") {
        request.expires_at = nowPlus(60 + index * 30);
      }
    }
  });

  activeRequests.forEach((request) => {
    if (request.dispatch_id && new Date(request.expires_at).getTime() < now) {
      request.expires_at = nowPlus(75);
    }
  });
}

function readDb() {
  if (memoryDb) return memoryDb;
  try {
    const raw = localStorage.getItem(DB_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed?.version === 2) {
        memoryDb = parsed;
        refreshDemoClock(memoryDb);
        return memoryDb;
      }
    }
  } catch {
    /* demo storage may be unavailable */
  }
  memoryDb = seedDatabase();
  writeDb(memoryDb);
  return memoryDb;
}

function writeDb(db) {
  try {
    localStorage.setItem(DB_KEY, JSON.stringify(db));
  } catch {
    /* keep memory copy when storage is unavailable */
  }
}

function fail(status, code, message, details = []) {
  throw new MockApiError(status, code, message, details);
}

function envelope(data, meta = {}) {
  return {
    data,
    meta: { request_id: crypto.randomUUID(), ...meta },
  };
}

function paginate(items, query) {
  const page = Math.max(1, Number(query.get("page")) || 1);
  const pageSize = Math.min(100, Math.max(1, Number(query.get("page_size")) || 20));
  return {
    items: items.slice((page - 1) * pageSize, page * pageSize),
    meta: { page, page_size: pageSize, total: items.length },
  };
}

function publicCenter(center) {
  if (!center) return null;
  const { id: centerId, name, address, phone, opening_hours, latitude, longitude } = center;
  return {
    id: centerId,
    name,
    address,
    phone,
    opening_hours,
    latitude,
    longitude,
    is_active: center.is_active,
  };
}

function currentSession(db, token) {
  const session = token ? db.sessions[token] : null;
  if (!session) {
    fail(401, "UNAUTHENTICATED", "نشست شما معتبر نیست. دوباره وارد شوید.");
  }
  const user = db.users.find((item) => item.id === session.user_id);
  if (!user) {
    fail(401, "UNAUTHENTICATED", "کاربر یافت نشد.");
  }
  return { session, user };
}

function requireRole(session, roles) {
  if (!roles.includes(session.role)) {
    fail(403, "FORBIDDEN", "برای این عملیات دسترسی ندارید.");
  }
}

function findDonorProfile(db, userId) {
  return db.donor_profiles.find((profile) => profile.user_id === userId) ?? null;
}

function isProfileComplete(profile) {
  return Boolean(profile?.blood_group && profile?.rh_factor);
}

function buildMe(db, session, user) {
  const profile = findDonorProfile(db, user.id);
  const availability = profile
    ? db.availability.find((item) => item.donor_id === profile.id) ?? null
    : null;
  const center = user.center_id ? publicCenter(db.centers.find((item) => item.id === user.center_id)) : null;

  return {
    id: user.id,
    phone: session.phone,
    name: user.name,
    role: user.role,
    is_active: user.is_active,
    is_profile_complete: Boolean(profile && isProfileComplete(profile) && profile.sms_consent),
    donor_profile: profile,
    availability,
    center,
  };
}

function enrichRequest(db, request) {
  const center = db.centers.find((item) => item.id === request.center_id);
  const responseCount = db.donor_responses.filter(
    (response) => response.request_id === request.id && response.response === "interested",
  ).length;
  const candidates = db.candidates[request.id] ?? [];
  return {
    ...request,
    center: publicCenter(center),
    candidates_count: candidates.length,
    interested_count: responseCount,
  };
}

function enrichNotification(db, notification) {
  const request = db.blood_requests.find((item) => item.id === notification.request_id);
  const center = request ? db.centers.find((item) => item.id === request.center_id) : null;
  return {
    id: notification.id,
    request_id: notification.request_id,
    channel: notification.channel,
    status: notification.status,
    created_at: notification.created_at,
    expires_at: notification.expires_at,
    center_id: center?.id ?? null,
    center_name: center?.name ?? null,
    component_type: request?.component_type ?? null,
    blood_group: request?.blood_group ?? null,
    rh_factor: request?.rh_factor ?? null,
    urgency: request?.urgency ?? null,
    response: notification.response
      ? { response: notification.response, responded_at: notification.responded_at }
      : null,
  };
}

function makeCandidateList(requestId) {
  const refs = [
    ["D-2041", 8, 1.6, "verified_data"],
    ["D-2177", 12, 2.3, "verified_data"],
    ["D-2284", 15, 3.2, "verified_data"],
    ["D-2330", 19, 4.1, "needs_review"],
    ["D-2415", 22, 4.9, "verified_data"],
    ["D-2506", 26, 5.8, "verified_data"],
    ["D-2619", 31, 6.7, "needs_review"],
  ];
  return refs.map(([ref, eta, distance, eligibility], index) => ({
    donor_id: id(),
    donor_reference: ref,
    eta_minutes: eta,
    distance_km: distance,
    eligibility_check_status: eligibility,
    dispatch_stage: index < 5 ? 1 : 2,
    request_id: requestId,
  }));
}

function validateRequestPayload(payload) {
  const details = [];
  if (!payload.center_id) details.push({ field: "center_id", message: "انتخاب مرکز الزامی است." });
  if (!["red_cells", "platelets", "plasma", "whole_blood"].includes(payload.component_type)) {
    details.push({ field: "component_type", message: "نوع فرآورده معتبر نیست." });
  }
  if (!["A", "B", "AB", "O"].includes(payload.blood_group)) {
    details.push({ field: "blood_group", message: "گروه خونی معتبر نیست." });
  }
  if (!["positive", "negative"].includes(payload.rh_factor)) {
    details.push({ field: "rh_factor", message: "Rh معتبر نیست." });
  }
  const units = Number(payload.units_needed);
  if (!Number.isInteger(units) || units <= 0) {
    details.push({ field: "units_needed", message: "تعداد واحد باید عددی بزرگ‌تر از صفر باشد." });
  }
  if (!["routine", "urgent", "critical"].includes(payload.urgency)) {
    details.push({ field: "urgency", message: "سطح فوریت معتبر نیست." });
  }
  const expires = new Date(payload.expires_at);
  if (!payload.expires_at || Number.isNaN(expires.getTime()) || expires.getTime() <= Date.now()) {
    details.push({ field: "expires_at", message: "مهلت درخواست باید در آینده باشد." });
  }
  if (details.length) {
    fail(422, "VALIDATION_ERROR", "اطلاعات ورودی معتبر نیست.", details);
  }
}

function handle(path, method, body, query, token) {
  const db = readDb();
  let result;

  if (path === "/auth/otp/request" && method === "POST") {
    const phone = normalizePhone(body?.phone);
    if (!isValidIranPhone(phone)) {
      fail(422, "VALIDATION_ERROR", "شماره موبایل معتبر نیست.", [
        { field: "phone", message: "شماره موبایل معتبر نیست." },
      ]);
    }
    if (!["login", "register"].includes(body?.purpose)) {
      fail(422, "VALIDATION_ERROR", "نوع درخواست معتبر نیست.", [
        { field: "purpose", message: "نوع درخواست معتبر نیست." },
      ]);
    }
    const demoRole = sessionStorage.getItem(ROLE_KEY) || "donor";
    const challenge = {
      id: id(),
      phone,
      purpose: body.purpose,
      demo_role: demoRole === "center_operator" ? "center_operator" : "donor",
      code: DEMO_OTP,
      attempts: 0,
      expires_at: new Date(Date.now() + 120000).toISOString(),
      created_at: new Date().toISOString(),
    };
    db.challenges = db.challenges.filter((item) => item.phone !== phone);
    db.challenges.push(challenge);
    writeDb(db);
    return {
      status: 202,
      payload: envelope({
        challenge_id: challenge.id,
        expires_in_seconds: 120,
        resend_after_seconds: 60,
      }),
    };
  }

  if (path === "/auth/otp/verify" && method === "POST") {
    const phone = normalizePhone(body?.phone);
    const challenge = db.challenges.find((item) => item.id === body?.challenge_id);
    if (!challenge || challenge.phone !== phone) {
      fail(422, "VALIDATION_ERROR", "درخواست تأیید کد معتبر نیست.", [
        { field: "code", message: "درخواست تأیید کد معتبر نیست." },
      ]);
    }
    if (new Date(challenge.expires_at).getTime() < Date.now()) {
      fail(401, "UNAUTHENTICATED", "کد تأیید منقضی شده است. کد جدید بگیرید.");
    }
    if (challenge.attempts >= 5) {
      fail(429, "RATE_LIMITED", "تعداد تلاش‌ها بیش از حد مجاز است.");
    }
    if (String(body?.code) !== challenge.code) {
      challenge.attempts += 1;
      writeDb(db);
      fail(422, "VALIDATION_ERROR", "کد وارد شده درست نیست.", [
        { field: "code", message: "کد شش‌رقمی را بررسی کنید." },
      ]);
    }
    const role = challenge.demo_role || "donor";
    const user = db.users.find((item) => item.role === role);
    if (!user) {
      fail(500, "INTERNAL_ERROR", "حساب نمایشی برای این نقش یافت نشد.");
    }
    const accessToken = `demo-${role}-${crypto.randomUUID()}`;
    db.sessions[accessToken] = {
      user_id: user.id,
      phone,
      role,
      created_at: new Date().toISOString(),
    };
    db.challenges = db.challenges.filter((item) => item.id !== challenge.id);
    writeDb(db);
    const profile = findDonorProfile(db, user.id);
    return {
      status: 200,
      payload: envelope({
        access_token: accessToken,
        token_type: "bearer",
        expires_in: 3600,
        user: {
          id: user.id,
          phone,
          name: user.name,
          role: user.role,
          is_profile_complete: Boolean(profile && isProfileComplete(profile) && profile.sms_consent),
          center: user.center_id
            ? publicCenter(db.centers.find((item) => item.id === user.center_id))
            : null,
        },
      }),
    };
  }

  const { session, user } = currentSession(db, token);

  if (path === "/users/me" && method === "GET") {
    return { status: 200, payload: envelope(buildMe(db, session, user)) };
  }

  if (path === "/donors/me/profile" && method === "PATCH") {
    requireRole(session, ["donor"]);
    const profile = findDonorProfile(db, user.id);
    if (!profile) fail(404, "RESOURCE_NOT_FOUND", "پروفایل داوطلب یافت نشد.");

    const payload = body ?? {};
    if (payload.blood_group !== undefined && !["A", "B", "AB", "O"].includes(payload.blood_group)) {
      fail(422, "VALIDATION_ERROR", "گروه خونی معتبر نیست.", [
        { field: "blood_group", message: "گروه خونی معتبر نیست." },
      ]);
    }
    if (
      payload.rh_factor !== undefined &&
      !["positive", "negative"].includes(payload.rh_factor)
    ) {
      fail(422, "VALIDATION_ERROR", "Rh معتبر نیست.", [
        { field: "rh_factor", message: "Rh معتبر نیست." },
      ]);
    }
    if (payload.last_donation_date) {
      const date = new Date(payload.last_donation_date);
      if (Number.isNaN(date.getTime()) || date.getTime() > Date.now()) {
        fail(422, "VALIDATION_ERROR", "تاریخ آخرین اهدا معتبر نیست.", [
          { field: "last_donation_date", message: "تاریخ نمی‌تواند در آینده باشد." },
        ]);
      }
    }

    if (payload.blood_group !== undefined) profile.blood_group = payload.blood_group;
    if (payload.rh_factor !== undefined) profile.rh_factor = payload.rh_factor;
    if (payload.last_donation_date !== undefined) {
      profile.last_donation_date = payload.last_donation_date || null;
    }
    if (typeof payload.sms_consent === "boolean") profile.sms_consent = payload.sms_consent;
    if (typeof payload.location_consent === "boolean") {
      profile.location_consent = payload.location_consent;
      if (!payload.location_consent) {
        db.donor_locations = db.donor_locations.filter(
          (location) => location.donor_id !== profile.id,
        );
      }
    }
    writeDb(db);
    return {
      status: 200,
      payload: envelope({
        donor_id: profile.id,
        blood_group: profile.blood_group,
        rh_factor: profile.rh_factor,
        blood_type_verified: profile.blood_type_verified,
        last_donation_date: profile.last_donation_date,
        sms_consent: profile.sms_consent,
        location_consent: profile.location_consent,
      }),
    };
  }

  if (path === "/donors/me/availability" && method === "PATCH") {
    requireRole(session, ["donor"]);
    const profile = findDonorProfile(db, user.id);
    if (!profile) fail(404, "RESOURCE_NOT_FOUND", "پروفایل داوطلب یافت نشد.");
    const status = body?.status;
    if (!["available", "unavailable"].includes(status)) {
      fail(422, "VALIDATION_ERROR", "وضعیت آمادگی معتبر نیست.", [
        { field: "status", message: "وضعیت آمادگی معتبر نیست." },
      ]);
    }

    let availableFrom = null;
    let availableUntil = null;
    if (status === "available") {
      availableFrom = body?.available_from ?? nowPlus(0);
      availableUntil = body?.available_until ?? nowPlus(240);
      if (new Date(availableUntil).getTime() <= new Date(availableFrom).getTime()) {
        fail(422, "VALIDATION_ERROR", "بازه زمانی معتبر نیست.", [
          { field: "available_until", message: "پایان بازه باید بعد از شروع باشد." },
        ]);
      }
    }

    let availability = db.availability.find((item) => item.donor_id === profile.id);
    if (!availability) {
      availability = { id: id(), donor_id: profile.id };
      db.availability.push(availability);
    }
    availability.status = status;
    availability.available_from = availableFrom;
    availability.available_until = availableUntil;
    availability.updated_at = new Date().toISOString();
    writeDb(db);
    return {
      status: 200,
      payload: envelope({
        donor_id: profile.id,
        status: availability.status,
        available_from: availability.available_from,
        available_until: availability.available_until,
        updated_at: availability.updated_at,
      }),
    };
  }

  if (path === "/donors/me/location" && method === "PATCH") {
    requireRole(session, ["donor"]);
    const profile = findDonorProfile(db, user.id);
    if (!profile?.location_consent) {
      fail(403, "FORBIDDEN", "برای ثبت موقعیت، ابتدا رضایت مکان را فعال کنید.");
    }
    const latitude = Number(body?.latitude);
    const longitude = Number(body?.longitude);
    if (
      !Number.isFinite(latitude) ||
      latitude < -90 ||
      latitude > 90 ||
      !Number.isFinite(longitude) ||
      longitude < -180 ||
      longitude > 180
    ) {
      fail(422, "VALIDATION_ERROR", "مختصات معتبر نیست.", [
        { field: "latitude", message: "مختصات معتبر نیست." },
      ]);
    }
    let location = db.donor_locations.find((item) => item.donor_id === profile.id);
    if (!location) {
      location = { id: id(), donor_id: profile.id };
      db.donor_locations.push(location);
    }
    location.latitude = latitude;
    location.longitude = longitude;
    location.updated_at = new Date().toISOString();
    writeDb(db);
    return {
      status: 200,
      payload: envelope({
        donor_id: profile.id,
        latitude,
        longitude,
        updated_at: location.updated_at,
      }),
    };
  }

  if (path === "/centers" && method === "GET") {
    const activeCenters = db.centers.filter((center) => center.is_active);
    const paged = paginate(activeCenters, query);
    return {
      status: 200,
      payload: envelope(
        paged.items.map(publicCenter),
        paged.meta,
      ),
    };
  }

  const centerMatch = path.match(/^\/centers\/([^/]+)$/);
  if (centerMatch && method === "GET") {
    const center = db.centers.find((item) => item.id === centerMatch[1]);
    if (!center) fail(404, "RESOURCE_NOT_FOUND", "مرکز یافت نشد.");
    return { status: 200, payload: envelope(publicCenter(center)) };
  }

  if (path === "/blood-requests" && method === "GET") {
    requireRole(session, ["center_operator", "admin"]);
    let requests = db.blood_requests;
    if (session.role === "center_operator") {
      requests = requests.filter((request) => request.center_id === user.center_id);
    }
    requests = [...requests].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
    const paged = paginate(requests, query);
    return {
      status: 200,
      payload: envelope(
        paged.items.map((request) => enrichRequest(db, request)),
        paged.meta,
      ),
    };
  }

  if (path === "/blood-requests" && method === "POST") {
    requireRole(session, ["center_operator"]);
    if (body?.center_id !== user.center_id) {
      fail(403, "FORBIDDEN", "اجازه ثبت درخواست برای این مرکز را ندارید.");
    }
    validateRequestPayload(body);
    const request = {
      id: id(),
      center_id: user.center_id,
      component_type: body.component_type,
      blood_group: body.blood_group,
      rh_factor: body.rh_factor,
      units_needed: Number(body.units_needed),
      urgency: body.urgency,
      status: "draft",
      expires_at: body.expires_at,
      notes: body.notes ?? "",
      created_by: user.id,
      created_at: new Date().toISOString(),
      activated_at: null,
      dispatch_id: null,
      dispatched_at: null,
      candidate_count: 0,
      first_batch_size: 5,
    };
    db.blood_requests.unshift(request);
    writeDb(db);
    return {
      status: 201,
      payload: envelope(enrichRequest(db, request)),
    };
  }

  const requestMatch = path.match(/^\/blood-requests\/([^/]+)(?:\/([^/]+))?$/);
  if (requestMatch) {
    const request = db.blood_requests.find((item) => item.id === requestMatch[1]);
    if (!request) fail(404, "RESOURCE_NOT_FOUND", "درخواست یافت نشد.");
    if (user.role === "center_operator" && request.center_id !== user.center_id) {
      fail(403, "FORBIDDEN", "این درخواست متعلق به مرکز شما نیست.");
    }
    const action = requestMatch[2];

    if (!action && method === "GET") {
      requireRole(session, ["center_operator", "admin", "donor"]);
      return { status: 200, payload: envelope(enrichRequest(db, request)) };
    }

    if (!action && method === "PATCH") {
      requireRole(session, ["center_operator"]);
      if (request.status !== "draft") {
        fail(409, "CONFLICT", "فقط درخواست پیش‌نویس قابل ویرایش است.");
      }
      validateRequestPayload({ ...request, ...body, center_id: request.center_id });
      Object.assign(request, {
        component_type: body.component_type ?? request.component_type,
        blood_group: body.blood_group ?? request.blood_group,
        rh_factor: body.rh_factor ?? request.rh_factor,
        units_needed: body.units_needed ?? request.units_needed,
        urgency: body.urgency ?? request.urgency,
        expires_at: body.expires_at ?? request.expires_at,
        notes: body.notes ?? request.notes,
      });
      writeDb(db);
      return { status: 200, payload: envelope(enrichRequest(db, request)) };
    }

    if (action === "activate" && method === "POST") {
      requireRole(session, ["center_operator"]);
      if (request.status !== "draft") {
        fail(409, "CONFLICT", "فقط درخواست پیش‌نویس قابل فعال‌سازی است.");
      }
      request.status = "active";
      request.activated_at = new Date().toISOString();
      writeDb(db);
      return {
        status: 200,
        payload: envelope({
          id: request.id,
          status: request.status,
          activated_at: request.activated_at,
        }),
      };
    }

    if (action === "cancel" && method === "POST") {
      requireRole(session, ["center_operator"]);
      if (["fulfilled", "cancelled", "expired"].includes(request.status)) {
        fail(409, "CONFLICT", "این درخواست در وضعیت نهایی است.");
      }
      request.status = "cancelled";
      db.notifications
        .filter((notification) => notification.request_id === request.id && !notification.response)
        .forEach((notification) => {
          notification.status = "cancelled";
        });
      writeDb(db);
      return {
        status: 200,
        payload: envelope({ id: request.id, status: request.status }),
      };
    }

    if (action === "dispatch" && method === "POST") {
      requireRole(session, ["center_operator"]);
      if (request.status !== "active") {
        fail(409, "CONFLICT", "فراخوان فقط برای درخواست فعال ممکن است.");
      }
      if (request.dispatch_id) {
        fail(409, "CONFLICT", "فراخوان این درخواست قبلاً آغاز شده است.");
      }
      const candidateList = makeCandidateList(request.id);
      db.candidates[request.id] = candidateList;
      request.dispatch_id = id();
      request.dispatched_at = new Date().toISOString();
      request.candidate_count = candidateList.length;
      request.first_batch_size = 5;

      const donor = db.donor_profiles[0];
      const hasNotification = db.notifications.some(
        (notification) => notification.request_id === request.id && notification.donor_id === donor.id,
      );
      if (!hasNotification) {
        db.notifications.push({
          id: id(),
          request_id: request.id,
          donor_id: donor.id,
          channel: "sms",
          status: "delivered",
          idempotency_key: `dispatch:${request.id}:${donor.id}`,
          provider_message_id: `mock-${Math.floor(Math.random() * 90000) + 10000}`,
          eta_minutes: 12,
          distance_km: 2.1,
          created_at: new Date().toISOString(),
          expires_at: request.expires_at,
          response: null,
          responded_at: null,
        });
      }
      writeDb(db);
      return {
        status: 202,
        payload: envelope({
          dispatch_id: request.dispatch_id,
          request_id: request.id,
          status: "queued",
          candidate_count: candidateList.length,
          first_batch_size: 5,
        }),
      };
    }

    if (action === "candidates" && method === "GET") {
      requireRole(session, ["center_operator", "admin"]);
      const items = db.candidates[request.id] ?? [];
      return { status: 200, payload: envelope(items, { total: items.length }) };
    }

    if (action === "responses" && method === "GET") {
      requireRole(session, ["center_operator", "admin"]);
      const items = db.donor_responses
        .filter((response) => response.request_id === request.id)
        .sort((a, b) => new Date(b.responded_at).getTime() - new Date(a.responded_at).getTime());
      return { status: 200, payload: envelope(items, { total: items.length }) };
    }
  }

  if (path === "/notifications" && method === "GET") {
    requireRole(session, ["donor"]);
    const profile = findDonorProfile(db, user.id);
    if (!profile) fail(404, "RESOURCE_NOT_FOUND", "پروفایل داوطلب یافت نشد.");
    const items = db.notifications
      .filter((notification) => notification.donor_id === profile.id)
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .map((notification) => enrichNotification(db, notification));
    return { status: 200, payload: envelope(items, { total: items.length }) };
  }

  const notificationMatch = path.match(/^\/notifications\/([^/]+)\/response$/);
  if (notificationMatch && method === "POST") {
    requireRole(session, ["donor"]);
    const profile = findDonorProfile(db, user.id);
    const notification = db.notifications.find((item) => item.id === notificationMatch[1]);
    if (!notification) fail(404, "RESOURCE_NOT_FOUND", "اعلان یافت نشد.");
    if (notification.donor_id !== profile?.id) {
      fail(403, "FORBIDDEN", "این اعلان متعلق به شما نیست.");
    }
    if (notification.response) {
      fail(409, "CONFLICT", "برای این اعلان قبلاً پاسخ ثبت شده است.");
    }
    if (!["interested", "unavailable"].includes(body?.response)) {
      fail(422, "VALIDATION_ERROR", "پاسخ معتبر نیست.", [
        { field: "response", message: "پاسخ معتبر نیست." },
      ]);
    }
    if (new Date(notification.expires_at).getTime() < Date.now()) {
      fail(409, "CONFLICT", "مهلت پاسخ به این فراخوان پایان یافته است.");
    }

    notification.response = body.response;
    notification.responded_at = new Date().toISOString();
    const donorResponse = {
      id: id(),
      notification_id: notification.id,
      request_id: notification.request_id,
      donor_reference: "D-1042",
      response: body.response,
      responded_at: notification.responded_at,
      eta_minutes: notification.eta_minutes,
    };
    db.donor_responses.push(donorResponse);
    writeDb(db);
    return {
      status: 201,
      payload: envelope({
        notification_id: notification.id,
        response: notification.response,
        responded_at: notification.responded_at,
      }),
    };
  }

  fail(404, "RESOURCE_NOT_FOUND", "مسیر درخواستی در سرور نمایشی وجود ندارد.");
}

export async function mockRequest(path, { method = "GET", body, token } = {}) {
  await sleep(DEMO_LATENCY + Math.random() * 180);
  const [rawPath, rawQuery = ""] = path.split("?");
  const normalized = rawPath.startsWith("/") ? rawPath : `/${rawPath}`;
  try {
    return handle(normalized.replace(/\/+$/, "") || "/", method.toUpperCase(), body, new URLSearchParams(rawQuery), token);
  } catch (error) {
    if (error instanceof MockApiError) throw error;
    console.error("[mock-api]", error);
    fail(500, "INTERNAL_ERROR", "خطای داخلی سرور نمایشی.");
  }
}
