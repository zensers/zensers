// components/settings/ThemePanel.tsx

'use client';

import { useSettingsStore } from '@/store/useSettingsStore';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

const FONT_SIZES = [
  { id: 'small', name: 'Small', value: '14px' },
  { id: 'medium', name: 'Medium', value: '16px' },
  { id: 'large', name: 'Large', value: '18px' },
];

const FONT_FAMILIES = [
  { id: 'Inter', name: 'Inter' },
  { id: 'system-ui', name: 'System Default' },
  { id: 'serif', name: 'Serif' },
  { id: 'monospace', name: 'Monospace' },
];

const PRIMARY_COLORS = [
  { id: '#3b82f6', name: 'Blue' },
  { id: '#10b981', name: 'Green' },
  { id: '#8b5cf6', name: 'Purple' },
  { id: '#f59e0b', name: 'Orange' },
  { id: '#ef4444', name: 'Red' },
  { id: '#06b6d4', name: 'Cyan' },
  { id: '#ec4899', name: 'Pink' },
];

/**
 * Theme settings panel
 */
export function ThemePanel() {
  const { theme, updateThemeConfig } = useSettingsStore();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Theme Settings</CardTitle>
        <CardDescription>Customize app appearance</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* 主题模式 */}
        <div className="space-y-2">
          <Label>Theme Mode</Label>
          <div className="flex gap-2">
            <Button
              variant={theme.mode === 'light' ? 'default' : 'outline'}
              size="sm"
              onClick={() => updateThemeConfig({ mode: 'light' })}
            >
              <svg className="mr-1 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
               Light
            </Button>
            <Button
              variant={theme.mode === 'dark' ? 'default' : 'outline'}
              size="sm"
              onClick={() => updateThemeConfig({ mode: 'dark' })}
            >
              <svg className="mr-1 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
              Dark
            </Button>
            <Button
              variant={theme.mode === 'system' ? 'default' : 'outline'}
              size="sm"
              onClick={() => updateThemeConfig({ mode: 'system' })}
            >
              <svg className="mr-1 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              System
            </Button>
          </div>
        </div>

        {/* 主题色 */}
        <div className="space-y-2">
          <Label>Theme Color</Label>
          <div className="flex flex-wrap gap-2">
            {PRIMARY_COLORS.map((color) => (
              <button
                key={color.id}
                onClick={() => updateThemeConfig({ primaryColor: color.id })}
                className={`h-8 w-8 rounded-full border-2 transition-transform hover:scale-110 ${
                  theme.primaryColor === color.id ? 'border-foreground scale-110' : 'border-transparent'
                }`}
                style={{ backgroundColor: color.id }}
                title={color.name}
              />
            ))}
          </div>
        </div>

        {/* 字体大小 */}
        <div className="space-y-2">
          <Label htmlFor="fontSize">Font Size</Label>
          <Select
            value={theme.fontSize}
            onValueChange={(v) => updateThemeConfig({ fontSize: v as any })}
          >
            <SelectTrigger id="fontSize">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FONT_SIZES.map((size) => (
                <SelectItem key={size.id} value={size.id}>
                  {size.name} ({size.value})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* 字体 */}
        <div className="space-y-2">
          <Label htmlFor="fontFamily">Font</Label>
          <Select
            value={theme.fontFamily}
            onValueChange={(v) => updateThemeConfig({ fontFamily: v })}
          >
            <SelectTrigger id="fontFamily">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FONT_FAMILIES.map((font) => (
                <SelectItem key={font.id} value={font.id}>
                  <span style={{ fontFamily: font.id }}>{font.name}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardContent>
    </Card>
  );
}
