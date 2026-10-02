import React from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Activity,
  ArrowRightLeft,
  Building2,
  Database,
  Droplets,
  FileSearch,
  GitBranch,
  Radar,
  RadioTower,
  ShieldCheck,
} from "lucide-react";
import { useTheme } from "@/lib/ThemeContext";
import { useLanguage } from "@/lib/LanguageContext";
import styles from "./AppShell.module.css";

const navItems = [
  { to: "/monitor", en: "Monitor", es: "Monitor", icon: Radar },
  { to: "/signals", en: "Signals", es: "Señales", icon: RadioTower },
  { to: "/matters", en: "Matters", es: "Asuntos", icon: FileSearch },
  { to: "/entidades", en: "Entities", es: "Entidades", icon: Building2 },
  { to: "/sources", en: "Sources", es: "Fuentes", icon: Database },
  { to: "/pipeline", en: "Pipeline", es: "Pipeline", icon: GitBranch },
  { to: "/water-disruption", en: "Water disruptions", es: "Interrupciones de agua", icon: Droplets },
  { to: "/handoff", en: "Handoff", es: "Handoff", icon: ArrowRightLeft },
];

export const AppShell = ({ children }) => {
  const location = useLocation();
  const { lang, toggleLang } = useLanguage();
  const { theme, toggleTheme } = useTheme();
  const t = (en, es) => lang === "en" ? en : es;

  return (
    <div className={`zip-surface ${styles.shell}`}>
      <aside className={styles.sidebar}>
        <Link to="/" className={styles.brand} aria-label={t("Centinelas overview", "Resumen de Centinelas")}>
          <div className={styles.brandMark} aria-hidden="true">
            <RadioTower size={18} />
          </div>
          <div>
            <div className={styles.brandName}>CENTINELAS</div>
            <div className={styles.brandSub}>{t("Puerto Rico · signal desk", "Puerto Rico · mesa de señales")}</div>
          </div>
        </Link>

        <nav className={styles.nav} aria-label={t("Centinelas diagnostic navigation", "Navegación diagnóstica de Centinelas")}>
          {navItems.map(({ to, en, es, icon: Icon }) => {
            const active = location.pathname === to || location.pathname.startsWith(`${to}/`);
            return (
              <Link key={to} to={to} aria-current={active ? "page" : undefined} className={`${styles.navItem} ${active ? styles.active : ""}`}>
                <Icon size={17} />
                <span>{t(en, es)}</span>
              </Link>
            );
          })}
        </nav>

        <div className={styles.boundary}>
          <div className={styles.boundaryHead}>
            <ShieldCheck size={15} />
            <span>CENTINELAS · PR</span>
          </div>
          <p>{t("Local producer operations only. Federation-global administration is not exposed here.", "Solo operaciones locales del productor. La administración global de la federación no se expone aquí.")}</p>
        </div>
      </aside>

      <div className={styles.workspace}>
        <header className={styles.topbar}>
          <div className={styles.runtime}>
            <Activity size={15} />

            <span>{t("Diagnostic surface", "Superficie diagnóstica")}</span>
          </div>
          <div className={styles.topActions}>
            <span className={styles.clockLabel}>{t("PRE-OFFICIAL SIGNAL PLANE", "PLANO DE SEÑALES PREOFICIALES")}</span>
            <button type="button" className={styles.languageToggle} onClick={toggleLang} aria-label={t("Change language", "Cambiar idioma")}>{lang === "en" ? "ES" : "EN"}</button>
            <button type="button" className={styles.languageToggle} onClick={toggleTheme} aria-label={t("Change theme", "Cambiar tema")}>{theme === "dark" ? "☀" : "☾"}</button>
          </div>
        </header>
        <main className={styles.main}>{children}</main>
      </div>
    </div>
  );
};