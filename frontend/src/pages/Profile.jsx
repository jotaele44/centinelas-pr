import React, { useState, useEffect } from "react";
import { appClient } from "@/api/appClient";
import { Link } from "react-router-dom";
import CategorySubscription from "@/components/laws/CategorySubscription";
import { ThumbsUp, ThumbsDown, MessageCircle, User } from "lucide-react";

export default function Profile() {
  const [user, setUser] = useState(null);
  const [comments, setComments] = useState([]);
  const [votes, setVotes] = useState([]);
  const [laws, setLaws] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const me = await appClient.auth.me();
      if (!me) {
        window.location.href = "/Login";
        return;
      }
      setUser(me);

      const [userComments, userVotes, allLaws] = await Promise.all([
        appClient.entities.Comment.filter({ created_by_id: me.id }, "-created_date", 100),
        appClient.entities.Vote.filter({ created_by_id: me.id }, "-created_date", 100),
        appClient.entities.Law.list("-last_action_date", 200),
      ]);

      setComments(userComments);
      setVotes(userVotes);

      const lawMap = {};
      allLaws.forEach((l) => {
        lawMap[l.id] = l;
      });
      setLaws(lawMap);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="max-w-4xl mx-auto px-4 py-20 text-center text-muted-foreground">Cargando...</div>;
  }
  if (!user) return null;

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="flex items-center gap-3 mb-8">
        <div className="w-14 h-14 rounded-full bg-primary flex items-center justify-center">
          <User className="w-7 h-7 text-primary-foreground" />
        </div>
        <div>
          <h1 className="text-3xl font-bold">{user.full_name || user.email}</h1>
          <p className="text-muted-foreground">{user.email}</p>
        </div>
      </div>

      {/* Category subscriptions */}
      <div className="mb-8">
        <CategorySubscription userEmail={user.email} userName={user.full_name || user.email} />
      </div>

      {/* Votes */}
      <div className="mb-8">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <ThumbsUp className="w-5 h-5" />
          Mis votos ({votes.length})
        </h2>
        <div className="space-y-2">
          {votes.length === 0 ? (
            <p className="text-muted-foreground text-sm">Aún no has votado por ninguna ley.</p>
          ) : (
            votes.map((v) => {
              const law = laws[v.law_id];
              return (
                <div
                  key={v.id}
                  className="bg-card rounded-lg border border-border p-3 flex items-center gap-3"
                >
                  {v.vote_type === "pro" ? (
                    <ThumbsUp className="w-4 h-4 text-green-500 shrink-0" />
                  ) : (
                    <ThumbsDown className="w-4 h-4 text-red-500 shrink-0" />
                  )}
                  <span className="text-sm font-medium shrink-0">
                    {v.vote_type === "pro" ? "A favor" : "En contra"}
                  </span>
                  {law ? (
                    <Link
                      to={`/ley/${law.id}`}
                      className="text-sm text-primary hover:underline flex-1 line-clamp-1"
                    >
                      {law.bill_number} — {law.title}
                    </Link>
                  ) : (
                    <span className="text-sm text-muted-foreground flex-1">Ley no disponible</span>
                  )}
                  <span className="text-xs text-muted-foreground shrink-0">
                    {new Date(v.created_date).toLocaleDateString("es-PR")}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Comments */}
      <div>
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <MessageCircle className="w-5 h-5" />
          Mis comentarios ({comments.length})
        </h2>
        <div className="space-y-2">
          {comments.length === 0 ? (
            <p className="text-muted-foreground text-sm">Aún no has comentado ninguna ley.</p>
          ) : (
            comments.map((c) => {
              const law = laws[c.law_id];
              return (
                <div key={c.id} className="bg-card rounded-lg border border-border p-4">
                  <div className="flex items-center justify-between mb-2">
                    {law ? (
                      <Link
                        to={`/ley/${law.id}`}
                        className="text-sm font-medium text-primary hover:underline line-clamp-1"
                      >
                        {law.bill_number} — {law.title}
                      </Link>
                    ) : (
                      <span className="text-sm text-muted-foreground">Ley no disponible</span>
                    )}
                    <span className="text-xs text-muted-foreground shrink-0 ml-2">
                      {new Date(c.created_date).toLocaleDateString("es-PR")}
                    </span>
                  </div>
                  <p className="text-sm text-foreground">{c.text}</p>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}