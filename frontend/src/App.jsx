import { Toaster } from "@/components/ui/toaster"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from '@/lib/query-client'
import { BrowserRouter as Router, Navigate, Route, Routes } from 'react-router-dom';
import PageNotFound from './lib/PageNotFound';
import { ThemeProvider } from '@/lib/ThemeContext';
import { LanguageProvider } from '@/lib/LanguageContext';
import Home from './pages/Home';
import Monitor from './pages/Monitor';
import Signals from './pages/Signals';
import Matters from './pages/Matters';
import MatterDetail from './pages/MatterDetail';
import Sources from './pages/Sources';
import Handoff from './pages/Handoff';
import Pipeline from './pages/Pipeline';
import PipelineItemDetail from './pages/PipelineItemDetail';
import WaterDisruption from './pages/WaterDisruption';
import Layout from './components/Layout';
import SignalsTable from './pages/SignalsTable';
import Entities from './pages/Entities';
import EntityDetail from './pages/EntityDetail';
import ErrorBoundary from '@/components/ErrorBoundary';

const AppRoutes = () => {
  return (
    <ErrorBoundary>
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/monitor" element={<Monitor />} />
        <Route path="/signals" element={<Signals />} />
        <Route path="/matters" element={<Matters />} />
        <Route path="/matters/:id" element={<MatterDetail />} />
        <Route path="/sources" element={<Sources />} />
        <Route path="/handoff" element={<Handoff />} />

        {/* Universal 6-domain intake pipeline (FastAPI backend, separate from the localStorage legislative layer). */}
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/pipeline/:itemId" element={<PipelineItemDetail />} />
        <Route path="/water-disruption" element={<WaterDisruption />} />

        {/* Signal-centric views converted from the legacy legislative surface. */}
        <Route path="/tabla" element={<SignalsTable />} />
        <Route path="/entidades" element={<Entities />} />
        <Route path="/entidad/:slug" element={<EntityDetail />} />
        {/* Back-compat: old legislator routes now resolve to the entity list. */}
        <Route path="/autores" element={<Navigate to="/entidades" replace />} />

      </Route>
      <Route path="*" element={<PageNotFound />} />
    </Routes>
    </ErrorBoundary>
  );
};

function App() {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <QueryClientProvider client={queryClientInstance}>
          <Router>
            <AppRoutes />
          </Router>
          <Toaster />
        </QueryClientProvider>
      </LanguageProvider>
    </ThemeProvider>
  )
}

export default App
