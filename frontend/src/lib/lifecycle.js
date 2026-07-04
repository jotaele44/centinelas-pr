export const APP_NAME = "Centinelas";
export const SIBLING_APP_NAME = "MoneySweep";

export const MATTER_LIFECYCLE_STAGES = [
  { key: "raw_observation", order: 0, app: "Centinelas", label: "Observación cruda" },
  { key: "public_signal", order: 1, app: "Centinelas", label: "Señal pública" },
  { key: "developing_matter", order: 2, app: "Centinelas", label: "Asunto en desarrollo" },
  { key: "pending_officialization", order: 3, app: "Centinelas", label: "Pendiente de oficialización" },
  { key: "officialized", order: 4, app: "MoneySweep", label: "Oficializado" },
  { key: "execution_amendment", order: 5, app: "MoneySweep", label: "Ejecución / enmienda" },
  { key: "audit_dispute_impact", order: 6, app: "Ambas", label: "Auditoría / disputa / impacto" },
];

export const SIGNAL_TYPES = [
  "announcement",
  "agenda_item",
  "hearing",
  "rfp_notice",
  "draft_bill",
  "public_notice",
  "board_meeting",
  "press_release",
  "social_statement",
  "budget_line",
  "permit_notice",
  "court_signal",
  "emergency_notice",
  "media_report",
  "community_tip",
];

export const MATTER_TYPES = [
  "law",
  "contract",
  "permit",
  "public_project",
  "procurement",
  "budget_allocation",
  "court_case",
  "audit",
  "appointment",
  "emergency",
  "infrastructure_event",
  "policy_change",
  "grant",
  "municipal_action",
  "environmental_notice",
];

export const OFFICIAL_RECORD_TYPES = [
  "law_record",
  "contract_record",
  "payment_record",
  "permit_record",
  "audit_record",
  "court_record",
  "amendment_record",
  "grant_award",
  "official_appointment",
  "executive_order",
];

export const HANDOFF_TRIGGERS = [
  "law_number_assigned",
  "contract_awarded",
  "signed_contract_published",
  "payment_issued",
  "permit_number_issued",
  "court_case_number_assigned",
  "audit_report_published",
  "grant_obligation_published",
  "appointment_confirmed",
  "executive_order_published",
];

export const PRE_OFFICIAL_LANGUAGE_GUARD = {
  blockedOfficialClaims: [
    "aprobado definitivamente",
    "contrato adjudicado",
    "ley vigente",
    "fondos desembolsados",
    "permiso emitido",
    "caso radicado",
    "auditoría final",
    "officially approved",
    "contract awarded",
    "funds disbursed",
    "permit issued",
    "case filed",
  ],
  approvedSignalLanguage: [
    "anunciado",
    "propuesto",
    "programado",
    "bajo consideración",
    "pendiente",
    "incluido en agenda",
    "abierto a subasta",
    "reportado por fuente",
    "requiere verificación oficial",
  ],
};

export const EVIDENCE_TIERS = {
  T1: "Documento primario, contrato, ley, docket, dataset, informe oficial o captura verificable.",
  T2: "Fuente operacional u oficial secundaria: comunicado, agenda, minuta, agencia, junta, municipio.",
  T3: "Testigo, entrevista, soplo o comunicación directa no documental.",
  T4: "Medio, comentario, agregador, republicación o fuente secundaria no primaria.",
};

export function getConfidenceBand(score = 0) {
  const normalized = Number(score) || 0;
  if (normalized >= 95) return { label: "T1 confirmado", tone: "strong", description: "Documento primario u oficial verificable." };
  if (normalized >= 85) return { label: "Oficial preliminar", tone: "high", description: "Fuente oficial, pero aún pre-oficialización." };
  if (normalized >= 70) return { label: "Corroborado", tone: "medium", description: "Múltiples señales o medio confiable con fuente identificable." };
  if (normalized >= 50) return { label: "Monitor", tone: "watch", description: "Señal útil, pendiente de confirmación adicional." };
  if (normalized >= 30) return { label: "Débil", tone: "low", description: "Una fuente indirecta o incompleta." };
  return { label: "No publicar como hecho", tone: "hold", description: "Solo lead interno hasta verificación." };
}

