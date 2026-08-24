import React from "react";
import { useLanguage } from "@/lib/LanguageContext";

export default function Footer() {
  const { t } = useLanguage();
  return (
    <footer className="border-t border-border bg-muted/30 mt-16">
      <div className="max-w-7xl mx-auto px-4 py-8 text-sm text-muted-foreground">
        <p className="font-semibold text-foreground">Centinelas</p>
        <p className="mt-1">{t("Monitor de señales públicas tempranas para Puerto Rico. Sibling upstream de MoneySweep.")}</p>
      </div>
    </footer>
  );
}
