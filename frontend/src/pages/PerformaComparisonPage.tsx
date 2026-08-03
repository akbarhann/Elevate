import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DashboardLayout } from '../components/layout/DashboardLayout';
import { api, type ComparisonChartRow } from '../services/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export const PerformaComparisonPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const paramStart = searchParams.get('start_date');
  const paramEnd = searchParams.get('end_date');

  const [outlets, setOutlets] = useState<string[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  const [selectedOutlet, setSelectedOutlet] = useState<string>('');
  const [selectedBrand, setSelectedBrand] = useState<string>('');
  const [selectedChannel, setSelectedChannel] = useState<string>('');
  const [startDate, setStartDate] = useState<string>(paramStart || '2026-04-01');
  const [endDate, setEndDate] = useState<string>(paramEnd || '2026-06-30');
  
  const [data, setData] = useState<ComparisonChartRow[]>([]);

  const formatIDR = (val: number) => `Rp ${Math.round(Number(val || 0)).toLocaleString('id-ID')}`;

  const formatYAxisCurrency = (val: number) => {
    if (val === 0) return 'Rp 0';
    if (Math.abs(val) >= 1e9) return `Rp ${(val / 1e9).toFixed(1)} M`;
    if (Math.abs(val) >= 1e6) return `Rp ${(val / 1e6).toFixed(0)} Jt`;
    return `Rp ${val.toLocaleString('id-ID')}`;
  };

  useEffect(() => {
    loadFilters();
  }, []);

  useEffect(() => {
    loadData();
  }, [selectedOutlet, selectedBrand, selectedChannel, startDate, endDate]);

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
      const params = {
        outlet: selectedOutlet,
        brand: selectedBrand,
        channel: selectedChannel,
        start_date: startDate,
        end_date: endDate
      };
      const res = await api.getComparisonCharts(params);
      if (res.status === 'success') setData(res.data || []);
    } catch (err) {
      console.error('Error loading comparison charts:', err);
    }
  };

  return (
    <DashboardLayout
      title="Performa Comparison"
      subtitle="Analisis komparatif Grouped Bar Chart untuk Keuangan dan Status Order"
    >
      {/* Filter Controls */}
      <div className="bg-white rounded-lg p-5">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
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
            <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase mb-1">Filter OFD</label>
            <select value={selectedChannel} onChange={(e) => setSelectedChannel(e.target.value)} className="w-full bg-[#FAFAFA] border border-[#E3E3E8] rounded-md px-3 py-2 text-xs text-[#1A1A1F]">
              <option value="">Semua Channel</option>
              <option value="GoFood">GoFood</option>
              <option value="GrabFood">GrabFood</option>
              <option value="ShopeeFood">ShopeeFood</option>
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

      {/* 1. Financial Comparison Chart */}
      <div className="bg-white rounded-lg p-6 space-y-4">
        <h2 className="text-sm font-bold text-[#1A1A1F]">Financial Comparison Chart</h2>
        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E3E3E8" />
              <XAxis dataKey="periode_label" stroke="#6B6B76" fontSize={11} />
              <YAxis stroke="#6B6B76" fontSize={11} tickFormatter={formatYAxisCurrency} />
              <Tooltip formatter={(value: any) => formatIDR(Number(value))} />
              <Legend />
              <Bar dataKey="pendapatan_kotor" name="Pendapatan Kotor" fill="#635BFF" radius={[4, 4, 0, 0]} />
              <Bar dataKey="potongan_ojol" name="Potongan Ojol" fill="#DF1B41" radius={[4, 4, 0, 0]} />
              <Bar dataKey="pendapatan_bersih" name="Pendapatan Bersih" fill="#14804A" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 2. Order Comparison Chart */}
      <div className="bg-white rounded-lg p-6 space-y-4">
        <h2 className="text-sm font-bold text-[#1A1A1F]">Order Comparison Chart</h2>
        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E3E3E8" />
              <XAxis dataKey="periode_label" stroke="#6B6B76" fontSize={11} />
              <YAxis stroke="#6B6B76" fontSize={11} tickFormatter={(val) => val.toLocaleString('id-ID')} />
              <Tooltip formatter={(value: any) => `${Number(value).toLocaleString('id-ID')} Order`} />
              <Legend />
              <Bar dataKey="total_order" name="Total Order" fill="#0055CC" radius={[4, 4, 0, 0]} />
              <Bar dataKey="order_sukses" name="Order Sukses" fill="#14804A" radius={[4, 4, 0, 0]} />
              <Bar dataKey="order_batal" name="Order Batal" fill="#DF1B41" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </DashboardLayout>
  );
};
