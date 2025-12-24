import { create } from 'zustand';
import type { Alert, ChangeEvent, DashboardStats } from '../types';

interface AppState {
  // Selected items
  selectedAssetId: string | null;
  selectedAlertId: string | null;

  // Dashboard data
  stats: DashboardStats | null;
  recentAlerts: Alert[];
  recentChanges: ChangeEvent[];

  // UI state
  sidebarCollapsed: boolean;
  topologyViewMode: 'full' | 'focused';

  // Actions
  setSelectedAssetId: (id: string | null) => void;
  setSelectedAlertId: (id: string | null) => void;
  setStats: (stats: DashboardStats) => void;
  setRecentAlerts: (alerts: Alert[]) => void;
  setRecentChanges: (changes: ChangeEvent[]) => void;
  toggleSidebar: () => void;
  setTopologyViewMode: (mode: 'full' | 'focused') => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Initial state
  selectedAssetId: null,
  selectedAlertId: null,
  stats: null,
  recentAlerts: [],
  recentChanges: [],
  sidebarCollapsed: false,
  topologyViewMode: 'full',

  // Actions
  setSelectedAssetId: (id) => set({ selectedAssetId: id }),
  setSelectedAlertId: (id) => set({ selectedAlertId: id }),
  setStats: (stats) => set({ stats }),
  setRecentAlerts: (alerts) => set({ recentAlerts: alerts }),
  setRecentChanges: (changes) => set({ recentChanges: changes }),
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setTopologyViewMode: (mode) => set({ topologyViewMode: mode }),
}));
