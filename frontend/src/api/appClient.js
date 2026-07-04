import { seedData } from "@/data/seedData";
import {
  buildRecordDraftFromHandoff,
  createOfficialRecordKey,
  isReadyForMoneySweep,
  normalizeMatterId,
  validatePreOfficialLanguage,
} from "@/lib/lifecycle";

const STORAGE_KEY = "centinelas_local_store_v1";
const AUTH_KEY = "centinelas_local_auth_v1";
const DEFAULT_USER = {
  id: "local-admin",
  email: "local@centinelas.test",
  full_name: "Local Centinelas Admin",
  role: "admin",
};

const clone = (value) => JSON.parse(JSON.stringify(value));

function withTimestamps(record = {}, isNew = false) {
  const now = new Date().toISOString();
  return {
    ...(isNew && !record.id ? { id: `local-${crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`}` } : {}),
    ...(isNew && !record.created_date ? { created_date: now } : {}),
    ...record,
    updated_date: now,
  };
}

function readStore() {
  if (typeof window === "undefined") return clone(seedData);
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    const initial = clone(seedData);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(initial));
    return initial;
  }
  try {
    return { ...clone(seedData), ...JSON.parse(raw) };
  } catch (_error) {
    const initial = clone(seedData);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(initial));
    return initial;
  }
}

function writeStore(store) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  }
  return store;
}

function getCollection(store, entityName) {
  if (!store[entityName]) store[entityName] = [];
  return store[entityName];
}

function compareValues(a, b) {
  if (a == null && b == null) return 0;
  if (a == null) return -1;
  if (b == null) return 1;
  const dateA = Date.parse(a);
  const dateB = Date.parse(b);
  if (!Number.isNaN(dateA) && !Number.isNaN(dateB)) return dateA - dateB;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b));
}

function sortRows(rows, sort = "-created_date") {
  if (!sort) return rows;
  const desc = String(sort).startsWith("-");
  const field = desc ? String(sort).slice(1) : String(sort);
  return [...rows].sort((left, right) => {
    const result = compareValues(left[field], right[field]);
    return desc ? -result : result;
  });
}

function matchesCriteria(record, criteria = {}) {
  return Object.entries(criteria || {}).every(([key, expected]) => {
    if (Array.isArray(expected)) return expected.includes(record[key]);
    return record[key] === expected;
  });
}

function makeEntityClient(entityName) {
  return {
    async list(sort = "-created_date", limit = 1000) {
      const store = readStore();
      return clone(sortRows(getCollection(store, entityName), sort).slice(0, limit));
    },
    async filter(criteria = {}, sort = "-created_date", limit = 1000) {
      const store = readStore();
      const rows = getCollection(store, entityName).filter((row) => matchesCriteria(row, criteria));
      return clone(sortRows(rows, sort).slice(0, limit));
    },
    async get(id) {
      const store = readStore();
      const row = getCollection(store, entityName).find((item) => item.id === id || item[`${entityName.toLowerCase()}_id`] === id);
      if (!row) throw new Error(`${entityName} not found: ${id}`);
      return clone(row);
    },
    async create(data = {}) {
      const store = readStore();
      const collection = getCollection(store, entityName);
      const row = withTimestamps(data, true);
      collection.push(row);
      writeStore(store);
      return clone(row);
    },
    async update(id, patch = {}) {
      const store = readStore();
      const collection = getCollection(store, entityName);
      const index = collection.findIndex((item) => item.id === id || item[`${entityName.toLowerCase()}_id`] === id);
      if (index === -1) throw new Error(`${entityName} not found: ${id}`);
      collection[index] = withTimestamps({ ...collection[index], ...patch });
      writeStore(store);
      return clone(collection[index]);
    },
    async delete(id) {
      const store = readStore();
      const collection = getCollection(store, entityName);
      const index = collection.findIndex((item) => item.id === id || item[`${entityName.toLowerCase()}_id`] === id);
      if (index === -1) return { deleted: false };
      const [deleted] = collection.splice(index, 1);
      writeStore(store);
      return { deleted: true, id: deleted.id };
    },
    subscribe() {
      return () => undefined;
    },
  };
}

const ENTITY_NAMES = [
  "AlertEvent",
  "AlertRule",
  "Author",
  "Beat",
  "Comment",
  "CoverageGap",
  "EditorialNote",
  "Entity",
  "EntityMention",
  "Evidence",
  "HandoffCandidate",
  "Law",
  "Matter",
  "Municipality",
  "OfficialRecord",
  "Signal",
  "Source",
  "Story",
  "Subscription",
  "User",
  "Vote",
  "Watchlist",
];

function buildEntities() {
  return Object.fromEntries(ENTITY_NAMES.map((entityName) => [entityName, makeEntityClient(entityName)]));
}

function readAuth() {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(AUTH_KEY);
  return raw ? JSON.parse(raw) : null;
}

function writeAuth(user) {
  if (typeof window !== "undefined") {
    if (user) window.localStorage.setItem(AUTH_KEY, JSON.stringify(user));
    else window.localStorage.removeItem(AUTH_KEY);
  }
}

const entities = buildEntities();

async function findMatter(matterId) {
  const normalized = normalizeMatterId({ matter_id: matterId });
  const matters = await entities.Matter.filter({ matter_id: normalized });
  return matters[0] || null;
}

async function findCandidate({ candidate_id, matter_id }) {
  if (candidate_id) {
    const rows = await entities.HandoffCandidate.filter({ candidate_id });
    if (rows[0]) return rows[0];
    try { return await entities.HandoffCandidate.get(candidate_id); } catch (_error) { /* noop */ }
  }
  if (matter_id) {
    const rows = await entities.HandoffCandidate.filter({ matter_id });
    return rows[0] || null;
  }
  return null;
}

async function findDuplicateOfficialRecord(record) {
  const canonicalKey = record.canonical_key || createOfficialRecordKey(record);
  const byKey = await entities.OfficialRecord.filter({ canonical_key: canonicalKey });
  if (byKey[0]) return byKey[0];
  const byMatter = await entities.OfficialRecord.filter({ matter_id: record.matter_id });
  return byMatter.find((existing) =>
    existing.record_type === record.record_type &&
    existing.official_identifier &&
    existing.official_identifier === record.official_identifier
  ) || null;
}

const functionHandlers = {
  async evaluateHandoffCandidate({ matter_id }) {
    const matter = await findMatter(matter_id);
    if (!matter) throw new Error(`Matter not found: ${matter_id}`);
    const signals = await entities.Signal.filter({ matter_id: matter.matter_id });
    if (!isReadyForMoneySweep(matter, signals)) {
      return { status: "not_ready", matter_id: matter.matter_id };
    }
    const existing = await findCandidate({ matter_id: matter.matter_id });
    if (existing) return { status: "existing", candidate: existing };
    const candidate = await entities.HandoffCandidate.create({
      candidate_id: `handoff-${matter.matter_id}-${Date.now()}`,
      matter_id: matter.matter_id,
      title: matter.title,
      target_app: "MoneySweep",
      target_record_type: "official_record",
      status: "ready_for_review",
      reason: "Centinelas detected officialization trigger or official identifier.",
      trigger_summary: (matter.handoff_triggers || []).join(", ") || "officialization_candidate",
      linked_signal_ids: signals.map((signal) => signal.signal_id || signal.id).filter(Boolean),
      confidence_score: matter.confidence_score || 0,
    });
    await entities.Matter.update(matter.id, {
      last_handoff_candidate_id: candidate.candidate_id,
      moneysweep_sync_status: "handoff_ready",
    });
    return { status: "created", candidate };
  },

  async acceptHandoffCandidate(payload = {}) {
    const matterId = normalizeMatterId({ matter_id: payload.matter_id || payload.official_record?.matter_id });
    const matter = await findMatter(matterId);
    if (!matter) throw new Error(`Matter not found: ${matterId}`);
    const signals = await entities.Signal.filter({ matter_id: matter.matter_id });
    const candidate = await findCandidate({ candidate_id: payload.candidate_id, matter_id: matter.matter_id }) || payload;
    const draft = buildRecordDraftFromHandoff({ matter, signals, candidate: { ...candidate, ...(payload.official_record || {}) } });
    const record = { ...draft, ...(payload.official_record || {}) };
    record.matter_id = matter.matter_id;
    record.canonical_key = createOfficialRecordKey(record);

    const duplicate = await findDuplicateOfficialRecord(record);
    let officialRecord;
    if (duplicate) {
      officialRecord = await entities.OfficialRecord.update(duplicate.id, {
        ...record,
        linked_signal_ids: Array.from(new Set([...(duplicate.linked_signal_ids || []), ...(record.linked_signal_ids || [])])),
        sync_status: "linked_existing",
      });
    } else {
      officialRecord = await entities.OfficialRecord.create({
        ...record,
        record_id: record.record_id || `record-${matter.matter_id}-${Date.now()}`,
        sync_status: "created_local",
      });
    }

    if (candidate?.id) {
      await entities.HandoffCandidate.update(candidate.id, {
        status: duplicate ? "linked_existing_record" : "accepted_created_record",
        moneysweep_record_id: officialRecord.record_id || officialRecord.id,
      });
    }

    await entities.Matter.update(matter.id, {
      status_lifecycle: "officialized",
      moneysweep_sync_status: "synced_local",
      moneysweep_record_ids: Array.from(new Set([...(matter.moneysweep_record_ids || []), officialRecord.record_id || officialRecord.id])),
    });

    await Promise.all(signals.map((signal) => entities.Signal.update(signal.id, { handoff_status: "matched_to_moneysweep" })));
    return { status: duplicate ? "linked_existing" : "created", official_record: officialRecord };
  },

  async rejectHandoffCandidate({ candidate_id, matter_id, reason }) {
    const candidate = await findCandidate({ candidate_id, matter_id });
    if (!candidate) throw new Error("Handoff candidate not found");
    const updated = await entities.HandoffCandidate.update(candidate.id, {
      status: "rejected",
      reviewer_note: reason || "Rejected from Centinelas UI.",
    });
    return { status: "rejected", candidate: updated };
  },

  async syncMoneySweepRecord(payload = {}) {
    const record = {
      ...payload,
      matter_id: normalizeMatterId(payload),
    };
    record.canonical_key = createOfficialRecordKey(record);
    const duplicate = await findDuplicateOfficialRecord(record);
    const officialRecord = duplicate
      ? await entities.OfficialRecord.update(duplicate.id, { ...duplicate, ...record, sync_status: "updated_from_moneysweep" })
      : await entities.OfficialRecord.create({ ...record, record_id: record.record_id || `record-${record.matter_id}-${Date.now()}`, sync_status: "created_from_moneysweep" });
    const matter = await findMatter(officialRecord.matter_id);
    if (matter) {
      await entities.Matter.update(matter.id, {
        status_lifecycle: "officialized",
        moneysweep_sync_status: "synced_local",
        moneysweep_record_ids: Array.from(new Set([...(matter.moneysweep_record_ids || []), officialRecord.record_id || officialRecord.id])),
      });
    }
    return { status: duplicate ? "updated" : "created", official_record: officialRecord };
  },

  async validatePreOfficialLanguage(payload = {}) {
    const text = payload.text || [payload.title, payload.summary, payload.body].filter(Boolean).join("\n");
    return validatePreOfficialLanguage(text, payload.lifecycle_stage || payload.status_lifecycle || "public_signal");
  },
};

export const appClient = {
  entities,
  auth: {
    async me() {
      return readAuth() || DEFAULT_USER;
    },
    async loginViaEmailPassword(email) {
      const user = { ...DEFAULT_USER, id: `local-${email}`, email, full_name: email };
      writeAuth(user);
      return { access_token: `local-token-${Date.now()}`, user };
    },
    async register({ email }) {
      return { status: "otp_required", email };
    },
    async verifyOtp({ email }) {
      const user = { ...DEFAULT_USER, id: `local-${email}`, email, full_name: email };
      writeAuth(user);
      return { access_token: `local-token-${Date.now()}`, user };
    },
    async resendOtp() {
      return { status: "sent" };
    },
    async resetPasswordRequest() {
      return { status: "sent" };
    },
    async resetPassword() {
      return { status: "reset" };
    },
    loginWithProvider(_provider, redirectTo = "/") {
      writeAuth(DEFAULT_USER);
      window.location.href = redirectTo;
    },
    logout(redirectTo) {
      writeAuth(null);
      if (redirectTo) window.location.href = redirectTo;
    },
    setToken() {
      writeAuth(DEFAULT_USER);
    },
    redirectToLogin() {
      window.location.href = "/login";
    },
  },
  functions: {
    async invoke(name, payload = {}) {
      const handler = functionHandlers[name];
      if (!handler) {
        return { status: "noop", function: name, payload };
      }
      return handler(payload);
    },
  },
  storage: {
    reset() {
      if (typeof window !== "undefined") window.localStorage.removeItem(STORAGE_KEY);
    },
    dump() {
      return readStore();
    },
  },
};
