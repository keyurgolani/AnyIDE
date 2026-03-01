import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from './store/authStore'
import LoginPage from './pages/LoginPage'
import DashboardLayout from './components/layout/DashboardLayout'
import DashboardPage from './pages/DashboardPage'
import HITLQueuePage from './pages/HITLQueuePage'
import AuditLogPage from './pages/AuditLogPage'
import SystemHealthPage from './pages/SystemHealthPage'
import ToolExplorerPage from './pages/ToolExplorerPage'
import ConfigPage from './pages/ConfigPage'
import SecretsPage from './pages/SecretsPage'
import ContainersPage from './pages/ContainersPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  
  return <>{children}</>
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/admin">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <DashboardLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="hitl" element={<HITLQueuePage />} />
            <Route path="audit" element={<AuditLogPage />} />
            <Route path="health" element={<SystemHealthPage />} />
            <Route path="tools" element={<ToolExplorerPage />} />
            <Route path="config" element={<ConfigPage />} />
            <Route path="secrets" element={<SecretsPage />} />
            <Route path="containers" element={<ContainersPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
