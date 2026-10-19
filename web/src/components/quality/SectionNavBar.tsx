'use client';

import { useState, useCallback } from 'react';
import { cn } from '@/lib/utils';

export interface SectionNavItem {
  id: string;
  title: string;
  hasWarning?: boolean;
}

interface SectionNavBarProps {
  sections: SectionNavItem[];
  activeSectionId?: string;
  onSectionClick?: (sectionId: string) => void;
  className?: string;
}

export function SectionNavBar({
  sections,
  activeSectionId,
  onSectionClick,
  className,
}: SectionNavBarProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const handleClick = useCallback(
    (id: string) => {
      onSectionClick?.(id);
    },
    [onSectionClick],
  );

  if (!sections.length) return null;

  return (
    <div className={cn('flex items-center gap-1 overflow-x-auto px-2 py-1.5 border-b bg-muted/30', className)}>
      <span className="text-[11px] text-muted-foreground shrink-0 mr-1">章节</span>
      {sections.map((sec) => (
        <button
          key={sec.id}
          onClick={() => handleClick(sec.id)}
          onMouseEnter={() => setHoveredId(sec.id)}
          onMouseLeave={() => setHoveredId(null)}
          className={cn(
            'shrink-0 px-2.5 py-1 rounded-md text-xs transition-colors whitespace-nowrap',
            activeSectionId === sec.id
              ? 'bg-primary text-primary-foreground font-medium'
              : sec.hasWarning
                ? 'bg-destructive/10 text-destructive hover:bg-destructive/20'
                : 'bg-muted text-muted-foreground hover:bg-muted/80',
            hoveredId === sec.id && activeSectionId !== sec.id && 'bg-accent text-accent-foreground',
          )}
        >
          {sec.hasWarning && (
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-destructive mr-1.5 align-middle" />
          )}
          {sec.title}
        </button>
      ))}
    </div>
  );
}
