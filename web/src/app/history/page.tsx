// app/history/page.tsx

import { SessionList } from '@/components/history/SessionList';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { Plus, History } from 'lucide-react';

export default function HistoryPage() {
  return (
    <div className="flex flex-1 flex-col bg-gradient-to-b from-background to-muted/30 min-h-0">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur-sm">
        <div className="mx-auto max-w-4xl px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <History className="h-5 w-5" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-foreground">Research History</h1>
                <p className="text-sm text-muted-foreground">View and manage your research records</p>
              </div>
            </div>
            <Link href="/">
              <Button className="gap-2">
                <Plus className="h-4 w-4" />
                New Research
              </Button>
            </Link>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="mx-auto max-w-4xl px-6 flex-1 overflow-y-auto w-full min-h-0">
        <div className="pt-2 pb-8">
          <SessionList />
        </div>
      </main>
    </div>
  );
}
