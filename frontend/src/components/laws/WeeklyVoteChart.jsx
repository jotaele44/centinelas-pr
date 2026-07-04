import React, { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { appClient } from "@/api/appClient";
import { CalendarClock } from "lucide-react";

export default function WeeklyVoteChart() {
  const [chartData, setChartData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [votes, laws] = await Promise.all([
        appClient.entities.Vote.list("-created_date", 500),
        appClient.entities.Law.list("-last_action_date", 200),
      ]);

      const oneWeekAgo = new Date();
      oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);

      const weeklyVotes = votes.filter((v) => new Date(v.created_date) >= oneWeekAgo);

      const lawMap = {};
      laws.forEach((l) => {
        lawMap[l.id] = l;
      });

      const grouped = {};
      weeklyVotes.forEach((v) => {
        if (!grouped[v.law_id]) {
          grouped[v.law_id] = { pro: 0, against: 0 };
        }
        if (v.vote_type === "pro") grouped[v.law_id].pro++;
        else grouped[v.law_id].against++;
      });

      const data = Object.entries(grouped)
        .map(([lawId, counts]) => ({
          name: (lawMap[lawId]?.bill_number || lawMap[lawId]?.title || "N/A").substring(0, 18),
          pro: counts.pro,
          against: counts.against,
          total: counts.pro + counts.against,
        }))
        .sort((a, b) => b.total - a.total)
        .slice(0, 10);

      setChartData(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-card rounded-2xl border border-border p-6">
        <div className="animate-pulse">
          <div className="h-6 bg-muted rounded w-1/3 mb-4"></div>
          <div className="h-64 bg-muted rounded"></div>
        </div>
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div className="bg-card rounded-2xl border border-border p-6">
        <h2 className="text-lg font-semibold flex items-center gap-2 mb-2">
          <CalendarClock className="w-5 h-5 text-primary" />
          Votos de esta semana
        </h2>
        <p className="text-muted-foreground text-center py-8">
          No se han registrado votos en los últimos 7 días. ¡Sé el primero en reaccionar a una ley!
        </p>
      </div>
    );
  }

  return (
    <div className="bg-card rounded-2xl border border-border p-6">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-1">
        <CalendarClock className="w-5 h-5 text-primary" />
        Votos de esta semana
      </h2>
      <p className="text-sm text-muted-foreground mb-4">
        Leyes con más votos a favor y en contra en los últimos 7 días
      </p>
      <ResponsiveContainer width="100%" height={350}>
        <BarChart data={chartData} layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
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