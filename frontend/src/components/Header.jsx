import React, { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Menu, Moon, ShieldCheck, Sun, X } from "lucide-react";
import { useTheme } from "@/lib/ThemeContext";
import { useLanguage } from "@/lib/LanguageContext";

const navItems = [
  { to: "/monitor", label: "Monitor" },
  { to: "/signals", label: "Señales" },
  { to: "/matters", label: "Asuntos" },
  { to: "/entidades", label: "Entidades" },
  { to: "/sources", label: "Fuentes" },
  { to: "/pipeline", label: "Pipeline" },
  { to: "/handoff", label: "Handoff" },
];

function NavItems({ onNavigate }) {
  const { t } = useLanguage();
  return navItems.map((item) => (
    <NavLink
      key={item.to}
      to={item.to}
      onClick={onNavigate}
      className={({ isActive }) => `text-sm transition-colors ${isActive ? "font-semibold text-foreground" : "text-muted-foreground hover:text-foreground"}`}
    >
      {t(item.label)}
    </NavLink>
  ));
}

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const { t } = useLanguage();
  const isDark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="inline-flex h-9 w-9 items-center justify-center rounded-lg border text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label={isDark ? t("Cambiar a modo claro") : t("Cambiar a modo oscuro")}
      title={isDark ? t("Modo claro") : t("Modo oscuro")}
    >
      {isDark ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
    </button>
  );
}

function LanguageToggle() {
  const { lang, toggleLang, t } = useLanguage();
  return (
    <button
      type="button"
      onClick={toggleLang}
      className="inline-flex h-9 min-w-9 items-center justify-center rounded-lg border px-2 text-xs font-semibold uppercase text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label={t("Cambiar idioma")}
      title={t("Cambiar idioma")}
    >
      {lang === "en" ? "ES" : "EN"}
    </button>
  );
}

export default function Header() {
  const [open, setOpen] = useState(false);
  const { t } = useLanguage();
  return (
    <header className="w-full border-b border-border bg-background/95 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ShieldCheck className="h-6 w-6" aria-hidden="true" />
          </div>
          <div>
            <span className="text-lg font-bold text-foreground block leading-tight">Centinelas</span>
            <span className="text-xs text-muted-foreground block leading-tight">{t("Señal temprana → MoneySweep")}</span>
          </div>
        </Link>
        <nav className="hidden items-center gap-6 md:flex" aria-label={t("Navegación principal")}>
          <NavItems />
        </nav>
        <div className="flex items-center gap-2">
          <LanguageToggle />
          <ThemeToggle />
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            className="inline-flex items-center justify-center rounded-lg border p-2 md:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={open ? t("Cerrar navegación") : t("Abrir navegación")}
            aria-expanded={open}
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>
      {open ? (
        <nav className="border-t bg-background px-4 py-4 md:hidden" aria-label={t("Navegación móvil")}>
          <div className="flex flex-col gap-4">
            <NavItems onNavigate={() => setOpen(false)} />
          </div>
        </nav>
      ) : null}
    </header>
  );
}
