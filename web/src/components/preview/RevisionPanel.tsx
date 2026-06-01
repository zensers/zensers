// components/preview/RevisionPanel.tsx

'use client';

import { useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Loader2, X, FileText } from 'lucide-react';
import { api, SectionInfo } from '@/lib/api';

interface RevisionPanelProps {
  taskId: string;
  isOpen: boolean;
  onClose: () => void;
  onRevisionComplete: () => void;
}

/**
 * Report revision panel
 * 
 * Allows users to select sections and enter revision notes to perform report revisions.
 */
export function RevisionPanel({
  taskId,
  isOpen,
  onClose,
  onRevisionComplete,
}: RevisionPanelProps) {
  const [sections, setSections] = useState<SectionInfo[]>([]);
  const [selectedSections, setSelectedSections] = useState<string[]>([]);
  const [adjustment, setAdjustment] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isFetching, setIsFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch section list
  useEffect(() => {
    if (isOpen && taskId) {
      fetchSections();
    }
  }, [isOpen, taskId]);

  const fetchSections = async () => {
    setIsFetching(true);
    setError(null);
    try {
      const result = await api.getSections(taskId);
      setSections(result.sections || []);
      setSelectedSections([]);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch section list');
    } finally {
      setIsFetching(false);
    }
  };

  const toggleSection = (sectionId: string) => {
    setSelectedSections((prev) =>
      prev.includes(sectionId)
        ? prev.filter((id) => id !== sectionId)
        : [...prev, sectionId]
    );
  };

  const handleRevise = async () => {
    if (selectedSections.length === 0) {
      setError('Please select at least one section');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      // 将 section ID 转换为章节标题
      const selectedTitles = sections
        .filter((s) => selectedSections.includes(s.id))
        .map((s) => s.title);

      const result = await api.reviseSections(taskId, selectedTitles, adjustment || undefined);

      if (result.status === 'completed') {
        onRevisionComplete();
        onClose();
      } else {
        setError(result.message || 'Revision failed');
      }
    } catch (err: any) {
      setError(err.message || 'Revision failed, please try again later');
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-background w-full max-w-lg mx-4 rounded-xl shadow-xl border overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b bg-muted/30">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold">Revise Report Sections</h2>
          </div>
          <button
            onClick={onClose}
            className="h-8 w-8 rounded-full hover:bg-muted flex items-center justify-center transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4 max-h-[60vh] overflow-y-auto">
          {/* Section selection */}
          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">
              Select Sections
            </label>
            {isFetching ? (
              <div className="flex items-center justify-center py-8 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin mr-2" />
                Loading sections...
              </div>
            ) : sections.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No section data
              </div>
            ) : (
              <div className="bg-muted/30 rounded-lg border divide-y">
                {sections.map((section) => (
                  <div key={section.id} className="p-3">
                    <label className="flex items-center gap-3 cursor-pointer">
                      <Checkbox
                        checked={selectedSections.includes(section.id)}
                        onCheckedChange={() => toggleSection(section.id)}
                      />
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium">{section.title}</span>
                          <span className="text-xs text-muted-foreground">
                            ~{section.word_count} chars
                          </span>
                        </div>
                        {section.children && section.children.length > 0 && (
                          <div className="mt-2 ml-6 space-y-1">
                            {section.children.map((child) => (
                              <label
                                key={child.id}
                                className="flex items-center gap-2 cursor-pointer"
                              >
                                <Checkbox
                                  checked={selectedSections.includes(child.id)}
                                  onCheckedChange={() => toggleSection(child.id)}
                                />
                                <span className="text-xs text-muted-foreground">
                                  {child.title}
                                </span>
                              </label>
                            ))}
                          </div>
                        )}
                      </div>
                    </label>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Selected tags */}
          {selectedSections.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {selectedSections.map((id) => {
                const section = sections.find((s) => s.id === id);
                if (!section) return null;
                return (
                  <span
                    key={id}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-primary/10 text-primary text-xs rounded-full"
                  >
                    {section.title}
                    <button
                      onClick={() => toggleSection(id)}
                      className="hover:bg-primary/20 rounded-full p-0.5"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                );
              })}
            </div>
          )}

          {/* Revision notes */}
          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">
              Revision Notes (Optional)
            </label>
            <Textarea
              placeholder="Describe how you'd like to revise these sections, e.g., update with latest 2024 data, add tech trends..."
              value={adjustment}
              onChange={(e) => setAdjustment(e.target.value)}
              rows={3}
              className="resize-none"
            />
          </div>

          {/* Error message */}
          {error && (
            <div className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t bg-muted/30">
          <Button variant="outline" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button
            onClick={handleRevise}
            disabled={isLoading || selectedSections.length === 0 || isFetching}
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Revising...
              </>
            ) : (
              'Start Revision'
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
