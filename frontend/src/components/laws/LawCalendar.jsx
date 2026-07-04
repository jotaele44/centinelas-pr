import React, { useState, useMemo } from "react";
import { Calendar } from "@/components/ui/calendar";
import { Link } from "react-router-dom";
import { CalendarDays } from "lucide-react";

export default function LawCalendar({ laws }) {
  const [selectedDate, setSelectedDate] = useState(null);
  const [month, setMonth] = useState(new Date());

  const dateMap = useMemo(() => {
    const map = {};
    laws.forEach((law) => {
      if (law.submission_date) {
        const key = new Date(law.submission_date).toDateString();
        if (!map[key]) map[key] = [];
        map[key].push({ law, type: "Radicación" });
      }
      if (law.last_action_date) {
        const key = new Date(law.last_action_date).toDateString();
        if (!map[key]) map[key] = [];
        map[key].push({ law, type: "Última acción" });
      }
    });
    return map;
  }, [laws]);

  const lawDates = useMemo(
    () => Object.keys(dateMap).map((k) => new Date(k)),
    [dateMap]
  );

  const selectedLaws = selectedDate ? dateMap[selectedDate.toDateString()] || [] : [];

  return (
    <div className="bg-card rounded-2xl border border-border p-6">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-1">
        <CalendarDays className="w-5 h-5 text-primary" />
        Calendario legislativo
      </h2>
      <p className="text-sm text-muted-foreground mb-4">
        Fechas de radicación y últimas acciones de las medidas
      </p>
      <div className="flex flex-col md:flex-row gap-6">
        <div className="flex-shrink-0 mx-auto">
          <Calendar
            mode="single"
            selected={selectedDate}
            onSelect={setSelectedDate}
            month={month}
            onMonthChange={setMonth}
            modifiers={{ lawDay: lawDates }}
            modifiersStyles={{
              lawDay: {
                backgroundColor: "rgba(214, 40, 40, 0.15)",
                fontWeight: "700",
                color: "#D62828",
                borderRadius: "50%",
              },
            }}
          />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold mb-3">
            {selectedDate
              ? `Actividad del ${selectedDate.toLocaleDateString("es-PR")}`
              : "Selecciona una fecha destacada"}
          </h3>
          {selectedLaws.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {selectedDate
                ? "No hay actividad legislativa en esta fecha."
                : "Las fechas destacadas en rojo tienen actividad legislativa. Haz clic en una para ver las medidas."}
            </p>
          ) : (
            <div className="space-y-2">
              {selectedLaws.map(({ law, type }, i) => (
                <Link
                  key={i}
                  to={`/ley/${law.id}`}
                  className="block bg-background rounded-lg border border-border p-3 hover:border-primary/50 transition-colors"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-primary px-2 py-0.5 bg-primary/10 rounded-full">
                      {type}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {law.bill_number || "N/A"}
                    </span>
                  </div>
                  <p className="text-sm text-foreground line-clamp-2">{law.title}</p>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}