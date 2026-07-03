import React from "react";
import { Search } from "lucide-react";

const CATEGORIES = [
  "educación", "salud", "transporte", "seguridad pública", "gobierno municipal",
  "energía", "asuntos del consumidor", "justicia", "nominaciones", "medio ambiente",
  "economía", "otro",
];
const TYPES = ["Proyecto (Senado)", "Proyecto (Cámara)", "Resolución (Senado)", "Resolución (Cámara)", "Resolución Conjunta", "Nombramiento"];
const STATUSES = ["Radicada", "En comisión", "En conferencia", "Aprobada por el Senado", "Aprobada por la Cámara", "Aprobada", "Ley", "Rechazada"];
const TAGS = ["urgente", "en revisión", "aprobada"];

const SORTS = [
  { value: "recent", label: "Más reciente" },
  { value: "oldest", label: "Más viejo" },
  { value: "popular", label: "Más popular" },
  { value: "voted_pro", label: "Más votado ✓" },
  { value: "voted_against", label: "Más votado ✗" },
  { value: "commented", label: "Más comentado 💬" },
];

const selectClass =
  "h-10 rounded-lg border border-border bg-card px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 capitalize";

export default function LawFilters({
  search, setSearch, category, setCategory, type, setType, status, setStatus, sortBy, setSortBy, tag, setTag,
}) {
  return (
    <div className="space-y-4">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
        <input
          type="text"
          placeholder="Buscar por nombre, número o descripción..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 h-12 rounded-lg border border-border bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>
      <div className="flex flex-wrap gap-3">
        <select value={category} onChange={(e) => setCategory(e.target.value)} className={selectClass}>
          <option value="all">Todas las categorías</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select value={type} onChange={(e) => setType(e.target.value)} className={selectClass}>
          <option value="all">Todos los tipos</option>
          {TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className={selectClass}>
          <option value="all">Todos los estados</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select value={tag} onChange={(e) => setTag(e.target.value)} className={selectClass}>
          <option value="all">Todas las etiquetas</option>
          {TAGS.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className={selectClass + " ml-auto"}>
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm text-muted-foreground">Etiquetas:</span>
        <button
          onClick={() => setTag("all")}
          className={`text-sm px-3 py-1 rounded-full border transition-colors ${
            tag === "all" ? "bg-primary text-primary-foreground border-primary" : "bg-card text-foreground border-border hover:border-primary/50"
          }`}
        >
          Todas
        </button>
        {TAGS.map((t) => (
          <button
            key={t}
            onClick={() => setTag(t)}
            className={`text-sm px-3 py-1 rounded-full border transition-colors capitalize ${
              tag === t
                ? t === "urgente"
                  ? "bg-red-500 text-white border-red-500"
                  : t === "en revisión"
                  ? "bg-yellow-500 text-white border-yellow-500"
                  : "bg-green-500 text-white border-green-500"
                : "bg-card text-foreground border-border hover:border-primary/50"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
    </div>
  );
}