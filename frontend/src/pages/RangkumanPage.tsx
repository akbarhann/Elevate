import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DashboardLayout } from '../components/layout/DashboardLayout';
import { api, type RangkumanChannelRow, type MonthlyBreakdownRow } from '../services/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export const RangkumanPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const paramStart = searchParams.get('start_date');
  const paramEnd = searchParams.get('end_date');

  const [outlets, setOutlets] = useState<string[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  const [selectedOutlet, setSelectedOutlet] = useState<string>('');
  const [selectedBrand, setSelectedBrand] = useState<string>('');
  const [startDate, setStartDate] = useState<string>(paramStart || '2026-04-01');
  const [endDate, setEndDate] = useState<string>(paramEnd || '2026-06-30');
  
  const [summaryData, setSummaryData] = useState<RangkumanChannelRow[]>([]);
  const [monthlyData, setMonthlyData] = useState<MonthlyBreakdownRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const formatIDR = (val: number) => `Rp ${Math.round(Number(val || 0)).toLocaleString('id-ID')}`;

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
      const resSum = await api.getRangkumanSummary(params);
      const resMon = await api.getRangkumanMonthly(params);

      if (resSum.status === 'success') setSummaryData(resSum.data || []);
      if (resMon.status === 'success') setMonthlyData(resMon.data || []);
    } catch (err) {
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
    }
  };

  const grandTotal = summaryData.find(r => r.channel === 'Grand Total') || {
    pendapatan_kotor: 0, potongan_ojol: 0, pendapatan_bersih: 0, order_sukses: 0
  };

  // Recharts Monthly Grouping
  const getBulanKey = (r: any) => r.bulan || r.bulan_tahun || '';
  const bulanList = Array.from(new Set(monthlyData.map(getBulanKey))).filter(b => b && b !== 'Grand Total');
  const chartDataKotor = bulanList.map(b => ({
    bulan: b,
    GoFood: monthlyData.find(r => getBulanKey(r) === b && r.channel === 'GoFood')?.pendapatan_kotor || 0,
    GrabFood: monthlyData.find(r => getBulanKey(r) === b && r.channel === 'GrabFood')?.pendapatan_kotor || 0,
    ShopeeFood: monthlyData.find(r => getBulanKey(r) === b && r.channel === 'ShopeeFood')?.pendapatan_kotor || 0,
  }));

  return (
    <DashboardLayout
      title="Rangkuman Performa Ojol"
      subtitle="Rangkuman eksekutif performa platform GoFood, GrabFood, ShopeeFood"
    >
      {/* Hero Big Number KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg p-4">
          <div className="text-xs font-semibold text-[#6B6B76] uppercase">Pendapatan Kotor</div>
          {loading ? <div className="h-6 w-3/4 bg-[#E3E3E8] animate-pulse rounded mt-1" /> : (
            <div className="text-xl font-bold text-[#1A1A1F] tabular-nums mt-1">{formatIDR(grandTotal.pendapatan_kotor)}</div>
          )}
        </div>
        <div className="bg-white rounded-lg p-4">
          <div className="text-xs font-semibold text-[#6B6B76] uppercase">Potongan Ojol</div>
          {loading ? <div className="h-6 w-3/4 bg-[#E3E3E8] animate-pulse rounded mt-1" /> : (
            <div className="text-xl font-bold text-[#DF1B41] tabular-nums mt-1">{formatIDR(grandTotal.potongan_ojol)}</div>
          )}
        </div>
        <div className="bg-white rounded-lg p-4">
          <div className="text-xs font-semibold text-[#6B6B76] uppercase">Pendapatan Bersih</div>
          {loading ? <div className="h-6 w-3/4 bg-[#E3E3E8] animate-pulse rounded mt-1" /> : (
            <div className="text-xl font-bold text-[#14804A] tabular-nums mt-1">{formatIDR(grandTotal.pendapatan_bersih)}</div>
          )}
        </div>
        <div className="bg-white rounded-lg p-4">
          <div className="text-xs font-semibold text-[#6B6B76] uppercase">Total Order Sukses</div>
          {loading ? <div className="h-6 w-3/4 bg-[#E3E3E8] animate-pulse rounded mt-1" /> : (
            <div className="text-xl font-bold text-[#635BFF] tabular-nums mt-1">{Number(grandTotal.order_sukses).toLocaleString('id-ID')} Order</div>
          )}
        </div>
      </div>

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
            <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase mb-1">Dari Tanggal</label>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-full bg-[#FAFAFA] border border-[#E3E3E8] rounded-md px-3 py-2 text-xs text-[#1A1A1F]" />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase mb-1">Hingga Tanggal</label>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-full bg-[#FAFAFA] border border-[#E3E3E8] rounded-md px-3 py-2 text-xs text-[#1A1A1F]" />
          </div>
        </div>
      </div>

      {/* Summary Table */}
      <div className="bg-white rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-[#E3E3E8] bg-[#F5F5F7]">
          <h2 className="text-sm font-bold text-[#1A1A1F]">Performa per Channel Ojol</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#F5F5F7] text-[#6B6B76] uppercase text-[11px] font-semibold border-b border-[#E3E3E8]">
                <th className="p-3">CHANNEL</th>
                <th className="p-3 text-right">PENDAPATAN KOTOR</th>
                <th className="p-3 text-right">POTONGAN OJOL</th>
                <th className="p-3 text-right">PENDAPATAN BERSIH</th>
                <th className="p-3 text-right">RATA-RATA ORDER</th>
                <th className="p-3 text-right">TOTAL ORDER</th>
                <th className="p-3 text-right">ORDER SUKSES</th>
                <th className="p-3 text-right">ORDER BATAL</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E3E3E8]">
              {loading ? (
                <tr>
                  <td colSpan={8} className="p-6 text-center text-[#6B6B76] animate-pulse">
                    Memuat data rangkuman channel...
                  </td>
                </tr>
              ) : summaryData.map((r, i) => (
                <tr key={i} className={r.channel === 'Grand Total' ? 'bg-[#EBF3FF] font-bold border-t-2 border-[#635BFF]' : 'hover:bg-[#F5F5F7]'}>
                  <td className="p-3 font-semibold">{r.channel}</td>
                  <td className="p-3 text-right tabular-nums">{formatIDR(r.pendapatan_kotor)}</td>
                  <td className="p-3 text-right tabular-nums">{formatIDR(r.potongan_ojol)}</td>
                  <td className="p-3 text-right tabular-nums">{formatIDR(r.pendapatan_bersih)}</td>
                  <td className="p-3 text-right tabular-nums">{formatIDR(r.rata_rata_order_per_customer)}</td>
                  <td className="p-3 text-right tabular-nums">{Number(r.total_order).toLocaleString('id-ID')}</td>
                  <td className="p-3 text-right tabular-nums">{Number(r.order_sukses).toLocaleString('id-ID')}</td>
                  <td className="p-3 text-right tabular-nums">{Number(r.order_batal).toLocaleString('id-ID')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recharts Bar Chart */}
      <div className="bg-white rounded-lg p-6 space-y-4">
        <h2 className="text-sm font-bold text-[#1A1A1F]">Bar Chart: Pendapatan Kotor per Channel</h2>
        <div className="h-80 w-full">
          {loading ? (
            <div className="h-full w-full bg-[#E3E3E8]/40 animate-pulse rounded-lg" />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartDataKotor} barCategoryGap="20%">
                <CartesianGrid strokeDasharray="3 3" stroke="#E3E3E8" />
                <XAxis dataKey="bulan" stroke="#6B6B76" fontSize={11} />
                <YAxis stroke="#6B6B76" fontSize={11} tickFormatter={(val) => `Rp ${(val/1e6).toFixed(0)}Jt`} />
                <Tooltip formatter={(value: any) => formatIDR(Number(value))} />
                <Legend />
                <Bar dataKey="GoFood" fill="#14804A" maxBarSize={32} radius={[4, 4, 0, 0]} />
                <Bar dataKey="GrabFood" fill="#0055CC" maxBarSize={32} radius={[4, 4, 0, 0]} />
                <Bar dataKey="ShopeeFood" fill="#F97316" maxBarSize={32} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
};
