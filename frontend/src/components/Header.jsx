import React, { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Menu, ShieldCheck, X } from "lucide-react";

const navItems = [
  { to: "/monitor", label: "Monitor" },
  { to: "/signals", label: "Señales" },
  { to: "/matters", label: "Asuntos" },
  { to: "/sources", label: "Fuentes" },
  { to: "/pipeline", label: "Pipeline" },
  { to: "/handoff", label: "Handoff" },
  { to: "/tabla", label: "Legislativo" },
];

function NavItems({ onNavigate }) {
  return navItems.map((item) => (
    <NavLink
      key={item.to}
      to={item.to}
      onClick={onNavigate}
      className={({ isActive }) => `text-sm transition-colors ${isActive ? "font-semibold text-foreground" : "text-muted-foreground hover:text-foreground"}`}
    >
      {item.label}
    </NavLink>
  ));
}

export default function Header() {
  const [open, setOpen] = useState(false);
  return (
    <header className="w-full border-b border-border bg-background/95 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ShieldCheck className="h-6 w-6" aria-hidden="true" />
          </div>
          <div>
            <span className="text-lg font-bold text-foreground block leading-tight">Centinelas</span>
            <span className="text-xs text-muted-foreground block leading-tight">Señal temprana → MoneySweep</span>
          </div>
        </Link>
        <nav className="hidden items-center gap-6 md:flex" aria-label="Navegación principal">
          <NavItems />
        </nav>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="inline-flex items-center justify-center rounded-lg border p-2 md:hidden"
          aria-label={open ? "Cerrar navegación" : "Abrir navegación"}
          aria-expanded={open}
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>
      {open ? (
        <nav className="border-t bg-background px-4 py-4 md:hidden" aria-label="Navegación móvil">
          <div className="flex flex-col gap-4">
            <NavItems onNavigate={() => setOpen(false)} />
          </div>
        </nav>
      ) : null}
    </header>
  );
}
