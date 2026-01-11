/**
 * Asset Type Select Component
 *
 * A grouped dropdown component for selecting asset types, organized by category.
 */

import { Fragment } from 'react';
import { Listbox, Transition } from '@headlessui/react';
import { CheckIcon, ChevronUpDownIcon } from '@heroicons/react/20/solid';
import clsx from 'clsx';
import type { AssetType } from '@/types';
import {
  ASSET_TYPE_GROUPS,
  ASSET_TYPES_BY_GROUP,
  ASSET_TYPE_CONFIG,
  getAssetTypeLabel,
  getAssetTypeColor,
} from '@/constants/assetTypes';

interface AssetTypeSelectProps {
  value: AssetType | '';
  onChange: (value: AssetType | '') => void;
  includeAll?: boolean;
  allLabel?: string;
  className?: string;
  disabled?: boolean;
  showColor?: boolean;
  placeholder?: string;
}

/**
 * Grouped dropdown for selecting asset types.
 *
 * Organizes asset types by category (Compute, Data, Network, etc.) for easier navigation.
 */
export default function AssetTypeSelect({
  value,
  onChange,
  includeAll = true,
  allLabel = 'All Types',
  className,
  disabled = false,
  showColor = true,
  placeholder = 'Select type...',
}: AssetTypeSelectProps) {
  const displayLabel = value ? getAssetTypeLabel(value) : (includeAll ? allLabel : placeholder);
  const displayColor = value ? getAssetTypeColor(value) : undefined;

  return (
    <Listbox value={value} onChange={onChange} disabled={disabled}>
      <div className={clsx('relative', className)}>
        <Listbox.Button
          className={clsx(
            'relative w-full cursor-default rounded-md border py-2 pl-3 pr-10 text-left text-sm',
            'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600',
            'focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
        >
          <span className="flex items-center">
            {showColor && displayColor && (
              <span
                className="mr-2 h-3 w-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: displayColor }}
              />
            )}
            <span className="block truncate text-gray-900 dark:text-gray-100">
              {displayLabel}
            </span>
          </span>
          <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
            <ChevronUpDownIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
          </span>
        </Listbox.Button>

        <Transition
          as={Fragment}
          leave="transition ease-in duration-100"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <Listbox.Options
            className={clsx(
              'absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md py-1 text-sm shadow-lg',
              'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700',
              'focus:outline-none'
            )}
          >
            {/* "All Types" option */}
            {includeAll && (
              <Listbox.Option
                value=""
                className={({ active }) =>
                  clsx(
                    'relative cursor-default select-none py-2 pl-10 pr-4',
                    active
                      ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-900 dark:text-blue-100'
                      : 'text-gray-900 dark:text-gray-100'
                  )
                }
              >
                {({ selected }) => (
                  <>
                    <span className={clsx('block truncate', selected && 'font-medium')}>
                      {allLabel}
                    </span>
                    {selected && (
                      <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-blue-600">
                        <CheckIcon className="h-5 w-5" aria-hidden="true" />
                      </span>
                    )}
                  </>
                )}
              </Listbox.Option>
            )}

            {/* Grouped options */}
            {ASSET_TYPE_GROUPS.filter((group) => {
              // Skip 'Other' group or groups with no options
              if (group === 'Other') return false;
              const types = ASSET_TYPES_BY_GROUP[group];
              return types && types.length > 0;
            }).map((group) => (
              <Fragment key={group}>
                {/* Group header */}
                <div className="px-3 py-1.5 text-xs font-semibold text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/50">
                  {group}
                </div>

                {/* Group options */}
                {ASSET_TYPES_BY_GROUP[group]
                  .filter((type) => type !== 'group')
                  .map((type) => {
                    const config = ASSET_TYPE_CONFIG[type];
                    return (
                      <Listbox.Option
                        key={type}
                        value={type}
                        className={({ active }) =>
                          clsx(
                            'relative cursor-default select-none py-2 pl-10 pr-4',
                            active
                              ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-900 dark:text-blue-100'
                              : 'text-gray-900 dark:text-gray-100'
                          )
                        }
                      >
                        {({ selected }) => (
                          <>
                            <span className="flex items-center">
                              {showColor && (
                                <span
                                  className="mr-2 h-3 w-3 rounded-full flex-shrink-0"
                                  style={{ backgroundColor: config.color }}
                                />
                              )}
                              <span className={clsx('block truncate', selected && 'font-medium')}>
                                {config.label}
                              </span>
                            </span>
                            {selected && (
                              <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-blue-600">
                                <CheckIcon className="h-5 w-5" aria-hidden="true" />
                              </span>
                            )}
                          </>
                        )}
                      </Listbox.Option>
                    );
                  })}
              </Fragment>
            ))}

            {/* Unknown option at the end */}
            <div className="px-3 py-1.5 text-xs font-semibold text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/50">
              Other
            </div>
            <Listbox.Option
              value="unknown"
              className={({ active }) =>
                clsx(
                  'relative cursor-default select-none py-2 pl-10 pr-4',
                  active
                    ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-900 dark:text-blue-100'
                    : 'text-gray-900 dark:text-gray-100'
                )
              }
            >
              {({ selected }) => (
                <>
                  <span className="flex items-center">
                    {showColor && (
                      <span
                        className="mr-2 h-3 w-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: ASSET_TYPE_CONFIG.unknown.color }}
                      />
                    )}
                    <span className={clsx('block truncate', selected && 'font-medium')}>
                      Unknown
                    </span>
                  </span>
                  {selected && (
                    <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-blue-600">
                      <CheckIcon className="h-5 w-5" aria-hidden="true" />
                    </span>
                  )}
                </>
              )}
            </Listbox.Option>
          </Listbox.Options>
        </Transition>
      </div>
    </Listbox>
  );
}

/**
 * Simple native select for asset types (ungrouped, for mobile or simpler UIs).
 */
export function AssetTypeNativeSelect({
  value,
  onChange,
  includeAll = true,
  allLabel = 'All Types',
  className,
  disabled = false,
}: Omit<AssetTypeSelectProps, 'showColor' | 'placeholder'>) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as AssetType | '')}
      disabled={disabled}
      className={clsx(
        'rounded-md border py-2 pl-3 pr-8 text-sm',
        'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-100',
        'focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500',
        disabled && 'opacity-50 cursor-not-allowed',
        className
      )}
    >
      {includeAll && <option value="">{allLabel}</option>}
      {ASSET_TYPE_GROUPS.filter((group) => group !== 'Other').map((group) => (
        <optgroup key={group} label={group}>
          {ASSET_TYPES_BY_GROUP[group]
            .filter((type) => type !== 'group')
            .map((type) => (
              <option key={type} value={type}>
                {ASSET_TYPE_CONFIG[type].label}
              </option>
            ))}
        </optgroup>
      ))}
      <optgroup label="Other">
        <option value="unknown">Unknown</option>
      </optgroup>
    </select>
  );
}
