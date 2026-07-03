import React, { useState, useEffect } from "react";
import { appClient } from "@/api/appClient";
import { Link } from "react-router-dom";
import { Users } from "lucide-react";

export default function Authors() {
  const [authors, setAuthors] = useState([]);
  const [laws, setLaws] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [authorData, lawData] = await Promise.all([
        appClient.entities.Author.list(),
        appClient.entities.Law.list(),
      ]);
      setAuthors(authorData);
      setLaws(lawData);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const getLawCount = (authorId) =>
    laws.filter((l) => l.author_ids?.includes(authorId)).length;

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-2">Legisladores y autores</h1>
      <p className="text-muted-foreground mb-6">
        Conoce a los legisladores y los proyectos que han presentado
      </p>

      {loading ? (
        <p className="text-center text-muted-foreground py-12">Cargando...</p>
      ) : authors.length === 0 ? (
        <p className="text-center text-muted-foreground py-12">
          No hay legisladores registrados.
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {authors.map((author) => (
            <Link
              key={author.id}
              to={`/autor/${author.id}`}
              className="bg-card rounded-xl border border-border p-5 hover:border-primary/50 transition-colors"
            >
              <div className="flex items-center gap-3 mb-3">
                {author.photo_url ? (
                  <img
                    src={author.photo_url}
                    alt={author.name}
                    className="w-12 h-12 rounded-full object-cover"
                  />
                ) : (
                  <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
                    <Users className="w-6 h-6 text-primary" />
                  </div>
                )}
                <div>
                  <h3 className="font-semibold text-foreground">{author.name}</h3>
                  <p className="text-sm text-muted-foreground">
                    {author.party || "Independiente"}
                  </p>
                </div>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">
                  {author.chamber || "N/A"}
                  {author.district ? ` · ${author.district}` : ""}
                </span>
                <span className="font-medium text-primary">
                  {getLawCount(author.id)} proyectos
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}