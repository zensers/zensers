// components/chat/DynamicParameterForm.tsx
// Dynamic parameter form — auto-renders controls based on backend DynamicParameter[]

'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import type { DynamicParameter } from '@/types/api';

interface DynamicParameterFormProps {
  parameters: DynamicParameter[];
  onSubmit: (params: Record<string, any>) => void;
  disabled?: boolean;
}

/**
 * Dynamic parameter form
 * 
 * Supports 4 parameter types:
 * - text: free text input
 * - select: single select dropdown
 * - multi_select: multi select
 * - date: date picker
 * 
 * Each type renders the corresponding shadcn/ui control.
 * Parameter definitions are dynamically provided by the backend SmartClarifier based on report type.
 */
export function DynamicParameterForm({
  parameters,
  onSubmit,
  disabled = false,
}: DynamicParameterFormProps) {
  // Initialize all parameter values
  const [values, setValues] = useState<Record<string, any>>(() => {
    const initial: Record<string, any> = {};
    for (const p of parameters) {
      if (p.type === 'multi_select') {
        initial[p.id] = Array.isArray(p.default) ? [...p.default] : [];
      } else {
        initial[p.id] = p.default ?? '';
      }
    }
    return initial;
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(values);
  };

  const updateValue = (id: string, value: any) => {
    setValues((prev) => ({ ...prev, [id]: value }));
  };

  if (!parameters || parameters.length === 0) {
    return (
      <Card className="w-full">
        <CardHeader>
          <CardTitle>Set Research Parameters</CardTitle>
          <CardDescription>No additional parameters needed for this report type</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex justify-end pt-4">
            <Button type="button" onClick={() => onSubmit({})} disabled={disabled}>
               Continue
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>Set Research Parameters</CardTitle>
        <CardDescription>Please configure the following research parameters</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
          {parameters.map((param) => (
            <div key={param.id} className="space-y-2">
              <Label htmlFor={param.id}>
                {param.label}
                {param.required && <span className="text-red-500 ml-1">*</span>}
              </Label>

              {param.type === 'text' && (
                <Input
                  id={param.id}
                  value={values[param.id] || ''}
                  onChange={(e) => updateValue(param.id, e.target.value)}
                  placeholder={param.placeholder}
                  disabled={disabled}
                />
              )}

              {param.type === 'select' && (
                <Select
                  value={values[param.id] || ''}
                  onValueChange={(v) => updateValue(param.id, v)}
                  disabled={disabled}
                >
                  <SelectTrigger id={param.id}>
                    <SelectValue placeholder="Please select" />
                  </SelectTrigger>
                  <SelectContent>
                    {param.options?.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}

              {param.type === 'multi_select' && (
                <div className="space-y-2">
                  {param.options?.map((opt) => {
                    const selected = (values[param.id] as string[] || []).includes(opt.value);
                    return (
                      <label
                        key={opt.value}
                        className="flex items-center gap-2 cursor-pointer py-1"
                      >
                        <Checkbox
                          checked={selected}
                          onCheckedChange={(checked) => {
                            const current = values[param.id] as string[] || [];
                            updateValue(
                              param.id,
                              checked
                                ? [...current, opt.value]
                                : current.filter((v: string) => v !== opt.value)
                            );
                          }}
                          disabled={disabled}
                        />
                        <span className="text-sm">{opt.label}</span>
                      </label>
                    );
                  })}
                </div>
              )}

              {param.type === 'date' && (
                <Input
                  id={param.id}
                  type="date"
                  value={values[param.id] || ''}
                  onChange={(e) => updateValue(param.id, e.target.value)}
                  disabled={disabled}
                />
              )}
            </div>
          ))}

          <div className="flex justify-end pt-4">
            <Button type="submit" disabled={disabled}>
               Confirm Parameters
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
