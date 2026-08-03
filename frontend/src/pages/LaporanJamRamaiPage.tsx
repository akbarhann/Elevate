import React, { useState, useEffect } from 'react';
import { DashboardLayout } from '../components/layout/DashboardLayout';
import { api } from '../services/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export const LaporanJamRamaiPage: React.FC = () => {
  const [outlets, setOutlets] = useState<string[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  const [selectedOutlet, setSelectedOutlet] = useState<string>('');
  const [selectedBrand, setSelectedBrand] = useState<string>('');
  const [startDate, setStartDate] = useState<string>('2026-04-01');
  const [endDate, setEndDate] = useState<string>('2026-06-30');
  
  const [hourlyData, setHourlyData] = useState<Array<{ jam_label: string; total_order: number }>>([]);
  const [matrixData, setMatrixData] = useState<Record<string, Record<number, number>>>({});

  useEffect(() => {
    loadFilters();
  }, []);

  useEffect(() => {
    loadData();
  }, [selectedOutlet, selectedBrand, startDate, endDate]);

  const loadFilters = async () => {
    try {
      const res = await api.getFilters();
      if (res.outlets) setOutlets(res.outlets);
      if (res.brands) setBrands(res.brands);
    } catch (err) {
      console.error('Error loading filters:', err);
    }
  };

  const loadData = async () => {
    try {
      const params = { outlet: selectedOutlet, brand: selectedBrand, start_date: startDate, end_date: endDate };
      const resSum = await api.getJamRamaiSummary(params);
      const resMat = await api.getJamRamaiMatrix(params);

      if (resSum.status === 'success') {
        const clean = (resSum.data || []).filter(
          (r: any) => r.jam_label !== 'Grand Total' && r.jam !== 99
        );
        setHourlyData(clean);
      }
      if (resMat.status === 'success') setMatrixData(resMat.matrix || {});
    } catch (err) {
      console.error('Error loading jam ramai data:', err);
    }
  };

  const days = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu'];
  
  let maxHeatVal = 1;
  days.forEach(d => {
    for (let h = 0; h < 24; h++) {
      const val = (matrixData[d] && matrixData[d][h]) || 0;
      if (val > maxHeatVal) maxHeatVal = val;
    }
  });

  const getHeatClass = (val: number) => {
    if (!val || val === 0) return 'bg-white text-[#9C9CA6]';
    const ratio = val / maxHeatVal;
    if (ratio > 0.75) return 'bg-[#635BFF] text-white font-bold';
    if (ratio > 0.50) return 'bg-[#635BFF]/75 text-white font-semibold';
    if (ratio > 0.25) return 'bg-[#635BFF]/35 text-[#1A1A1F] font-medium';
    return 'bg-[#EBF3FF] text-[#635BFF]';
  };

  return (
    <DashboardLayout
      title="Laporan Jam Ramai"
      subtitle="Analisis jam sibuk/ramai (00:00 - 23:00) dan Matriks Intensitas Order 24 Jam x 7 Hari"
    >
      {/* Filter Controls */}
      <div className="bg-white rounded-lg p-5">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase mb-1">Filter Outlet</label>
            <select value={selectedOutlet} onChange={(e) => setSelectedOutlet(e.target.value)} className="w-full bg-[#FAFAFA] border border-[#E3E3E8] rounded-md px-3 py-2 text-xs text-[#1A1A1F]">
              <option value="">Semua Outlet</option>
              {outlets.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase mb-1">Filter Brand</label>
            <select value={selectedBrand} onChange={(e) => setSelectedBrand(e.target.value)} className="w-full bg-[#FAFAFA] border border-[#E3E3E8] rounded-md px-3 py-2 text-xs text-[#1A1A1F]">
              <option value="">Semua Brand</option>
              {brands.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase mb-1">Dari</label>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-full bg-[#FAFAFA] border border-[#E3E3E8] rounded-md px-3 py-2 text-xs text-[#1A1A1F]" />
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase mb-1">Hingga</label>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-full bg-[#FAFAFA] border border-[#E3E3E8] rounded-md px-3 py-2 text-xs text-[#1A1A1F]" />
          </div>
        </div>
      </div>

      {/* Hourly Bar Chart */}
      <div className="bg-white rounded-lg p-6 space-y-4">
        <h2 className="text-sm font-bold text-[#1A1A1F]">Distribusi Order per Jam (00:00 - 23:00)</h2>
        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={hourlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E3E3E8" />
              <XAxis dataKey="jam_label" stroke="#6B6B76" fontSize={11} />
              <YAxis stroke="#6B6B76" fontSize={11} tickFormatter={(val) => val.toLocaleString('id-ID')} />
              <Tooltip formatter={(value: any) => `${Number(value).toLocaleString('id-ID')} Order`} />
              <Bar dataKey="total_order" fill="#635BFF" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 24x7 Matrix Heatmap Table */}
      <div className="bg-white rounded-lg p-6 space-y-4">
        <h2 className="text-sm font-bold text-[#1A1A1F]">Matriks Intensitas Order (24 Jam x 7 Hari)</h2>
        
        <div className="overflow-x-auto border border-[#E3E3E8] rounded-md">
          <table className="w-full text-center text-xs border-collapse tabular-nums">
            <thead>
              <tr className="bg-[#F5F5F7] text-[#6B6B76] font-semibold border-b border-[#E3E3E8]">
                <th className="p-2.5 text-left bg-[#F5F5F7]">Hari / Jam</th>
                {Array.from({ length: 24 }).map((_, h) => (
                  <th key={h} className="p-2 min-w-[36px]">{String(h).padStart(2, '0')}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E3E3E8]">
              {days.map(d => (
                <tr key={d}>
                  <td className="p-2.5 text-left font-semibold text-[#1A1A1F] bg-[#F5F5F7]">{d}</td>
                  {Array.from({ length: 24 }).map((_, h) => {
                    const val = (matrixData[d] && matrixData[d][h]) || 0;
                    return (
                      <td key={h} className={`p-2 ${getHeatClass(val)} border-r border-[#E3E3E8] last:border-r-0`} title={`${d} Jam ${h}:00 - ${val.toLocaleString('id-ID')} Order`}>
                        {val > 0 ? val : '-'}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </DashboardLayout>
  );
};
