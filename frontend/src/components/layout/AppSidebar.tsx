import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Receipt, 
  BarChart3, 
  TrendingUp, 
  GitCompare, 
  Clock, 
  PieChart,
  ChevronRight
} from 'lucide-react';

const navigationItems = [
  { name: 'Dashboard Utama', path: '/dashboard', icon: LayoutDashboard },
  { name: 'Rekap Tagihan Billing', path: '/rekap-tagihan-billing', icon: Receipt },
  { name: 'Rangkuman Performa', path: '/rangkuman', icon: BarChart3 },
  { name: 'Laporan Performa', path: '/laporan-performa', icon: TrendingUp },
  { name: 'Performa Comparison', path: '/performa-comparison', icon: GitCompare },
  { name: 'Laporan Jam Ramai', path: '/laporan-jam-ramai', icon: Clock },
  { name: 'Order Sukses vs Batal', path: '/order-sukses-vs-batal', icon: PieChart },
];

export const AppSidebar: React.FC = () => {
  return (
    <aside className="w-64 bg-white border-r border-[#E3E3E8] h-screen sticky top-0 flex flex-col justify-between select-none">
      {/* Brand Header */}
      <div>
        <div className="h-16 px-6 flex items-center border-b border-[#EBEBEF]">
          <span className="text-base font-bold text-[#1A1A1F] tracking-tight">Elevate</span>
        </div>

        {/* Navigation Menu */}
        <div className="p-3 space-y-1">
          <div className="px-3 py-2 text-[11px] font-semibold text-[#9C9CA6] uppercase tracking-wider">
            Menu Utama
          </div>

          <nav className="space-y-0.5">
            {navigationItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    `flex items-center justify-between px-3 py-2.5 rounded-md text-xs font-semibold transition-all duration-150 ${
                      isActive
                        ? 'bg-[#EBF3FF] text-[#635BFF]'
                        : 'text-[#6B6B76] hover:bg-[#F5F5F7] hover:text-[#1A1A1F]'
                    }`
                  }
                >
                  <div className="flex items-center gap-3">
                    <Icon className="w-4 h-4 stroke-[2]" />
                    <span>{item.name}</span>
                  </div>
                  <ChevronRight className="w-3.5 h-3.5 opacity-40" />
                </NavLink>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Footer Info */}
      <div className="p-4 border-t border-[#E3E3E8] bg-[#FAFAFA]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-[#14804A] animate-pulse"></div>
            <span className="text-xs text-[#6B6B76] font-medium">PostgreSQL Connected</span>
          </div>
          <span className="text-[11px] text-[#9C9CA6] font-mono">v1.0</span>
        </div>
      </div>
    </aside>
  );
};
