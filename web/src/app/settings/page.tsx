// app/settings/page.tsx

'use client';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { LLMConfigPanel, ThemePanel, GeneralPanel } from '@/components/settings';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Settings, Sparkles, Palette, Sliders } from 'lucide-react';

export default function SettingsPage() {
  return (
    <div className="flex flex-1 flex-col bg-gradient-to-b from-background to-muted/30 min-h-0">
      {/* Header */}
      <header className="sticky top-0 z-10 shrink-0 border-b bg-background/80 backdrop-blur-sm">
        <div className="mx-auto max-w-4xl px-6 py-4">
          <div className="flex items-center gap-4">
            <Link href="/">
              <Button variant="ghost" size="icon" className="h-9 w-9">
                <ArrowLeft className="h-4 w-4" />
              </Button>
            </Link>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Settings className="h-5 w-5" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-foreground">Settings</h1>
                <p className="text-sm text-muted-foreground">Configure Your Zensers</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Scrollable Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-6 py-8">
          <Tabs defaultValue="llm" className="space-y-6">
            <TabsList className="grid w-full grid-cols-3 h-auto p-1 bg-muted/50">
              <TabsTrigger 
                value="llm" 
                className="flex items-center gap-2 py-2.5 data-[state=active]:bg-background data-[state=active]:shadow-sm"
              >
                <Sparkles className="h-4 w-4" />
                <span>LLM Configuration</span>
              </TabsTrigger>
              <TabsTrigger 
                value="theme"
                className="flex items-center gap-2 py-2.5 data-[state=active]:bg-background data-[state=active]:shadow-sm"
              >
                <Palette className="h-4 w-4" />
                <span>Theme</span>
              </TabsTrigger>
              <TabsTrigger 
                value="general"
                className="flex items-center gap-2 py-2.5 data-[state=active]:bg-background data-[state=active]:shadow-sm"
              >
                <Sliders className="h-4 w-4" />
                <span>General</span>
              </TabsTrigger>
            </TabsList>

            <TabsContent value="llm" className="mt-0">
              <LLMConfigPanel />
            </TabsContent>

            <TabsContent value="theme" className="mt-0">
              <ThemePanel />
            </TabsContent>

            <TabsContent value="general" className="mt-0">
              <GeneralPanel />
            </TabsContent>
          </Tabs>
        </div>
      </main>
    </div>
  );
}
