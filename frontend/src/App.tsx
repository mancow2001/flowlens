import { Routes, Route, Navigate } from 'react-router-dom';
import { useEffect, useCallback } from 'react';
import Layout from './components/layout/Layout';
import Dashboard from './pages/Dashboard';
import Topology from './pages/Topology';
import Assets from './pages/Assets';
import AssetDetail from './pages/AssetDetail';
import Applications from './pages/Applications';
import ApplicationDetail from './pages/ApplicationDetail';
import Dependencies from './pages/Dependencies';
import Alerts from './pages/Alerts';
import AlertRules from './pages/AlertRules';
import Maintenance from './pages/Maintenance';
import Changes from './pages/Changes';
import ClassificationRules from './pages/ClassificationRules';
import Analysis from './pages/Analysis';
import Tasks from './pages/Tasks';
import SystemSettings from './pages/SystemSettings';
import Login from './pages/Login';
import Setup from './pages/Setup';
import UserManagement from './pages/UserManagement';
import SAMLConfiguration from './pages/SAMLConfiguration';
import DiscoveryProviders from './pages/DiscoveryProviders';
import ProtectedRoute from './components/auth/ProtectedRoute';
import { useWebSocket } from './hooks/useWebSocket';
import { useWebSocketEvents } from './hooks/useWebSocketEvents';
import { ToastContainer, toast } from './components/common/Toast';

function App() {
  const { connect, disconnect } = useWebSocket();

  // Handle alert notifications via toast
  const handleAlertCreated = useCallback((data: Record<string, unknown>) => {
    const severity = (data.severity as string) || 'info';
    const title = (data.title as string) || 'New Alert';
    const message = (data.message as string) || undefined;
    toast.alert(severity, title, message);
  }, []);

  // Set up WebSocket event handlers
  useWebSocketEvents({
    onAlertCreated: handleAlertCreated,
  });

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return (
    <>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/setup" element={<Setup />} />

        {/* Protected routes with layout */}
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <Layout>
                <Routes>
                  <Route path="/" element={<Navigate to="/dashboard" replace />} />
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/topology" element={<Topology />} />
                  <Route path="/assets" element={<Assets />} />
                  <Route path="/assets/:id" element={<AssetDetail />} />
                  <Route path="/applications" element={<Applications />} />
                  <Route path="/applications/:id" element={<ApplicationDetail />} />
                  <Route path="/dependencies" element={<Dependencies />} />
                  <Route path="/alerts" element={<Alerts />} />
                  <Route path="/changes" element={<Changes />} />
                  <Route path="/analysis" element={<Analysis />} />
                  <Route path="/tasks" element={<Tasks />} />

                  {/* Analyst+ routes */}
                  <Route
                    path="/settings/classification"
                    element={
                      <ProtectedRoute requiredRoles={['admin', 'analyst']}>
                        <ClassificationRules />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/settings/alert-rules"
                    element={
                      <ProtectedRoute requiredRoles={['admin', 'analyst']}>
                        <AlertRules />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/settings/maintenance"
                    element={
                      <ProtectedRoute requiredRoles={['admin', 'analyst']}>
                        <Maintenance />
                      </ProtectedRoute>
                    }
                  />

                  {/* Admin-only routes */}
                  <Route
                    path="/settings/system"
                    element={
                      <ProtectedRoute requiredRoles={['admin']}>
                        <SystemSettings />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/settings/users"
                    element={
                      <ProtectedRoute requiredRoles={['admin']}>
                        <UserManagement />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/settings/saml"
                    element={
                      <ProtectedRoute requiredRoles={['admin']}>
                        <SAMLConfiguration />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/settings/discovery"
                    element={
                      <ProtectedRoute requiredRoles={['admin']}>
                        <DiscoveryProviders />
                      </ProtectedRoute>
                    }
                  />
                </Routes>
              </Layout>
            </ProtectedRoute>
          }
        />
      </Routes>
      <ToastContainer />
    </>
  );
}

export default App;
