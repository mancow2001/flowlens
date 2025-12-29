import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  PlusIcon,
  PencilIcon,
  TrashIcon,
  KeyIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { userApi } from '../services/api';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import Badge from '../components/common/Badge';
import { LoadingPage } from '../components/common/Loading';
import type { User, UserRole } from '../types';

interface UserFormData {
  email: string;
  name: string;
  password: string;
  role: UserRole;
  is_active: boolean;
}

const initialFormData: UserFormData = {
  email: '',
  name: '',
  password: '',
  role: 'viewer',
  is_active: true,
};

export default function UserManagement() {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isResetPasswordOpen, setIsResetPasswordOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [resetPasswordUser, setResetPasswordUser] = useState<User | null>(null);
  const [formData, setFormData] = useState<UserFormData>(initialFormData);
  const [newPassword, setNewPassword] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Fetch users
  const { data: usersData, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => userApi.list(),
  });

  // Create user mutation
  const createMutation = useMutation({
    mutationFn: (data: UserFormData) => userApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      closeModal();
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setError(err.response?.data?.detail || err.message);
    },
  });

  // Update user mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<UserFormData> }) =>
      userApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      closeModal();
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setError(err.response?.data?.detail || err.message);
    },
  });

  // Deactivate user mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => userApi.deactivate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });

  // Reset password mutation
  const resetPasswordMutation = useMutation({
    mutationFn: ({ id, password }: { id: string; password: string }) =>
      userApi.resetPassword(id, password),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      closeResetPasswordModal();
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setError(err.response?.data?.detail || err.message);
    },
  });

  const openCreateModal = () => {
    setEditingUser(null);
    setFormData(initialFormData);
    setError(null);
    setIsModalOpen(true);
  };

  const openEditModal = (user: User) => {
    setEditingUser(user);
    setFormData({
      email: user.email,
      name: user.name,
      password: '',
      role: user.role,
      is_active: user.is_active,
    });
    setError(null);
    setIsModalOpen(true);
  };

  const openResetPasswordModal = (user: User) => {
    setResetPasswordUser(user);
    setNewPassword('');
    setError(null);
    setIsResetPasswordOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingUser(null);
    setFormData(initialFormData);
    setError(null);
  };

  const closeResetPasswordModal = () => {
    setIsResetPasswordOpen(false);
    setResetPasswordUser(null);
    setNewPassword('');
    setError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (editingUser) {
      // Update existing user - don't send password if empty
      const updateData: Partial<UserFormData> = {
        email: formData.email,
        name: formData.name,
        role: formData.role,
        is_active: formData.is_active,
      };
      updateMutation.mutate({ id: editingUser.id, data: updateData });
    } else {
      // Create new user
      createMutation.mutate(formData);
    }
  };

  const handleResetPassword = (e: React.FormEvent) => {
    e.preventDefault();
    if (resetPasswordUser && newPassword) {
      resetPasswordMutation.mutate({ id: resetPasswordUser.id, password: newPassword });
    }
  };

  const handleDelete = (user: User) => {
    if (confirm(`Are you sure you want to deactivate user "${user.name}"?`)) {
      deleteMutation.mutate(user.id);
    }
  };

  if (isLoading) {
    return <LoadingPage />;
  }

  const users = usersData?.items ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">User Management</h1>
          <p className="text-slate-400 mt-1">Manage local user accounts</p>
        </div>
        <Button onClick={openCreateModal} className="flex items-center gap-2">
          <PlusIcon className="w-4 h-4" />
          Add User
        </Button>
      </div>

      {/* Users Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">Name</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">Email</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">Role</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">Type</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">Status</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">Last Login</th>
                <th className="text-right px-4 py-3 text-sm font-medium text-slate-400">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                    No users found. Create your first user to get started.
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.id} className="border-b border-slate-700/50 hover:bg-slate-800/50">
                    <td className="px-4 py-3">
                      <span className="text-white font-medium">{user.name}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-slate-300">{user.email}</span>
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        variant={
                          user.role === 'admin'
                            ? 'error'
                            : user.role === 'analyst'
                            ? 'warning'
                            : 'info'
                        }
                      >
                        {user.role.charAt(0).toUpperCase() + user.role.slice(1)}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={user.is_local ? 'default' : 'info'}>
                        {user.is_local ? 'Local' : 'SAML'}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={user.is_active ? 'success' : 'default'}>
                        {user.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-slate-400 text-sm">
                        {user.last_login_at
                          ? new Date(user.last_login_at).toLocaleString()
                          : 'Never'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => openEditModal(user)}
                          className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded transition-colors"
                          title="Edit user"
                        >
                          <PencilIcon className="w-4 h-4" />
                        </button>
                        {user.is_local && (
                          <button
                            onClick={() => openResetPasswordModal(user)}
                            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded transition-colors"
                            title="Reset password"
                          >
                            <KeyIcon className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(user)}
                          className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded transition-colors"
                          title="Deactivate user"
                        >
                          <TrashIcon className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Create/Edit Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-xl w-full max-w-md mx-4">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
              <h2 className="text-lg font-semibold text-white">
                {editingUser ? 'Edit User' : 'Create User'}
              </h2>
              <button
                onClick={closeModal}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              {error && (
                <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg text-red-400 text-sm">
                  {error}
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Name
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="John Doe"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Email
                </label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  required
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="john@example.com"
                />
              </div>

              {!editingUser && (
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Password
                  </label>
                  <input
                    type="password"
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    required
                    minLength={8}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                    placeholder="Minimum 8 characters"
                  />
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Role
                </label>
                <select
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value as UserRole })}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  <option value="viewer">Viewer</option>
                  <option value="analyst">Analyst</option>
                  <option value="admin">Admin</option>
                </select>
                <p className="text-slate-500 text-xs mt-1">
                  Admin: Full access. Analyst: Read/write. Viewer: Read only.
                </p>
              </div>

              {editingUser && (
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="is_active"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                  />
                  <label htmlFor="is_active" className="text-slate-300 text-sm">
                    Active account
                  </label>
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4">
                <Button type="button" variant="secondary" onClick={closeModal}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  loading={createMutation.isPending || updateMutation.isPending}
                >
                  {editingUser ? 'Save Changes' : 'Create User'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Reset Password Modal */}
      {isResetPasswordOpen && resetPasswordUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-xl w-full max-w-md mx-4">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
              <h2 className="text-lg font-semibold text-white">Reset Password</h2>
              <button
                onClick={closeResetPasswordModal}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleResetPassword} className="p-6 space-y-4">
              {error && (
                <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg text-red-400 text-sm">
                  {error}
                </div>
              )}

              <p className="text-slate-300">
                Set a new password for <span className="font-medium text-white">{resetPasswordUser.name}</span>
              </p>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  New Password
                </label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  minLength={8}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="Minimum 8 characters"
                />
              </div>

              <div className="flex justify-end gap-3 pt-4">
                <Button type="button" variant="secondary" onClick={closeResetPasswordModal}>
                  Cancel
                </Button>
                <Button type="submit" loading={resetPasswordMutation.isPending}>
                  Reset Password
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
