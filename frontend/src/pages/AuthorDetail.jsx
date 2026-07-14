import React, { useState, useEffect } from "react";
import { appClient } from "@/api/appClient";
import { Link, useParams } from "react-router-dom";
import { Users, ArrowLeft } from "lucide-react";
import { useLanguage } from "@/lib/LanguageContext";

export default function AuthorDetail() {
  const { t } = useLanguage();
  const { id } = useParams();
  const [author, setAuthor] = useState(null);
  const [laws, setLaws] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, [id]);

  const loadData = async () => {
    try {
      const authorData = await appClient.entities.Author.get(id);
      setAuthor(authorData);
      const allLaws = await appClient.entities.Law.list();
      setLaws(allLaws.filter((l) => l.author_ids?.includes(id)));
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-20 text-center text-muted-foreground">
        {t("Cargando…")}
      </div>
    );
  }
  if (!author) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-20 text-center text-muted-foreground">
        {t("Legislador no encontrado.")}
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link
        to="/autores"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" aria-hidden="true" /> {t("Volver a legisladores")}
      </Link>

      <div className="flex items-center gap-4 mb-6">
        {author.photo_url ? (
          <img
            src={author.photo_url}
            alt={author.name}
            className="w-20 h-20 rounded-full object-cover"
          />
        ) : (
          <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center">
            <Users className="w-10 h-10 text-primary" />
          </div>
        )}
        <div>
          <h1 className="text-3xl font-bold">{author.name}</h1>
          <p className="text-muted-foreground">{author.party || t("Independiente")}</p>
          <p className="text-sm text-muted-foreground">
            {author.chamber || "N/A"}
            {author.district ? ` · ${author.district}` : ""}
          </p>
        </div>
      </div>

      {author.bio && (
        <div className="bg-card rounded-xl border border-border p-5 mb-6">
          <p className="text-foreground">{author.bio}</p>
        </div>
      )}

      <h2 className="text-xl font-semibold mb-4">
        {t("Proyectos presentados")} ({laws.length})
      </h2>
      {laws.length === 0 ? (
        <p className="text-muted-foreground">
          {t("Este legislador no tiene proyectos registrados.")}
        </p>
      ) : (
        <div className="space-y-3">
          {laws.map((law) => (
            <Link
              key={law.id}
              to={`/ley/${law.id}`}
              className="block bg-card rounded-lg border border-border p-4 hover:border-primary/50 transition-colors"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-bold text-primary">
                  {law.bill_number || "N/A"}
                </span>
                <span className="text-xs px-2 py-0.5 bg-muted rounded-full">
                  {law.status}
                </span>
              </div>
              <p className="text-foreground font-medium line-clamp-2">{law.title}</p>
              <p className="text-sm text-muted-foreground mt-1 capitalize">
                {law.category}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}