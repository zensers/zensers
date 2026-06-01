// app/layout.tsx

import type { Metadata } from 'next';
import { ErrorBoundary } from '@/components/ui/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { DesktopModeWrapper } from '@/components/layout/DesktopModeWrapper';
import { UpdateBanner } from '@/components/layout/UpdateBanner';
import { ThemeProvider } from '@/components/layout/ThemeProvider';
import './globals.css';

export const metadata: Metadata = {
  title: 'Zensers - AI Market Research Assistant',
  description: 'AI-powered Market Research Report Generator',
  icons: {
    icon: '/logo.png',
    apple: '/logo.png',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="h-screen flex flex-col antialiased">
        <ErrorBoundary>
          <ThemeProvider>
            <DesktopModeWrapper>
              <UpdateBanner />
              {children}
            </DesktopModeWrapper>
          </ThemeProvider>
        </ErrorBoundary>
        <Toaster />
      </body>
    </html>
  );
}
