import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { DashboardPage } from './pages/DashboardPage';
import { RekapBillingPage } from './pages/RekapBillingPage';
import { RangkumanPage } from './pages/RangkumanPage';
import { LaporanPerformaPage } from './pages/LaporanPerformaPage';
import { PerformaComparisonPage } from './pages/PerformaComparisonPage';
import { LaporanJamRamaiPage } from './pages/LaporanJamRamaiPage';
import { OrderStatusPage } from './pages/OrderStatusPage';

export const App: React.FC = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/rekap-tagihan-billing" element={<RekapBillingPage />} />
        <Route path="/rangkuman" element={<RangkumanPage />} />
        <Route path="/laporan-performa" element={<LaporanPerformaPage />} />
        <Route path="/performa-comparison" element={<PerformaComparisonPage />} />
        <Route path="/laporan-jam-ramai" element={<LaporanJamRamaiPage />} />
        <Route path="/order-sukses-vs-batal" element={<OrderStatusPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Router>
  );
};

export default App;
