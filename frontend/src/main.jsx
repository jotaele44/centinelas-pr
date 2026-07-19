import React from 'react'
import ReactDOM from 'react-dom/client'
// Self-hosted fonts (no render-blocking third-party request; offline-safe).
import '@fontsource-variable/inter'
import '@fontsource/jetbrains-mono'
import App from '@/App.jsx'
import { resolveInitialTheme, applyTheme } from '@/lib/ThemeContext'
import '@/index.css'
import '@/styles/federation.css'

// Repo accent for the shared federation.css.
document.documentElement.dataset.repo = 'centinelas-pr'
// Apply the resolved theme synchronously before the first render (no FOUC).
applyTheme(resolveInitialTheme())

ReactDOM.createRoot(document.getElementById('root')).render(
  <App />
)
