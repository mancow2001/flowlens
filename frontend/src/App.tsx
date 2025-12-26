import { Routes, Route, Navigate } from 'react-router-dom';
import { useEffect } from 'react';
import Layout from './components/layout/Layout';
import Dashboard from './pages/Dashboard';
import Topology from './pages/Topology';
import Assets from './pages/Assets';
import AssetDetail from './pages/AssetDetail';
import Dependencies from './pages/Dependencies';
import Alerts from './pages/Alerts';
import Changes from './pages/Changes';
import ClassificationRules from './pages/ClassificationRules';
import { useWebSocket } from './hooks/useWebSocket';

function App() {
  const { connect, disconnect } = useWebSocket();

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/topology" element={<Topology />} />
        <Route path="/assets" element={<Assets />} />
        <Route path="/assets/:id" element={<AssetDetail />} />
        <Route path="/dependencies" element={<Dependencies />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/changes" element={<Changes />} />
        <Route path="/settings/classification" element={<ClassificationRules />} />
      </Routes>
    </Layout>
  );
}

export default App;
