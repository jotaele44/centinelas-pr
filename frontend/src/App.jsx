import { Toaster } from "@/components/ui/toaster"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from '@/lib/query-client'
import { BrowserRouter as Router, Navigate, Route, Routes } from 'react-router-dom';
import PageNotFound from './lib/PageNotFound';
import { AuthProvider, useAuth } from '@/lib/AuthContext';
import { ThemeProvider } from '@/lib/ThemeContext';
import { LanguageProvider } from '@/lib/LanguageContext';
import UserNotRegisteredError from '@/components/UserNotRegisteredError';
import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Home from './pages/Home';
import Monitor from './pages/Monitor';
import Signals from './pages/Signals';
import Matters from './pages/Matters';
import MatterDetail from './pages/MatterDetail';
import Sources from './pages/Sources';
import Handoff from './pages/Handoff';
import Pipeline from './pages/Pipeline';
import PipelineItemDetail from './pages/PipelineItemDetail';
import Layout from './components/Layout';
import SignalsTable from './pages/SignalsTable';
import Entities from './pages/Entities';
import EntityDetail from './pages/EntityDetail';

const AuthenticatedApp = () => {
  const { isLoadingAuth, isLoadingPublicSettings, authError, navigateToLogin } = useAuth();

  if (isLoadingPublicSettings || isLoadingAuth) {
    return (
      <div className="fixed inset-0 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-muted border-t-foreground rounded-full animate-spin" />
      </div>
    );
  }

  if (authError) {
    if (authError.type === 'user_not_registered') {
      return <UserNotRegisteredError />;
    } else if (authError.type === 'auth_required') {
      navigateToLogin();
      return null;
    }
  }

  return (
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

        {/* Signal-centric views converted from the legacy legislative surface. */}
        <Route path="/tabla" element={<SignalsTable />} />
        <Route path="/entidades" element={<Entities />} />
        <Route path="/entidad/:slug" element={<EntityDetail />} />
        {/* Back-compat: old legislator routes now resolve to the entity list. */}
        <Route path="/autores" element={<Navigate to="/entidades" replace />} />

        {/* Normalized auth routes. */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/Login" element={<Navigate to="/login" replace />} />
        <Route path="/Register" element={<Navigate to="/register" replace />} />
        <Route path="/ForgotPassword" element={<Navigate to="/forgot-password" replace />} />
        <Route path="/ResetPassword" element={<Navigate to="/reset-password" replace />} />
      </Route>
      <Route path="*" element={<PageNotFound />} />
    </Routes>
  );
};

function App() {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <AuthProvider>
          <QueryClientProvider client={queryClientInstance}>
            <Router>
              <AuthenticatedApp />
            </Router>
            <Toaster />
          </QueryClientProvider>
        </AuthProvider>
      </LanguageProvider>
    </ThemeProvider>
  )
}

export default App
