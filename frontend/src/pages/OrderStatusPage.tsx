import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DashboardLayout } from '../components/layout/DashboardLayout';
import { api, type OrderStatusRow } from '../services/api';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export const OrderStatusPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const paramStart = searchParams.get('start_date');
  const paramEnd = searchParams.get('end_date');

  const [outlets, setOutlets] = useState<string[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  const [selectedOutlet, setSelectedOutlet] = useState<string>('');
  const [selectedBrand, setSelectedBrand] = useState<string>('');
  const [startDate, setStartDate] = useState<string>(paramStart || '2026-04-01');
  const [endDate, setEndDate] = useState<string>(paramEnd || '2026-06-30');
  
  const [data, setData] = useState<OrderStatusRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

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
    setLoading(true);
    try {
      const params = { outlet: selectedOutlet, brand: selectedBrand, start_date: startDate, end_date: endDate };
      const res = await api.getOrderStatusSummary(params);
      if (res.status === 'success') setData(res.data || []);
    } catch (err) {
      console.error('Error loading order status:', err);
    } finally {
      setLoading(false);
    }
  };

  const COLORS = ['#14804A', '#DF1B41'];

  const getDonutData = (channelName: string) => {
    const row = data.find(r => r.channel === channelName) || { order_sukses: 0, order_batal: 0 };
    return [
      { name: 'Order Sukses', value: Number(row.order_sukses) },
      { name: 'Order Batal', value: Number(row.order_batal) }
    ];
  };

  return (
    <DashboardLayout
      title="Order Sukses vs Order Batal"
      subtitle="Visualisasi rasio persentase order sukses vs batal per channel (All OFD, GrabFood, ShopeeFood)"
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

      {/* 3 Donut Charts Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-white rounded-lg p-5 h-72 animate-pulse bg-[#E3E3E8]/40" />
          <div className="bg-white rounded-lg p-5 h-72 animate-pulse bg-[#E3E3E8]/40" />
          <div className="bg-white rounded-lg p-5 h-72 animate-pulse bg-[#E3E3E8]/40" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* All OFD */}
          <div className="bg-white rounded-lg p-5 space-y-3">
            <h2 className="text-sm font-bold text-[#1A1A1F] text-center">Gabungan All OFD</h2>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={getDonutData('Grand Total')} innerRadius={60} outerRadius={85} paddingAngle={2} dataKey="value">
                    {getDonutData('Grand Total').map((_, index) => <Cell key={index} fill={COLORS[index]} />)}
                  </Pie>
                  <Tooltip formatter={(val: any) => `${Number(val).toLocaleString('id-ID')} Order`} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

        {/* GrabFood */}
        <div className="bg-white rounded-lg p-5 space-y-3">
          <h2 className="text-sm font-bold text-[#1A1A1F] text-center">GrabFood</h2>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={getDonutData('GrabFood')} innerRadius={60} outerRadius={85} paddingAngle={2} dataKey="value">
                  {getDonutData('GrabFood').map((_, index) => <Cell key={index} fill={COLORS[index]} />)}
                </Pie>
                <Tooltip formatter={(val: any) => `${Number(val).toLocaleString('id-ID')} Order`} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* ShopeeFood */}
        <div className="bg-white rounded-lg p-5 space-y-3">
          <h2 className="text-sm font-bold text-[#1A1A1F] text-center">ShopeeFood</h2>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={getDonutData('ShopeeFood')} innerRadius={60} outerRadius={85} paddingAngle={2} dataKey="value">
                  {getDonutData('ShopeeFood').map((_, index) => <Cell key={index} fill={COLORS[index]} />)}
                </Pie>
                <Tooltip formatter={(val: any) => `${Number(val).toLocaleString('id-ID')} Order`} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    )}

      {/* Summary Table */}
      <div className="bg-white rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-[#E3E3E8] bg-[#F5F5F7]">
          <h2 className="text-sm font-bold text-[#1A1A1F]">Rincian Status Order per Channel</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#F5F5F7] text-[#6B6B76] uppercase text-[11px] font-semibold border-b border-[#E3E3E8]">
                <th className="p-3">CHANNEL</th>
                <th className="p-3 text-right">TOTAL ORDER</th>
                <th className="p-3 text-right">ORDER SUKSES</th>
                <th className="p-3 text-right">ORDER BATAL</th>
                <th className="p-3 text-right">% ORDER SUKSES</th>
                <th className="p-3 text-right">% ORDER BATAL</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E3E3E8]">
              {data.map((r, i) => (
                <tr key={i} className={r.channel === 'Grand Total' ? 'bg-[#EBF3FF] font-bold border-t-2 border-[#635BFF]' : 'hover:bg-[#F5F5F7]'}>
                  <td className="p-3 font-semibold">{r.channel}</td>
                  <td className="p-3 text-right tabular-nums">{Number(r.total_order).toLocaleString('id-ID')}</td>
                  <td className="p-3 text-right tabular-nums">{Number(r.order_sukses).toLocaleString('id-ID')}</td>
                  <td className="p-3 text-right tabular-nums">{Number(r.order_batal).toLocaleString('id-ID')}</td>
                  <td className="p-3 text-right tabular-nums">
                    <span className="inline-block px-2 py-0.5 rounded bg-[#EAF7ED] text-[#14804A] font-semibold">{r.pct_sukses}%</span>
                  </td>
                  <td className="p-3 text-right tabular-nums">
                    <span className="inline-block px-2 py-0.5 rounded bg-[#FDE8EC] text-[#DF1B41] font-semibold">{r.pct_batal}%</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </DashboardLayout>
  );
};
