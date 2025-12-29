import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, UserRole } from '../types';

interface AuthState {
  // User state
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;

  // Loading state
  isLoading: boolean;
  isInitialized: boolean;

  // Auth settings from server
  authEnabled: boolean;
  samlEnabled: boolean;

  // Actions
  setUser: (user: User | null) => void;
  setTokens: (accessToken: string, refreshToken: string) => void;
  clearAuth: () => void;
  setLoading: (loading: boolean) => void;
  setInitialized: (initialized: boolean) => void;
  setAuthSettings: (authEnabled: boolean, samlEnabled: boolean) => void;

  // Computed helpers (as methods for Zustand)
  hasRole: (roles: UserRole[]) => boolean;
  isAdmin: () => boolean;
  isAnalyst: () => boolean;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      // Initial state
      user: null,
      accessToken: null,
      refreshToken: null,
      isLoading: false,
      isInitialized: false,
      authEnabled: true,
      samlEnabled: false,

      // Actions
      setUser: (user) => set({ user }),

      setTokens: (accessToken, refreshToken) =>
        set({ accessToken, refreshToken }),

      clearAuth: () =>
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
        }),

      setLoading: (isLoading) => set({ isLoading }),

      setInitialized: (isInitialized) => set({ isInitialized }),

      setAuthSettings: (authEnabled, samlEnabled) =>
        set({ authEnabled, samlEnabled }),

      // Role checking helpers
      hasRole: (roles) => {
        const { user, authEnabled } = get();

        // If auth is disabled, treat as having all permissions
        if (!authEnabled) return true;

        if (!user) return false;

        return roles.includes(user.role);
      },

      isAdmin: () => {
        const { user, authEnabled } = get();
        if (!authEnabled) return true;
        return user?.role === 'admin';
      },

      isAnalyst: () => {
        const { user, authEnabled } = get();
        if (!authEnabled) return true;
        return user?.role === 'admin' || user?.role === 'analyst';
      },

      isAuthenticated: () => {
        const { user, accessToken, authEnabled } = get();

        // If auth is disabled, treat as authenticated
        if (!authEnabled) return true;

        return user !== null && accessToken !== null;
      },
    }),
    {
      name: 'flowlens-auth',
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
      }),
    }
  )
);

// Helper hook for role-based access
export function useHasRole(roles: UserRole[]): boolean {
  const hasRole = useAuthStore((state) => state.hasRole);
  return hasRole(roles);
}

// Helper hook for checking if user is admin
export function useIsAdmin(): boolean {
  const isAdmin = useAuthStore((state) => state.isAdmin);
  return isAdmin();
}

// Helper hook for checking if user is analyst or higher
export function useIsAnalyst(): boolean {
  const isAnalyst = useAuthStore((state) => state.isAnalyst);
  return isAnalyst();
}

// Helper hook for checking authentication status
export function useIsAuthenticated(): boolean {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  return isAuthenticated();
}
