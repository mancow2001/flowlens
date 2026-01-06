import { Link, useLocation } from 'react-router-dom';
import {
  HomeIcon,
  ServerStackIcon,
  ArrowsRightLeftIcon,
  BellAlertIcon,
  ClockIcon,
  ChartBarIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  TagIcon,
  BeakerIcon,
  AdjustmentsHorizontalIcon,
  WrenchScrewdriverIcon,
  Cog6ToothIcon,
  QueueListIcon,
  CubeTransparentIcon,
  UsersIcon,
  ShieldCheckIcon,
  ShieldExclamationIcon,
  CloudIcon,
} from '@heroicons/react/24/outline';
import { useAppStore } from '../../stores/appStore';
import { useAuthStore } from '../../stores/authStore';
import clsx from 'clsx';
import type { UserRole } from '../../types';

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: HomeIcon },
  { name: 'Topology', href: '/topology', icon: ChartBarIcon },
  { name: 'Assets', href: '/assets', icon: ServerStackIcon },
  { name: 'Applications', href: '/applications', icon: CubeTransparentIcon },
  { name: 'Segmentation', href: '/segmentation-policies', icon: ShieldExclamationIcon },
  { name: 'Dependencies', href: '/dependencies', icon: ArrowsRightLeftIcon },
  { name: 'Alerts', href: '/alerts', icon: BellAlertIcon },
  { name: 'Changes', href: '/changes', icon: ClockIcon },
  { name: 'Analysis', href: '/analysis', icon: BeakerIcon },
  { name: 'Tasks', href: '/tasks', icon: QueueListIcon },
];

interface NavItem {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  requiredRoles?: UserRole[];
}

const settingsNavigation: NavItem[] = [
  { name: 'Classification Rules', href: '/settings/classification', icon: TagIcon, requiredRoles: ['admin', 'analyst'] },
  { name: 'Alert Rules', href: '/settings/alert-rules', icon: AdjustmentsHorizontalIcon, requiredRoles: ['admin', 'analyst'] },
  { name: 'Maintenance', href: '/settings/maintenance', icon: WrenchScrewdriverIcon, requiredRoles: ['admin', 'analyst'] },
  { name: 'Discovery Providers', href: '/settings/discovery', icon: CloudIcon, requiredRoles: ['admin'] },
  { name: 'System Settings', href: '/settings/system', icon: Cog6ToothIcon, requiredRoles: ['admin'] },
  { name: 'User Management', href: '/settings/users', icon: UsersIcon, requiredRoles: ['admin'] },
  { name: 'SAML Configuration', href: '/settings/saml', icon: ShieldCheckIcon, requiredRoles: ['admin'] },
];

export default function Sidebar() {
  const location = useLocation();
  const { sidebarCollapsed, toggleSidebar } = useAppStore();
  const { hasRole, authEnabled } = useAuthStore();

  // Filter settings navigation based on user role
  const filteredSettingsNavigation = settingsNavigation.filter((item) => {
    // If auth is disabled, show all items
    if (!authEnabled) return true;
    // If no role requirements, show the item
    if (!item.requiredRoles) return true;
    // Check if user has required role
    return hasRole(item.requiredRoles);
  });

  return (
    <div
      className={clsx(
        'fixed inset-y-0 left-0 z-50 flex flex-col bg-slate-800 border-r border-slate-700 transition-all duration-300',
        sidebarCollapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* Logo */}
      <div className={clsx(
        "flex items-center h-16 border-b border-slate-700",
        sidebarCollapsed ? "px-4 justify-center" : "px-1"
      )}>
        <img
          src={sidebarCollapsed ? "/FlowLens_logo_small.png" : "/FlowLens_logo_full.png"}
          alt="FlowLens"
          className={sidebarCollapsed ? "h-8 w-8" : "w-full h-full object-contain"}
        />
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
        {navigation.map((item) => {
          const isActive = location.pathname === item.href;
          return (
            <Link
              key={item.name}
              to={item.href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2 rounded-lg transition-colors',
                isActive
                  ? 'bg-primary-600 text-white'
                  : 'text-slate-300 hover:bg-slate-700 hover:text-white'
              )}
            >
              <item.icon className="w-5 h-5 flex-shrink-0" />
              {!sidebarCollapsed && <span>{item.name}</span>}
            </Link>
          );
        })}

        {/* Settings Section */}
        {filteredSettingsNavigation.length > 0 && (
          <div className="pt-4 mt-4 border-t border-slate-700">
            {!sidebarCollapsed && (
              <p className="px-3 pb-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Settings
              </p>
            )}
            {filteredSettingsNavigation.map((item) => {
              const isActive = location.pathname === item.href;
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={clsx(
                    'flex items-center gap-3 px-3 py-2 rounded-lg transition-colors',
                    isActive
                      ? 'bg-primary-600 text-white'
                      : 'text-slate-300 hover:bg-slate-700 hover:text-white'
                  )}
                >
                  <item.icon className="w-5 h-5 flex-shrink-0" />
                  {!sidebarCollapsed && <span>{item.name}</span>}
                </Link>
              );
            })}
          </div>
        )}
      </nav>

      {/* Collapse button */}
      <button
        onClick={toggleSidebar}
        className="flex items-center justify-center h-12 border-t border-slate-700 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
      >
        {sidebarCollapsed ? (
          <ChevronRightIcon className="w-5 h-5" />
        ) : (
          <ChevronLeftIcon className="w-5 h-5" />
        )}
      </button>
    </div>
  );
}
