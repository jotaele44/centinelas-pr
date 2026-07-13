import { Toaster } from "@/components/ui/toaster"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from '@/lib/query-client'
import { BrowserRouter as Router, Navigate, Route, Routes } from 'react-router-dom';
import PageNotFound from './lib/PageNotFound';
import { AuthProvider, useAuth } from '@/lib/AuthContext';
import { ThemeProvider } from '@/lib/ThemeContext';
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
import LawDetail from './pages/LawDetail';
import LawTable from './pages/LawTable';
import Profile from './pages/Profile';
import Authors from './pages/Authors';
import AuthorDetail from './pages/AuthorDetail';

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

        {/* Legacy legislative routes retained as backward-compatible MoneySweep/LegislativeMeasure bridge. */}
        <Route path="/ley/:id" element={<LawDetail />} />
        <Route path="/tabla" element={<LawTable />} />
        <Route path="/perfil" element={<Profile />} />
        <Route path="/autores" element={<Authors />} />
        <Route path="/autor/:id" element={<AuthorDetail />} />

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
      <AuthProvider>
        <QueryClientProvider client={queryClientInstance}>
          <Router>
            <AuthenticatedApp />
          </Router>
          <Toaster />
        </QueryClientProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}

export default App
