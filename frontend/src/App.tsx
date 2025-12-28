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
          <Route path="/settings/classification" element={<ClassificationRules />} />
          <Route path="/settings/alert-rules" element={<AlertRules />} />
          <Route path="/settings/maintenance" element={<Maintenance />} />
          <Route path="/settings/system" element={<SystemSettings />} />
        </Routes>
      </Layout>
      <ToastContainer />
    </>
  );
}

export default App;
