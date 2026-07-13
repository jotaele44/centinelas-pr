import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { EN } from "@/lib/i18n/en";

const STORAGE_KEY = "centinelas_lang";
const LanguageContext = createContext(null);

function getInitialLang() {
  if (typeof window === "undefined") return "es";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "es" || stored === "en") return stored;
  return (window.navigator?.language || "es").toLowerCase().startsWith("en") ? "en" : "es";
}

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(getInitialLang);

  useEffect(() => {
    document.documentElement.lang = lang === "en" ? "en" : "es-PR";
    window.localStorage.setItem(STORAGE_KEY, lang);
  }, [lang]);

  // Canonical strings are Spanish; `t` returns the English translation when the
  // language is English, falling back to the Spanish key if a translation is
  // missing (so gaps are visible in-product, never a blank).
  const t = useCallback((es) => (lang === "en" ? EN[es] ?? es : es), [lang]);

  const toggleLang = useCallback(() => setLang((current) => (current === "en" ? "es" : "en")), []);

  const value = useMemo(() => ({ lang, setLang, toggleLang, t }), [lang, toggleLang, t]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) throw new Error("useLanguage must be used within a LanguageProvider");
  return context;
}
