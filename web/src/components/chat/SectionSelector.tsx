// components/chat/SectionSelector.tsx

'use client';

import { useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import type { SelectOption } from '@/types/api';
import type { FrameworkSection, FrameworkSubSection } from '@/types/api';
import { Check, ChevronDown, ChevronRight } from 'lucide-react';

interface SectionSelectorProps {
  title?: string;
  description?: string;
  sections: SelectOption[];
  frameworkTree?: FrameworkSection[];
  onConfirm: (selectedIds: string[]) => void;
  disabled?: boolean;
}

export function SectionSelector({
  title = 'Select Report Sections',
  description = 'Choose the sections you want to include in the report',
  sections,
  frameworkTree,
  onConfirm,
  disabled = false,
}: SectionSelectorProps) {
  const [selectedIds, setSelectedIds] = useState<string[]>(() =>
    sections.filter((s) => s.required || s.selected).map((s) => s.id)
  );
  const [expandedSections, setExpandedSections] = useState<Set<string>>(() =>
    frameworkTree ? new Set(frameworkTree.map((s) => s.name)) : new Set()
  );

  useEffect(() => {
    setSelectedIds(sections.filter((s) => s.required || s.selected).map((s) => s.id));
  }, [sections]);

  const toggleSection = (id: string, isRequired: boolean) => {
    if (isRequired || disabled) return;
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  const toggleExpand = (name: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const handleConfirm = () => {
    const requiredIds = sections.filter((s) => s.required === true).map((s) => s.id);
    const finalIds = [...requiredIds, ...selectedIds.filter(id => !requiredIds.includes(id))];
    onConfirm(finalIds);
  };

  const hasTree = frameworkTree && frameworkTree.length > 0;

  return (
    <div className="w-full">
      <div className="px-1 mb-2">
        <h3 className="text-xs font-semibold text-primary uppercase tracking-wide">
          {title}
        </h3>
        {description && (
          <p className="text-sm text-muted-foreground mt-1">{description}</p>
        )}
      </div>

      <div className="bg-card rounded-xl overflow-hidden border shadow-sm">
        {hasTree ? (
          frameworkTree!.map((section, index) => {
            const sectionId = `section-${index}`;
            const isSelected = selectedIds.includes(sectionId);
            const isRequired = sections.find(s => s.id === sectionId)?.required === true;
            const isExpanded = expandedSections.has(section.name);
            const subSections = section.sub_sections || [];

            return (
              <div key={sectionId}>
                <button
                  type="button"
                  disabled={isRequired || disabled}
                  onClick={() => {
                    toggleSection(sectionId, isRequired);
                    if (subSections.length > 0) toggleExpand(section.name);
                  }}
                  className={cn(
                    'w-full text-left',
                    'flex items-center justify-between',
                    'px-4 py-3',
                    'transition-colors duration-150',
                    index < frameworkTree!.length - 1 && 'border-b',
                    isRequired
                      ? 'opacity-60 cursor-not-allowed'
                      : 'hover:bg-accent cursor-pointer active:bg-accent/80',
                    disabled && 'pointer-events-none'
                  )}
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    {subSections.length > 0 && (
                      <span className="text-muted-foreground shrink-0">
                        {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                      </span>
                    )}
                    <span className="text-sm font-medium text-foreground">{section.name}</span>
                    {isRequired && (
                      <span className="text-xs text-primary font-medium">Required</span>
                    )}
                  </div>
                  <div
                    className={cn(
                      'h-5 w-5 rounded-full flex items-center justify-center shrink-0 ml-2 transition-colors',
                      isSelected ? 'bg-primary text-primary-foreground' : 'bg-muted border'
                    )}
                  >
                    {isSelected && <Check className="h-3 w-3" />}
                  </div>
                </button>

                {isExpanded && subSections.length > 0 && (
                  <div className="bg-muted/30">
                    {subSections.map((sub, subIdx) => {
                      const points = sub.points || [];
                      return (
                        <div
                          key={`${sectionId}-sub-${subIdx}`}
                          className="pl-10 pr-4 py-2 border-b border-border/50 last:border-b-0"
                        >
                          <p className="text-sm text-foreground/80 font-medium">{sub.name}</p>
                          {points.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 mt-1">
                              {points.map((pt, ptIdx) => (
                                <span
                                  key={`${sectionId}-sub-${subIdx}-pt-${ptIdx}`}
                                  className="text-xs bg-muted text-muted-foreground px-2 py-0.5 rounded-full"
                                >
                                  {pt}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })
        ) : (
          sections.map((section, index) => {
            const isRequired = section.required === true;
            const isSelected = selectedIds.includes(section.id);
            const isLast = index === sections.length - 1;

            return (
              <button
                key={section.id}
                type="button"
                disabled={isRequired || disabled}
                onClick={() => toggleSection(section.id, isRequired)}
                className={cn(
                  'w-full text-left',
                  'flex items-center justify-between',
                  'px-4 py-3',
                  'transition-colors duration-150',
                  !isLast && 'border-b',
                  isRequired
                    ? 'opacity-60 cursor-not-allowed'
                    : 'hover:bg-accent cursor-pointer active:bg-accent/80',
                  disabled && 'pointer-events-none'
                )}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-foreground">
                      {section.label}
                    </span>
                    {isRequired && (
                      <span className="text-xs text-primary font-medium">Required</span>
                    )}
                  </div>
                  {section.description && (
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                      {section.description}
                    </p>
                  )}
                </div>
                <div
                  className={cn(
                    'h-5 w-5 rounded-full flex items-center justify-center shrink-0 ml-2 transition-colors',
                    isSelected ? 'bg-primary text-primary-foreground' : 'bg-muted border'
                  )}
                >
                  {isSelected && <Check className="h-3 w-3" />}
                </div>
              </button>
            );
          })
        )}
      </div>

      <div className="mt-4 flex items-center justify-between px-1">
        <p className="text-xs text-muted-foreground">
          Selected {selectedIds.length} / {sections.length} sections
        </p>
        <button
          type="button"
          onClick={handleConfirm}
          disabled={disabled || selectedIds.length === 0}
          className={cn(
            'px-4 py-2 rounded-lg text-sm font-medium',
            'transition-all duration-150',
            selectedIds.length > 0 && !disabled
              ? 'bg-primary text-primary-foreground hover:bg-primary/90'
              : 'bg-muted text-muted-foreground cursor-not-allowed'
          )}
        >
          Confirm Selection
        </button>
      </div>
    </div>
  );
}
