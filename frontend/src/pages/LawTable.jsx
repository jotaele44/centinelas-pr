import React, { useState, useEffect } from "react";
import { appClient } from "@/api/appClient";
import { Link } from "react-router-dom";

const STATUS_COLORS = {
  Radicada: "bg-blue-100 text-blue-700",
  "En comisión": "bg-yellow-100 text-yellow-700",
  "En conferencia": "bg-orange-100 text-orange-700",
  "Aprobada por el Senado": "bg-green-100 text-green-700",
  "Aprobada por la Cámara": "bg-green-100 text-green-700",
  Aprobada: "bg-green-100 text-green-700",
  Ley: "bg-emerald-100 text-emerald-700",
  Rechazada: "bg-red-100 text-red-700",
};

export default function LawTable() {
  const [laws, setLaws] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadLaws();
  }, []);

  const loadLaws = async () => {
    try {
      const data = await appClient.entities.Law.list("-last_action_date", 200);
      setLaws(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-1">Catálogo de medidas</h1>
      <p className="text-muted-foreground mb-6">
        Vista detallada de todas las medidas y leyes en una sola pantalla
      </p>

      {loading ? (
        <p className="text-center text-muted-foreground py-12">Cargando...</p>
      ) : laws.length === 0 ? (
        <p className="text-center text-muted-foreground py-12">No hay medidas disponibles.</p>
      ) : (
        <div className="overflow-x-auto bg-card rounded-xl border border-border">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="text-left px-4 py-3 text-sm font-semibold">Número</th>
                <th className="text-left px-4 py-3 text-sm font-semibold">Título</th>
                <th className="text-left px-4 py-3 text-sm font-semibold">Estado</th>
                <th className="text-left px-4 py-3 text-sm font-semibold">Última acción</th>
                <th className="text-left px-4 py-3 text-sm font-semibold">Categoría</th>
                <th className="text-left px-4 py-3 text-sm font-semibold">Votos</th>
              </tr>
            </thead>
            <tbody>
              {laws.map((law) => (
                <tr key={law.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 whitespace-nowrap">
                    <Link to={`/ley/${law.id}`} className="font-bold text-primary hover:underline">
                      {law.bill_number || "N/A"}
                    </Link>
                  </td>
                  <td className="px-4 py-3 max-w-md">
                    <Link to={`/ley/${law.id}`} className="text-foreground hover:underline line-clamp-1">
                      {law.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span
                      className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                        STATUS_COLORS[law.status] || "bg-gray-100 text-gray-700"
                      }`}
                    >
                      {law.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-muted-foreground whitespace-nowrap">
                    {law.last_action_date
                      ? new Date(law.last_action_date).toLocaleDateString("es-PR")
                      : "N/A"}
                  </td>
                  <td className="px-4 py-3 text-sm capitalize whitespace-nowrap">{law.category || "N/A"}</td>
                  <td className="px-4 py-3 text-sm whitespace-nowrap">
                    <span className="text-green-600 font-medium">✓ {law.votes_pro || 0}</span>
                    {" / "}
                    <span className="text-red-600 font-medium">✗ {law.votes_against || 0}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}