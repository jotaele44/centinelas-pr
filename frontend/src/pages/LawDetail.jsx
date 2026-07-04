import React, { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { appClient } from "@/api/appClient";
import { ArrowLeft, Calendar, Users, Building2, Tag } from "lucide-react";
import VoteButtons from "@/components/laws/VoteButtons";
import CommentSection from "@/components/laws/CommentSection";
import LawTimeline from "@/components/laws/LawTimeline";

export default function LawDetail() {
  const { id } = useParams();
  const [law, setLaw] = useState(null);
  const [authors, setAuthors] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadLaw();
  }, [id]);

  const loadLaw = async () => {
    try {
      const data = await appClient.entities.Law.get(id);
      setLaw(data);
      if (data.author_ids?.length > 0) {
        const allAuthors = await appClient.entities.Author.list();
        setAuthors(allAuthors.filter((a) => data.author_ids.includes(a.id)));
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="max-w-4xl mx-auto px-4 py-20 text-center text-muted-foreground">Cargando...</div>;
  }
  if (!law) {
    return <div className="max-w-4xl mx-auto px-4 py-20 text-center text-muted-foreground">Ley no encontrada.</div>;
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link to="/" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6">
        <ArrowLeft className="w-4 h-4" />
        Volver al catálogo
      </Link>

      {/* Header badges */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        {law.bill_number && (
          <span className="text-sm font-bold text-primary bg-primary/10 px-3 py-1 rounded-lg">
            {law.bill_number}
          </span>
        )}
        <span className="text-sm text-muted-foreground">{law.type}</span>
        <span className="text-sm px-3 py-1 rounded-full bg-muted">{law.status}</span>
        {law.category && (
          <span className="text-sm text-muted-foreground bg-muted px-3 py-1 rounded-full flex items-center gap-1 capitalize">
            <Tag className="w-3 h-3" />
            {law.category}
          </span>
        )}
        {law.tags?.map((t) => (
          <span
            key={t}
            className={`text-sm px-3 py-1 rounded-full font-medium ${
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

      <h1 className="text-2xl font-bold text-foreground mb-4 leading-snug">{law.title}</h1>

      {/* Dates */}
      <div className="flex gap-6 text-sm text-muted-foreground mb-6 flex-wrap">
        {law.submission_date && (
          <span className="flex items-center gap-1">
            <Calendar className="w-4 h-4" />
            Presentada: {new Date(law.submission_date).toLocaleDateString("es-PR")}
          </span>
        )}
        {law.last_action_date && (
          <span className="flex items-center gap-1">
            <Calendar className="w-4 h-4" />
            Última acción: {new Date(law.last_action_date).toLocaleDateString("es-PR")}
          </span>
        )}
      </div>

      {/* Vote buttons */}
      <div className="mb-8">
        <VoteButtons law={law} />
      </div>

      {/* Description */}
      {law.description && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold mb-2">Descripción</h2>
          <p className="text-foreground whitespace-pre-wrap leading-relaxed">{law.description}</p>
        </div>
      )}

      {/* Pros and Contras */}
      <div className="grid md:grid-cols-2 gap-4 mb-6">
        {law.pros && (
          <div className="bg-green-50 rounded-lg p-4 border border-green-200">
            <h3 className="font-semibold text-green-800 mb-2">Pros</h3>
            <p className="text-sm text-green-900 whitespace-pre-wrap leading-relaxed">{law.pros}</p>
          </div>
        )}
        {law.contras && (
          <div className="bg-red-50 rounded-lg p-4 border border-red-200">
            <h3 className="font-semibold text-red-800 mb-2">Contras</h3>
            <p className="text-sm text-red-900 whitespace-pre-wrap leading-relaxed">{law.contras}</p>
          </div>
        )}
      </div>

      {/* Connections */}
      {(law.officials?.length > 0 || law.lobbyists?.length > 0) && (
        <div className="grid md:grid-cols-2 gap-4 mb-8">
          {law.officials?.length > 0 && (
            <div>
              <h3 className="font-semibold mb-2 flex items-center gap-2">
                <Users className="w-4 h-4" />
                Oficiales públicos relacionados
              </h3>
              <div className="flex flex-wrap gap-2">
                {law.officials.map((o, i) => (
                  <span key={i} className="text-sm bg-muted px-3 py-1 rounded-full">{o}</span>
                ))}
              </div>
            </div>
          )}
          {law.lobbyists?.length > 0 && (
            <div>
              <h3 className="font-semibold mb-2 flex items-center gap-2">
                <Building2 className="w-4 h-4" />
                Personas y organizaciones influyentes
              </h3>
              <div className="flex flex-wrap gap-2">
                {law.lobbyists.map((l, i) => (
                  <span key={i} className="text-sm bg-muted px-3 py-1 rounded-full">{l}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Authors */}
      {authors.length > 0 && (
        <div className="mb-8">
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <Users className="w-4 h-4" />
            Legisladores autores
          </h3>
          <div className="flex flex-wrap gap-3">
            {authors.map((a) => (
              <Link
                key={a.id}
                to={`/autor/${a.id}`}
                className="flex items-center gap-2 bg-card border border-border rounded-lg p-2 pr-4 hover:border-primary/50 transition-colors"
              >
                {a.photo_url ? (
                  <img src={a.photo_url} alt={a.name} className="w-8 h-8 rounded-full object-cover" />
                ) : (
                  <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                    <Users className="w-4 h-4 text-primary" />
                  </div>
                )}
                <div>
                  <p className="text-sm font-medium text-foreground">{a.name}</p>
                  <p className="text-xs text-muted-foreground">{a.party || "Independiente"}</p>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Timeline */}
      <div className="mb-8">
        <LawTimeline law={law} />
      </div>

      {/* Comments */}
      <div className="border-t border-border pt-6">
        <CommentSection lawId={law.id} />
      </div>
    </div>
  );
}