// app/surveys/new/page.tsx
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Save, Loader2 } from 'lucide-react';
import Link from 'next/link';

const DEFAULT_JSON = JSON.stringify([
  { "text": "How satisfied are you with our product?", "type": "single_choice", "options": ["Very satisfied", "Satisfied", "Neutral", "Dissatisfied", "Very dissatisfied"] },
  { "text": "Would you recommend us to others?", "type": "yes_no" },
  { "text": "What improvements would you suggest?", "type": "open_ended" }
], null, 2);

export default function NewSurveyPage() {
  const router = useRouter();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [json, setJson] = useState(DEFAULT_JSON);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const handleCreate = async () => {
    setError('');
    if (!title.trim()) { setError('Title is required'); return; }
    let questions: any[];
    try {
      questions = JSON.parse(json);
      if (!Array.isArray(questions)) throw new Error('Must be an array');
    } catch (e: any) {
      setError(`Invalid JSON: ${e.message}`); return;
    }
    setSaving(true);
    try {
      const res = await api.createSurvey({ title, description, questions });
      router.push(`/surveys/${res.survey_id}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Failed to create survey');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <header className="flex h-[52px] items-center justify-between border-b px-4 shrink-0">
        <div className="flex items-center gap-2">
          <Link href="/surveys"><Button variant="ghost" size="icon" className="h-8 w-8"><ArrowLeft className="h-4 w-4" /></Button></Link>
          <h1 className="font-semibold text-sm">New Survey</h1>
        </div>
        <Button onClick={handleCreate} disabled={saving} size="sm" className="h-8 gap-1.5">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {saving ? 'Saving...' : 'Create'}
        </Button>
      </header>

      <div className="flex-1 overflow-auto p-4 max-w-3xl">
        <div className="space-y-4">
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Title *</label>
            <input
              className="w-full border rounded-lg px-3 py-2 text-sm bg-background"
              placeholder="e.g. Customer Satisfaction Survey"
              value={title} onChange={e => setTitle(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Description</label>
            <input
              className="w-full border rounded-lg px-3 py-2 text-sm bg-background"
              placeholder="Optional description"
              value={description} onChange={e => setDescription(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Questions (JSON)</label>
            <textarea
              className="w-full border rounded-lg px-3 py-2 text-sm font-mono bg-background min-h-[300px]"
              value={json} onChange={e => setJson(e.target.value)}
            />
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
        </div>
      </div>
    </div>
  );
}
