import React from "react";
import { Link } from "react-router-dom";
import { ThumbsUp, ThumbsDown, MessageCircle, Calendar } from "lucide-react";

const STATUS_COLORS = {
  "Radicada": "bg-blue-100 text-blue-700",
  "En comisión": "bg-yellow-100 text-yellow-700",
  "En conferencia": "bg-orange-100 text-orange-700",
  "Aprobada por el Senado": "bg-green-100 text-green-700",
  "Aprobada por la Cámara": "bg-green-100 text-green-700",
  "Aprobada": "bg-green-100 text-green-700",
  "Ley": "bg-emerald-100 text-emerald-700",
  "Rechazada": "bg-red-100 text-red-700",
};

export default function LawCard({ law }) {
  const statusColor = STATUS_COLORS[law.status] || "bg-gray-100 text-gray-700";

  return (
    <Link to={`/ley/${law.id}`} className="block">
      <div className="bg-card rounded-xl border border-border p-5 hover:shadow-md hover:border-primary/30 transition-all">
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          {law.bill_number && (
            <span className="text-sm font-bold text-primary bg-primary/10 px-2.5 py-0.5 rounded-md">
              {law.bill_number}
            </span>
          )}
          <span className="text-xs text-muted-foreground">{law.type}</span>
          <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${statusColor}`}>{law.status}</span>
          {law.category && (
            <span className="text-xs text-muted-foreground bg-muted px-2.5 py-0.5 rounded-full ml-auto capitalize">
              {law.category}
            </span>
          )}
        </div>
        {law.tags?.length > 0 && (
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            {law.tags.map((t) => (
              <span
                key={t}
                className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                  t === "urgente"
                    ? "bg-red-100 text-red-700"
                    : t === "en revisión"
                    ? "bg-yellow-100 text-yellow-700"
                    : "bg-green-100 text-green-700"
                }`}
              >
                {t}
              </span>
            ))}
          </div>
        )}
        <h3 className="font-semibold text-foreground line-clamp-2 mb-3 leading-snug">{law.title}</h3>
        {law.last_action_date && (
          <p className="text-xs text-muted-foreground mb-3 flex items-center gap-1">
            <Calendar className="w-3 h-3" />
            Última acción: {new Date(law.last_action_date).toLocaleDateString("es-PR")}
          </p>
        )}
        <div className="flex items-center gap-4 text-sm text-muted-foreground border-t border-border pt-3">
          <span className="flex items-center gap-1">
            <ThumbsUp className="w-4 h-4 text-green-500" />
            {law.votes_pro || 0}
          </span>
          <span className="flex items-center gap-1">
            <ThumbsDown className="w-4 h-4 text-red-500" />
            {law.votes_against || 0}
          </span>
          <span className="flex items-center gap-1">
            <MessageCircle className="w-4 h-4" />
            {law.comments_count || 0}
          </span>
        </div>
      </div>
    </Link>
  );
}