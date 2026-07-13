// English translations keyed by the Spanish canonical string used in the UI.
// A missing key falls back to the Spanish text (see LanguageContext `t`).
// Keys must match the argument passed to t(...) exactly, including punctuation,
// the "…" ellipsis, ":" suffixes, and the "→" arrow.
export const EN = {
  // Header / nav / chrome
  "Monitor": "Monitor",
  "Señales": "Signals",
  "Asuntos": "Matters",
  "Fuentes": "Sources",
  "Pipeline": "Pipeline",
  "Handoff": "Handoff",
  "Señal temprana → MoneySweep": "Early signal → MoneySweep",
  "Navegación principal": "Main navigation",
  "Navegación móvil": "Mobile navigation",
  "Abrir navegación": "Open navigation",
  "Cerrar navegación": "Close navigation",
  "Cambiar a modo claro": "Switch to light mode",
  "Cambiar a modo oscuro": "Switch to dark mode",
  "Modo claro": "Light mode",
  "Modo oscuro": "Dark mode",
  "Cambiar idioma": "Change language",
  "Monitor de señales públicas tempranas para Puerto Rico. Sibling upstream de MoneySweep.":
    "Early public-signal monitor for Puerto Rico. Upstream sibling of MoneySweep.",

  // Home
  "Monitor temprano de información pública relevante a Puerto Rico":
    "Early monitor of public information relevant to Puerto Rico",
  "Captura lo que se anuncia, agenda, propone o notifica antes de que el proyecto, ley, contrato, permiso, pago o auditoría quede oficializado. MoneySweep cataloga el mismo asunto después de la oficialización.":
    "Captures what is announced, scheduled, proposed or noticed before a project, law, contract, permit, payment or audit becomes official. MoneySweep catalogs the same matter after officialization.",
  "Abrir monitor": "Open monitor",
  "Ver handoff MoneySweep": "View MoneySweep handoff",
  "Upstream": "Upstream",
  "Downstream": "Downstream",
  "Reporting": "Reporting",
  "Centinelas registra señales: anuncios, agendas, RFP, vistas, comunicados, avisos, minutas y declaraciones públicas.":
    "Centinelas records signals: announcements, agendas, RFPs, hearings, press releases, notices, minutes and public statements.",
  "MoneySweep registra el hecho oficial: contrato, ley, permiso, pago, auditoría, docket, enmienda o informe final.":
    "MoneySweep records the official fact: contract, law, permit, payment, audit, docket, amendment or final report.",
  "El Matter ID une señales, evidencia, leads editoriales y registros oficiales en una línea de vida verificable.":
    "The Matter ID links signals, evidence, editorial leads and official records into a verifiable lifeline.",

  // Monitor
  "Monitor temprano de información pública de Puerto Rico":
    "Early monitor of Puerto Rico public information",
  "Captura señales antes de que se conviertan en ley, contrato, permiso, pago, auditoría o expediente oficial. MoneySweep cataloga el registro oficial posterior.":
    "Captures signals before they become a law, contract, permit, payment, audit or official record. MoneySweep catalogs the subsequent official record.",
  "Ver handoff": "View handoff",
  "Señales capturadas": "Signals captured",
  "Upstream: anuncios, agendas, RFP, vistas, avisos.": "Upstream: announcements, agendas, RFPs, hearings, notices.",
  "Asuntos públicos": "Public matters",
  "Objetos compartidos con MoneySweep.": "Objects shared with MoneySweep.",
  "Listos para MoneySweep": "Ready for MoneySweep",
  "Oficialización detectada o candidata.": "Officialization detected or candidate.",
  "Fuentes con brecha": "Sources with gaps",
  "Manual, rota o atrasada.": "Manual, broken or stale.",
  "Bandeja de señales": "Signal inbox",
  "Ver todas": "View all",

  // Signals
  "Información que aparece antes de oficializarse como contrato, ley, pago, permiso, auditoría o expediente.":
    "Information that appears before becoming official as a contract, law, payment, permit, audit or record.",
  "Buscar señales": "Search signals",
  "agencia, municipio, RFP, vista, contrato…": "agency, municipality, RFP, hearing, contract…",
  "Todos": "All",
  "En observación": "Watching",
  "Candidato": "Candidate",
  "Listo para MoneySweep": "Ready for MoneySweep",
  "Vinculado": "Matched",

  // Matters
  "Objeto compartido entre Centinelas y MoneySweep. Une la señal temprana con el registro oficial posterior.":
    "Object shared between Centinelas and MoneySweep. Links the early signal with the subsequent official record.",
  "Primer visto:": "First seen:",
  "sin fecha": "no date",
  "Fuentes:": "Sources:",
  "record(s)": "record(s)",

  // MatterDetail
  "Cargando asunto…": "Loading matter…",
  "No se pudo cargar el asunto. Revisa la conexión con el almacén de datos e inténtalo de nuevo.":
    "Could not load the matter. Check the connection to the data store and try again.",
  "Asunto no encontrado.": "Matter not found.",
  "Señales Centinelas": "Centinelas signals",
  "No hay señales vinculadas.": "No linked signals.",
  "Panel MoneySweep": "MoneySweep panel",
  "Registros oficiales vinculados:": "Linked official records:",
  "Identificador oficial:": "Official identifier:",
  "pendiente": "pending",
  "URL oficial:": "Official URL:",
  "capturada": "captured",
  "Regla de lenguaje": "Language rule",
  "Mientras no exista registro oficial, describir como anunciado, propuesto, programado, bajo consideración o pendiente de oficialización.":
    "Until an official record exists, describe as announced, proposed, scheduled, under consideration or pending officialization.",

  // Handoff
  "Handoff hacia MoneySweep": "Handoff to MoneySweep",
  "Asuntos donde Centinelas detectó señal de oficialización y debe crearse o vincularse un registro canónico posterior.":
    "Matters where Centinelas detected an officialization signal and a subsequent canonical record should be created or linked.",
  "Disparadores aceptados": "Accepted triggers",
  "Tipo:": "Type:",
  "Señales:": "Signals:",
  "Oficial:": "Official:",
  "requiere vinculación": "requires linking",
  "Evaluar": "Evaluate",
  "Aceptar / crear registro": "Accept / create record",
  "Rechazar": "Reject",

  // Sources
  "Registro de fuentes": "Source registry",
  "Cobertura upstream: fuentes que anuncian, agendan, notifican o anticipan asuntos antes de oficializarse.":
    "Upstream coverage: sources that announce, schedule, notify or anticipate matters before they become official.",
  "Buscar fuente": "Search source",
  "legislatura, municipio, subasta, tribunal…": "legislature, municipality, procurement, court…",
  "sin tipo": "no type",
  "Estado:": "Status:",
  "Último éxito:": "Last success:",

  // Pipeline
  "Admisión universal": "Universal intake",
  "Contenido en línea clasificado en seis dominios y despachado a los repositorios de la federación correspondientes. Cada item también se registra en thehub-pr sin importar la clasificación.":
    "Online content classified across six domains and dispatched to the corresponding federation repositories. Every item is also logged to thehub-pr regardless of classification.",
  "Clasificados:": "Classified:",
  "Despachados:": "Dispatched:",
  "En cola:": "Queue:",
  "Backend no accesible": "Backend not reachable",
  "Inicia el API de admisión desde la raíz del repositorio:": "Start the intake API from the repo root:",
  "Cargando items…": "Loading items…",
  "No hay items clasificados": "No classified items",
  "Ejecuta el pipeline con": "Run the pipeline with",
  "para poblarlo.": "to populate.",

  // Lifecycle / shared components
  "Línea de vida del asunto": "Matter lifeline",
  "Centinelas detecta intención; MoneySweep verifica ejecución oficial.":
    "Centinelas detects intent; MoneySweep verifies official execution.",
  "Etapa": "Stage",
  "Centinelas": "Centinelas",
  "MoneySweep": "MoneySweep",
  "Ambas": "Both",
  "Observación cruda": "Raw observation",
  "Señal pública": "Public signal",
  "Asunto en desarrollo": "Developing matter",
  "Pendiente de oficialización": "Pending officialization",
  "Oficializado": "Officialized",
  "Ejecución / enmienda": "Execution / amendment",
  "Auditoría / disputa / impacto": "Audit / dispute / impact",

  // SignalCard
  "Sin fecha": "No date",
  "sin beat": "no beat",
  "Señal capturada; falta resumen editorial.": "Signal captured; editorial summary missing.",
  "Fuente:": "Source:",
  "sin fuente asignada": "no source assigned",
  "Fuente original": "Original source",

  // HandoffStatusBadge labels
  "No listo": "Not ready",
  "Archivado": "Archived",

  // ConfidenceBadge bands + descriptions
  "T1 confirmado": "T1 confirmed",
  "Documento primario u oficial verificable.": "Primary or verifiable official document.",
  "Oficial preliminar": "Preliminary official",
  "Fuente oficial, pero aún pre-oficialización.": "Official source, but still pre-officialization.",
  "Corroborado": "Corroborated",
  "Múltiples señales o medio confiable con fuente identificable.":
    "Multiple signals or a reliable outlet with an identifiable source.",
  "Señal útil, pendiente de confirmación adicional.": "Useful signal, pending further confirmation.",
  "Débil": "Weak",
  "Una fuente indirecta o incompleta.": "A single indirect or incomplete source.",
  "No publicar como hecho": "Do not publish as fact",
  "Solo lead interno hasta verificación.": "Internal lead only until verified.",
};
