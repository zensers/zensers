// components/chat/OptionSelector.tsx

'use client';

import { cn } from '@/lib/utils';
import type { SelectOption } from '@/types/api';
import { Check, ChevronRight } from 'lucide-react';

interface OptionSelectorProps {
  title: string;
  description?: string;
  options: SelectOption[];
  onSelect: (optionId: string) => void;
  disabled?: boolean;
  selectedId?: string;
  multiSelect?: boolean;
  selectedIds?: string[];
  onMultiSelect?: (ids: string[]) => void;
}

/**
 * Option selector - Apple-style design
 */
export function OptionSelector({
  title,
  description,
  options,
  onSelect,
  disabled = false,
  selectedId,
  multiSelect = false,
  selectedIds = [],
  onMultiSelect,
}: OptionSelectorProps) {
  const handleOptionClick = (optionId: string, optionDisabled?: boolean) => {
    if (disabled || optionDisabled) return;

    if (multiSelect && onMultiSelect) {
      const newSelected = selectedIds.includes(optionId)
        ? selectedIds.filter((id) => id !== optionId)
        : [...selectedIds, optionId];
      onMultiSelect(newSelected);
    } else {
      onSelect(optionId);
    }
  };

  return (
    <div className="w-full animate-scale-in">
      {/* Title area */}
      <div className="px-1 mb-3">
        <h3 className="text-xs font-semibold text-primary uppercase tracking-wider">
          {title}
        </h3>
        {description && (
          <p className="text-sm text-muted-foreground mt-1.5">{description}</p>
        )}
      </div>

      {/* Option list - Apple grouped style */}
      <div className="apple-card overflow-hidden">
        {options.map((option, index) => {
          const isSelected = multiSelect
            ? selectedIds.includes(option.id)
            : selectedId === option.id;
          const isOptionDisabled = option.disabled;
          const isLast = index === options.length - 1;

          return (
            <button
              key={option.id}
              type="button"
              disabled={disabled || isOptionDisabled}
              onClick={() => handleOptionClick(option.id, isOptionDisabled)}
              className={cn(
                'w-full text-left',
                'flex items-center justify-between',
                'px-4 py-3',
                'transition-all duration-200',
                !isLast && 'border-b border-border/50',
                isOptionDisabled
                  ? 'opacity-40 cursor-not-allowed'
                  : 'hover:bg-secondary/50 cursor-pointer active:bg-secondary',
                disabled && 'pointer-events-none',
                isSelected && 'bg-primary/5'
              )}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-foreground">
                    {option.label}
                  </span>
                  {option.required && (
                      <span className="text-[10px] text-primary font-medium px-1.5 py-0.5 bg-primary/10 rounded">
                       Required
                     </span>
                  )}
                </div>
                {option.description && (
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                    {option.description}
                  </p>
                )}
              </div>

              {/* Selected state indicator - Apple style */}
              <div
                className={cn(
                  'shrink-0 ml-3 h-5 w-5 rounded-full flex items-center justify-center',
                  'transition-all duration-200',
                  isSelected
                    ? 'bg-primary'
                    : 'bg-secondary border border-border'
                )}
              >
                {isSelected && (
                  <Check className="h-3 w-3 text-primary-foreground" />
                )}
              </div>
            </button>
          );
        })}
      </div>

      {/* Multi-select confirm button */}
      {multiSelect && onMultiSelect && (
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={() => {}}
            disabled={disabled || selectedIds.length === 0}
            className={cn(
              'apple-button px-5 py-2.5 text-sm',
              selectedIds.length > 0 && !disabled
                ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                : 'bg-secondary text-muted-foreground cursor-not-allowed'
            )}
          >
            Confirm Selection ({selectedIds.length})
          </button>
        </div>
      )}
    </div>
  );
}
