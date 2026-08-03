import React from 'react';
import { AppSidebar } from './AppSidebar';
import { HeaderTopbar } from './HeaderTopbar';

interface DashboardLayoutProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({ title, subtitle, children }) => {
  return (
    <div className="flex min-h-screen bg-white">
      {/* 240px Fixed Left Sidebar */}
      <AppSidebar />

      {/* Main Workspace Area */}
      <div className="flex-1 flex flex-col min-w-0">
        <HeaderTopbar title={title} subtitle={subtitle} />

        <main className="p-8 flex-1 max-w-[1400px] w-full mx-auto space-y-6">
          {children}
        </main>
      </div>
    </div>
  );
};
