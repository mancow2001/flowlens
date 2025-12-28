import { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { Link } from 'react-router-dom';
import Badge from '../common/Badge';
import Button from '../common/Button';
import { formatRelativeTime } from '../../utils/format';
import type { Alert } from '../../types';

interface AlertDetailSlideOverProps {
  alert: Alert | null;
  isOpen: boolean;
  onClose: () => void;
  onAcknowledge: (id: string) => void;
  onResolve: (id: string) => void;
  isAcknowledging?: boolean;
  isResolving?: boolean;
}

export default function AlertDetailSlideOver({
  alert,
  isOpen,
  onClose,
  onAcknowledge,
  onResolve,
  isAcknowledging = false,
  isResolving = false,
}: AlertDetailSlideOverProps) {
  if (!alert) return null;

  const getSeverityVariant = (severity: string) => {
    switch (severity) {
      case 'critical':
      case 'error':
        return 'error';
      case 'warning':
        return 'warning';
      default:
        return 'info';
    }
  };

  const getStatusBadge = () => {
    if (alert.is_resolved) {
      return <Badge variant="success">Resolved</Badge>;
    }
    if (alert.is_acknowledged) {
      return <Badge variant="warning">Acknowledged</Badge>;
    }
    return <Badge variant="error">Open</Badge>;
  };

  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-in-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in-out duration-300"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/50 transition-opacity" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-hidden">
          <div className="absolute inset-0 overflow-hidden">
            <div className="pointer-events-none fixed inset-y-0 right-0 flex max-w-full pl-10">
              <Transition.Child
                as={Fragment}
                enter="transform transition ease-in-out duration-300"
                enterFrom="translate-x-full"
                enterTo="translate-x-0"
                leave="transform transition ease-in-out duration-300"
                leaveFrom="translate-x-0"
                leaveTo="translate-x-full"
              >
                <Dialog.Panel className="pointer-events-auto w-screen max-w-lg">
                  <div className="flex h-full flex-col overflow-y-auto bg-slate-800 shadow-xl">
                    {/* Header */}
                    <div className="px-6 py-4 border-b border-slate-700">
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-3">
                          <Badge variant={getSeverityVariant(alert.severity)}>
                            {alert.severity}
                          </Badge>
                          {getStatusBadge()}
                        </div>
                        <button
                          type="button"
                          className="rounded-md text-slate-400 hover:text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                          onClick={onClose}
                        >
                          <span className="sr-only">Close panel</span>
                          <XMarkIcon className="h-6 w-6" aria-hidden="true" />
                        </button>
                      </div>
                      <Dialog.Title className="text-lg font-semibold text-white mt-3">
                        {alert.title}
                      </Dialog.Title>
                    </div>

                    {/* Content */}
                    <div className="flex-1 px-6 py-4 space-y-6">
                      {/* Message */}
                      <div>
                        <h4 className="text-sm font-medium text-slate-400 mb-2">
                          Message
                        </h4>
                        <p className="text-white whitespace-pre-wrap">
                          {alert.message}
                        </p>
                      </div>

                      {/* Related Asset */}
                      {alert.asset_id && (
                        <div>
                          <h4 className="text-sm font-medium text-slate-400 mb-2">
                            Related Asset
                          </h4>
                          <Link
                            to={`/assets/${alert.asset_id}`}
                            className="text-primary-400 hover:text-primary-300 hover:underline"
                            onClick={onClose}
                          >
                            View Asset Details
                          </Link>
                        </div>
                      )}

                      {/* Timestamps */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <h4 className="text-sm font-medium text-slate-400 mb-1">
                            Created
                          </h4>
                          <p className="text-white">
                            {formatRelativeTime(alert.created_at)}
                          </p>
                          <p className="text-xs text-slate-500">
                            {new Date(alert.created_at).toLocaleString()}
                          </p>
                        </div>
                        <div>
                          <h4 className="text-sm font-medium text-slate-400 mb-1">
                            Updated
                          </h4>
                          <p className="text-white">
                            {formatRelativeTime(alert.updated_at)}
                          </p>
                        </div>
                      </div>

                      {/* Acknowledgment Info */}
                      {alert.is_acknowledged && (
                        <div className="p-4 bg-slate-700/50 rounded-lg">
                          <h4 className="text-sm font-medium text-slate-400 mb-2">
                            Acknowledgment
                          </h4>
                          <div className="space-y-1">
                            <p className="text-white">
                              By: {alert.acknowledged_by || 'Unknown'}
                            </p>
                            {alert.acknowledged_at && (
                              <p className="text-sm text-slate-400">
                                {new Date(alert.acknowledged_at).toLocaleString()}
                              </p>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Resolution Info */}
                      {alert.is_resolved && (
                        <div className="p-4 bg-green-900/20 border border-green-800/30 rounded-lg">
                          <h4 className="text-sm font-medium text-green-400 mb-2">
                            Resolution
                          </h4>
                          <div className="space-y-2">
                            <p className="text-white">
                              By: {alert.resolved_by || 'Unknown'}
                            </p>
                            {alert.resolved_at && (
                              <p className="text-sm text-slate-400">
                                {new Date(alert.resolved_at).toLocaleString()}
                              </p>
                            )}
                            {alert.resolution_notes && (
                              <div className="mt-2 pt-2 border-t border-green-800/30">
                                <p className="text-sm text-slate-400 mb-1">Notes:</p>
                                <p className="text-white whitespace-pre-wrap">
                                  {alert.resolution_notes}
                                </p>
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Notification Status */}
                      <div>
                        <h4 className="text-sm font-medium text-slate-400 mb-2">
                          Notification
                        </h4>
                        {alert.notification_sent ? (
                          <Badge variant="success">Sent</Badge>
                        ) : (
                          <Badge variant="default">Not Sent</Badge>
                        )}
                      </div>

                      {/* Tags */}
                      {alert.tags && Object.keys(alert.tags).length > 0 && (
                        <div>
                          <h4 className="text-sm font-medium text-slate-400 mb-2">
                            Tags
                          </h4>
                          <div className="flex flex-wrap gap-2">
                            {Object.entries(alert.tags).map(([key, value]) => (
                              <span
                                key={key}
                                className="px-2 py-1 bg-slate-700 rounded text-sm text-slate-300"
                              >
                                {key}: {value}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* IDs for debugging/linking */}
                      <div className="pt-4 border-t border-slate-700">
                        <h4 className="text-sm font-medium text-slate-400 mb-2">
                          Details
                        </h4>
                        <div className="space-y-1 text-xs text-slate-500 font-mono">
                          <p>Alert ID: {alert.id}</p>
                          {alert.change_event_id && (
                            <p>Change Event: {alert.change_event_id}</p>
                          )}
                          {alert.dependency_id && (
                            <p>Dependency: {alert.dependency_id}</p>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Footer Actions */}
                    {(!alert.is_acknowledged || !alert.is_resolved) && (
                      <div className="px-6 py-4 border-t border-slate-700 flex gap-3">
                        {!alert.is_acknowledged && (
                          <Button
                            variant="secondary"
                            onClick={() => onAcknowledge(alert.id)}
                            disabled={isAcknowledging}
                          >
                            {isAcknowledging ? 'Acknowledging...' : 'Acknowledge'}
                          </Button>
                        )}
                        {!alert.is_resolved && (
                          <Button
                            variant="primary"
                            onClick={() => onResolve(alert.id)}
                            disabled={isResolving}
                          >
                            {isResolving ? 'Resolving...' : 'Resolve'}
                          </Button>
                        )}
                      </div>
                    )}
                  </div>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  );
}
