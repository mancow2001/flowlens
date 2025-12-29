import { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '../../stores/authStore';
import { authApi } from '../../services/api';
import type { UserRole } from '../../types';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRoles?: UserRole[];
}

export default function ProtectedRoute({ children, requiredRoles }: ProtectedRouteProps) {
  const location = useLocation();
  const {
    user,
    accessToken,
    setUser,
    setAuthSettings,
    setInitialized,
    isInitialized,
    hasRole,
    clearAuth,
  } = useAuthStore();

  const [isChecking, setIsChecking] = useState(!isInitialized);

  // Check auth status on mount - this is the source of truth for auth_enabled
  const { data: authStatus, isLoading: isLoadingStatus, isError: isStatusError } = useQuery({
    queryKey: ['auth-status'],
    queryFn: authApi.getStatus,
    retry: 1,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Update auth settings when status is fetched
  useEffect(() => {
    if (authStatus) {
      setAuthSettings(authStatus.auth_enabled, authStatus.saml_enabled);
    }
  }, [authStatus, setAuthSettings]);

  // Determine if auth is enabled from the API response (source of truth)
  // Only fetch user if auth is enabled AND we have a token
  const authEnabledFromApi = authStatus?.auth_enabled ?? true;

  // Fetch current user if we have a token but no user data
  const { isLoading: isLoadingUser } = useQuery({
    queryKey: ['current-user'],
    queryFn: async () => {
      const userData = await authApi.getCurrentUser();
      setUser(userData);
      return userData;
    },
    enabled: authEnabledFromApi && !!accessToken && !user,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  // Mark as initialized once we have auth status and user (if applicable)
  useEffect(() => {
    if (!isLoadingStatus && !isLoadingUser) {
      setIsChecking(false);
      setInitialized(true);
    }
  }, [isLoadingStatus, isLoadingUser, setInitialized]);

  // Show loading state while checking auth status
  // We must wait for auth status before making any redirect decisions
  if (isChecking || isLoadingStatus) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-slate-400">Loading...</span>
        </div>
      </div>
    );
  }

  // If auth status fetch failed, show error
  if (isStatusError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="text-center">
          <h1 className="text-xl font-bold text-white mb-2">Connection Error</h1>
          <p className="text-slate-400 mb-4">Unable to connect to the API server.</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // If auth is disabled (from API response), allow access to all routes
  if (!authEnabledFromApi) {
    return <>{children}</>;
  }

  // Still loading user data after auth status confirmed
  if (isLoadingUser) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-slate-400">Loading...</span>
        </div>
      </div>
    );
  }

  // If setup is required (no users exist), redirect to setup page
  if (authStatus?.setup_required) {
    return <Navigate to="/setup" replace />;
  }

  // If not authenticated, redirect to login
  if (!accessToken || !user) {
    // Clear any stale auth state
    clearAuth();

    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Check role requirements
  if (requiredRoles && requiredRoles.length > 0 && !hasRole(requiredRoles)) {
    // User doesn't have required role - show access denied
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white mb-2">Access Denied</h1>
          <p className="text-slate-400 mb-4">
            You don't have permission to access this page.
          </p>
          <p className="text-sm text-slate-500">
            Required roles: {requiredRoles.join(', ')}
          </p>
          <p className="text-sm text-slate-500">
            Your role: {user.role}
          </p>
        </div>
      </div>
    );
  }

  // User is authenticated and has required role
  return <>{children}</>;
}
