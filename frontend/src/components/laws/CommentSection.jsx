import React, { useState, useEffect } from "react";
import { appClient } from "@/api/appClient";
import { Button } from "@/components/ui/button";
import { MessageCircle, Send, Loader2 } from "lucide-react";

export default function CommentSection({ lawId }) {
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadComments();
    loadUser();
  }, [lawId]);

  const loadComments = async () => {
    try {
      const data = await appClient.entities.Comment.filter({ law_id: lawId }, "-created_date", 100);
      setComments(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadUser = async () => {
    try {
      const user = await appClient.auth.me();
      if (user) setName(user.full_name || user.email || "");
    } catch (err) {
      // ignore
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setSubmitting(true);
    try {
      await appClient.entities.Comment.create({
        law_id: lawId,
        user_name: name || "Anónimo",
        text: text.trim(),
      });
      setText("");
      loadComments();
    } catch (err) {
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <MessageCircle className="w-5 h-5" />
        Comentarios ({comments.length})
      </h3>

      <form onSubmit={handleSubmit} className="mb-6 space-y-3">
        <input
          type="text"
          placeholder="Tu nombre"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full h-10 rounded-lg border border-border bg-card px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
        <textarea
          placeholder="Comparte tu opinión sobre esta medida..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
          required
        />
        <Button type="submit" disabled={submitting || !text.trim()}>
          {submitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}
          {submitting ? "Enviando..." : "Publicar comentario"}
        </Button>
      </form>

      <div className="space-y-3">
        {loading ? (
          <p className="text-muted-foreground text-sm">Cargando comentarios...</p>
        ) : comments.length === 0 ? (
          <p className="text-muted-foreground text-sm">Sé el primero en comentar.</p>
        ) : (
          comments.map((c) => (
            <div key={c.id} className="bg-card rounded-lg border border-border p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-sm text-foreground">{c.user_name || "Anónimo"}</span>
                <span className="text-xs text-muted-foreground">
                  {new Date(c.created_date).toLocaleDateString("es-PR")}
                </span>
              </div>
              <p className="text-sm text-foreground whitespace-pre-wrap">{c.text}</p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}