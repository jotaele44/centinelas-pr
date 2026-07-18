import React from 'react';
import { useLanguage } from '@/lib/LanguageContext';

const UserNotRegisteredError = () => {
  const { t } = useLanguage();
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gradient-to-b from-background to-muted/40 px-4">
      <div className="max-w-md w-full p-8 bg-card rounded-lg shadow-lg border border-border">
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 mb-6 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400">
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-foreground mb-4">{t("Acceso restringido")}</h1>
          <p className="text-muted-foreground mb-8">
            {t("No estás registrado para usar esta aplicación. Contacta al administrador para solicitar acceso.")}
          </p>
          <div className="p-4 bg-muted rounded-md text-sm text-muted-foreground text-left">
            <p>{t("Si crees que esto es un error, puedes:")}</p>
            <ul className="list-disc list-inside mt-2 space-y-1">
              <li>{t("Verificar que iniciaste sesión con la cuenta correcta")}</li>
              <li>{t("Contactar al administrador para obtener acceso")}</li>
              <li>{t("Cerrar sesión y volver a entrar")}</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default UserNotRegisteredError;
