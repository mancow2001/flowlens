import { useState, useEffect } from 'react';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { authApi } from '../services/api';
import { useAuthStore } from '../stores/authStore';
import Button from '../components/common/Button';

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);

  const { setTokens, setUser, setAuthSettings, isAuthenticated } = useAuthStore();

  // Get redirect path from location state or default to dashboard
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/dashboard';

  // Handle SAML callback with tokens in URL
  useEffect(() => {
    const accessToken = searchParams.get('access_token');
    const refreshToken = searchParams.get('refresh_token');
    const returnTo = searchParams.get('return_to') || '/dashboard';
    const errorParam = searchParams.get('error');

    if (errorParam) {
      setError(decodeURIComponent(errorParam));
      // Clear URL params
      navigate('/login', { replace: true });
      return;
    }

    if (accessToken && refreshToken) {
      // SAML callback - store tokens and fetch user
      setTokens(accessToken, refreshToken);

      authApi.getCurrentUser()
        .then((user) => {
          setUser(user);
          navigate(returnTo, { replace: true });
        })
        .catch(() => {
          setError('Failed to fetch user information after SAML login');
          navigate('/login', { replace: true });
        });
    }
  }, [searchParams, setTokens, setUser, navigate]);

  // Check auth status
  const { data: authStatus, isLoading: isLoadingStatus } = useQuery({
    queryKey: ['auth-status'],
    queryFn: authApi.getStatus,
    retry: false,
  });

  // Update auth settings when status is fetched
  useEffect(() => {
    if (authStatus) {
      setAuthSettings(authStatus.auth_enabled, authStatus.saml_enabled);

      // If auth is disabled, redirect to dashboard
      if (!authStatus.auth_enabled) {
        navigate('/dashboard', { replace: true });
        return;
      }

      // If setup is required (no users exist), redirect to setup
      if (authStatus.setup_required) {
        navigate('/setup', { replace: true });
      }
    }
  }, [authStatus, setAuthSettings, navigate]);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated()) {
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, navigate, from]);

  // Login mutation
  const loginMutation = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      authApi.login(email, password),
    onSuccess: async (data) => {
      setTokens(data.access_token, data.refresh_token);

      // Fetch current user info
      try {
        const user = await authApi.getCurrentUser();
        setUser(user);
        navigate(from, { replace: true });
      } catch {
        setError('Failed to fetch user information');
      }
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      const message = error.response?.data?.detail || 'Login failed. Please check your credentials.';
      setError(message);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    loginMutation.mutate({ email, password });
  };

  const handleSamlLogin = () => {
    // Redirect to SAML login endpoint
    window.location.href = '/api/v1/auth/saml/login';
  };

  if (isLoadingStatus) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="text-slate-400">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900 px-4">
      <div className="max-w-md w-full space-y-8">
        {/* Logo/Header */}
        <div className="text-center">
          <h1 className="text-3xl font-bold text-white">FlowLens</h1>
          <p className="mt-2 text-sm text-slate-400">
            Application Dependency Mapping
          </p>
        </div>

        {/* Login Card */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-8">
          <h2 className="text-xl font-semibold text-white mb-6">Sign in to your account</h2>

          {/* Error Message */}
          {error && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/50 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          {/* Local Login Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-slate-300 mb-1">
                Email address
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-300 mb-1">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                placeholder="Enter your password"
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              className="w-full"
              disabled={loginMutation.isPending}
            >
              {loginMutation.isPending ? 'Signing in...' : 'Sign in'}
            </Button>
          </form>

          {/* SAML Login Option */}
          {authStatus?.saml_enabled && authStatus.active_provider && (
            <>
              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-slate-700" />
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-2 bg-slate-800 text-slate-400">Or continue with</span>
                </div>
              </div>

              <Button
                type="button"
                variant="secondary"
                className="w-full"
                onClick={handleSamlLogin}
              >
                Sign in with {authStatus.active_provider.name}
              </Button>
            </>
          )}
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-slate-500">
          Protected by FlowLens RBAC
        </p>
      </div>
    </div>
  );
}
