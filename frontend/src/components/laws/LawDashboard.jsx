import React, { useMemo } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { TrendingUp } from "lucide-react";

export default function LawDashboard({ laws }) {
  const topLaws = useMemo(() => {
    return [...laws]
      .map((l) => ({
        name: (l.bill_number || l.title || "N/A").substring(0, 18),
        fullName: l.bill_number ? `${l.bill_number} — ${l.title}` : l.title,
        pro: l.votes_pro || 0,
        against: l.votes_against || 0,
        total: (l.votes_pro || 0) + (l.votes_against || 0),
      }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 10);
  }, [laws]);

  const hasVotes = topLaws.some((l) => l.total > 0);

  if (!hasVotes) {
    return (
      <div className="bg-card rounded-2xl border border-border p-6">
        <h2 className="text-lg font-semibold flex items-center gap-2 mb-2">
          <TrendingUp className="w-5 h-5 text-primary" />
          Resumen de participación ciudadana
        </h2>
        <p className="text-muted-foreground text-center py-8">
          Aún no hay votos registrados. ¡Sé el primero en reaccionar a una ley con "A favor" o "En contra"!
        </p>
      </div>
    );
  }

  return (
    <div className="bg-card rounded-2xl border border-border p-6">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-1">
        <TrendingUp className="w-5 h-5 text-primary" />
        Leyes con mayor participación ciudadana
      </h2>
      <p className="text-sm text-muted-foreground mb-4">
        Top 10 medidas por cantidad de votos a favor y en contra
      </p>
      <ResponsiveContainer width="100%" height={420}>
        <BarChart data={topLaws} layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis type="number" tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" />
          <YAxis dataKey="name" type="category" width={110} tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
          <Tooltip
            contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }}
            formatter={(value, name) => [value, name === "pro" ? "A favor" : "En contra"]}
          />
          <Legend formatter={(value) => (value === "pro" ? "A favor" : "En contra")} />
          <Bar dataKey="pro" stackId="a" fill="#22c55e" radius={[0, 0, 0, 0]} />
          <Bar dataKey="against" stackId="a" fill="#ef4444" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}