export function slugify(value = "") {
  return String(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

export function createMatterId({ matterType = "matter", jurisdiction = "PR", title = "", firstSeenAt = "" }) {
  const cleanTitle = slugify(title).slice(0, 48) || "untitled";
  const date = firstSeenAt ? String(firstSeenAt).slice(0, 10).replace(/-/g, "") : "undated";
  return `${jurisdiction.toUpperCase()}-${matterType.toUpperCase()}-${date}-${cleanTitle}`;
}

export function normalizeMatterId(input = {}) {
  if (input.matter_id) return String(input.matter_id).trim();
  return createMatterId({
    matterType: input.matter_type || input.record_type || "matter",
    jurisdiction: input.jurisdiction || "PR",
    title: input.title || input.official_identifier || "untitled",
    firstSeenAt: input.first_seen_at || input.published_at || input.effective_date || input.created_date || "",
  });
}

export function createOfficialRecordKey(record = {}) {
  const matterId = normalizeMatterId(record);
  const type = slugify(record.record_type || "official_record");
  const identifier = slugify(record.official_identifier || record.document_hash || record.official_source_url || record.title || "unknown");
  return `${matterId}::${type}::${identifier}`;
}

export function getLifecycleStage(stageKey) {
  return MATTER_LIFECYCLE_STAGES.find((stage) => stage.key === stageKey) || MATTER_LIFECYCLE_STAGES[1];
}

export function isReadyForMoneySweep(matter = {}, signals = []) {
  const triggers = new Set([...(matter.handoff_triggers || []), ...signals.flatMap((signal) => signal.handoff_triggers || [])]);
  const hasTrigger = HANDOFF_TRIGGERS.some((trigger) => triggers.has(trigger));
  const hasOfficialIdentifier = Boolean(matter.official_identifier || matter.official_source_url);
  const stage = getLifecycleStage(matter.status_lifecycle);
  return hasTrigger || hasOfficialIdentifier || stage.order >= 4;
}

export function validatePreOfficialLanguage(text = "", lifecycleStage = "public_signal") {
  const stage = getLifecycleStage(lifecycleStage);
  const normalizedText = String(text).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const blockedMatches = PRE_OFFICIAL_LANGUAGE_GUARD.blockedOfficialClaims.filter((phrase) => {
    const normalizedPhrase = phrase.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    return normalizedText.includes(normalizedPhrase);
  });

  if (stage.order < 4 && blockedMatches.length > 0) {
    return {
      status: "blocked_official_claim",
      blocked_matches: blockedMatches,
      message: "El lenguaje afirma oficialización antes de existir registro canónico MoneySweep.",
    };
  }

  return {
    status: blockedMatches.length > 0 ? "needs_review" : "clean",
    blocked_matches: blockedMatches,
    message: blockedMatches.length > 0 ? "Lenguaje permitido solo si el asunto ya está oficializado." : "Lenguaje compatible con estado pre-oficial.",
  };
}

export function buildRecordDraftFromHandoff({ matter = {}, signals = [], candidate = {} }) {
  const matterId = normalizeMatterId(matter);
  const title = matter.title || candidate.title || "Registro oficial pendiente";
  const officialIdentifier = matter.official_identifier || candidate.official_identifier || "";
  const recordType = candidate.target_record_type || inferRecordType(matter.matter_type);
  const recordDraft = {
    record_id: candidate.moneysweep_record_id || `record-${matterId}-${Date.now()}`,
    matter_id: matterId,
    record_type: recordType,
    title,
    official_identifier: officialIdentifier,
    official_source_url: matter.official_source_url || candidate.official_source_url || "",
    amount_confirmed: matter.amount_confirmed,
    parties: [...(matter.agencies || []), ...(matter.organizations || [])].filter(Boolean),
    linked_signal_ids: signals.map((signal) => signal.signal_id || signal.id).filter(Boolean),
    linked_candidate_id: candidate.candidate_id || candidate.id || "",
    source_app: SIBLING_APP_NAME,
    sync_status: "pending_sync",
  };
  return { ...recordDraft, canonical_key: createOfficialRecordKey(recordDraft) };
}

export function inferRecordType(matterType) {
  switch (matterType) {
    case "law":
      return "law_record";
    case "permit":
      return "permit_record";
    case "court_case":
      return "court_record";
    case "audit":
      return "audit_record";
    case "grant":
      return "grant_award";
    case "appointment":
      return "official_appointment";
    default:
      return "contract_record";
  }
}

export function mapLegacyLawToSignal(law = {}) {
  const firstSeenAt = law.submission_date || law.created_date || law.last_action_date;
  const title = law.title || law.bill_number || "Medida legislativa sin título";
  const matterId = law.matter_id || createMatterId({ matterType: "law", title, firstSeenAt });

  return {
    id: law.id,
    signal_id: law.signal_id || `legacy-law-${law.id}`,
    matter_id: matterId,
    signal_type: "draft_bill",
    title,
    summary: law.description || "Medida legislativa importada desde el modelo Law heredado.",
    source_name: "Legislatura / Law legacy entity",
    published_at: law.submission_date || law.created_date,
    captured_at: law.created_date,
    signal_stage: law.status === "Ley" || law.status === "Aprobada" ? "pending_officialization" : "developing_matter",
    beat: law.category || "government",
    municipalities: law.municipalities || [],
    agencies: law.officials || [],
    entities: [...(law.officials || []), ...(law.lobbyists || [])],
    confidence_score: law.status === "Ley" ? 90 : 75,
    evidence_tier: "T2",
    source_url: law.official_source_url || law.url || "",
    handoff_status: law.status === "Ley" ? "ready_for_moneysweep" : "watching",
  };
}

export function mapLegacyLawToMatter(law = {}) {
  const signal = mapLegacyLawToSignal(law);
  const matter = {
    matter_id: signal.matter_id,
    canonical_key: signal.matter_id,
    jurisdiction: "PR",
    title: signal.title,
    matter_type: "law",
    status_lifecycle: signal.handoff_status === "ready_for_moneysweep" ? "pending_officialization" : "developing_matter",
    first_seen_at: signal.published_at || signal.captured_at,
    municipalities: signal.municipalities,
    agencies: signal.agencies,
    people: [],
    organizations: signal.entities,
    source_count: 1,
    confidence_score: signal.confidence_score,
    centinelas_signal_ids: [signal.signal_id],
    moneysweep_record_ids: [],
    official_identifier: law.law_number || "",
    official_source_url: law.official_source_url || "",
    moneysweep_sync_status: "not_synced",
  };
  return matter;
}
