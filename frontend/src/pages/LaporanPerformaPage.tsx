import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DashboardLayout } from '../components/layout/DashboardLayout';
import { api, type PerformaDataRow } from '../services/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export const LaporanPerformaPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const paramStart = searchParams.get('start_date');
  const paramEnd = searchParams.get('end_date');
  const paramTipe = searchParams.get('tipe_laporan');

  const [tipeLaporan, setTipeLaporan] = useState<'Bulanan' | 'Mingguan' | 'Harian'>(
    (paramTipe as any) || 'Bulanan'
  );
  const [owners, setOwners] = useState<string[]>([]);
  const [outlets, setOutlets] = useState<string[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  
  const [selectedOwner, setSelectedOwner] = useState<string>('');
  const [selectedOutlet, setSelectedOutlet] = useState<string>('');
  const [selectedBrand, setSelectedBrand] = useState<string>('');
  const [startDate, setStartDate] = useState<string>(paramStart || '2026-04-01');
  const [endDate, setEndDate] = useState<string>(paramEnd || '2026-06-30');
  
  const [data, setData] = useState<PerformaDataRow[]>([]);

  const formatIDR = (val: number) => `Rp ${Math.round(Number(val || 0)).toLocaleString('id-ID')}`;

  const formatYAxisCurrency = (val: number) => {
    if (val === 0) return 'Rp 0';
    if (Math.abs(val) >= 1e9) return `Rp ${(val / 1e9).toFixed(1)} M`;
    if (Math.abs(val) >= 1e6) return `Rp ${(val / 1e6).toFixed(0)} Jt`;
    return `Rp ${val.toLocaleString('id-ID')}`;
  };

  const [rankings, setRankings] = useState<any[]>([]);
  const [wowData, setWowData] = useState<any[]>([]);
  const [baselineData, setBaselineData] = useState<any[]>([]);

  useEffect(() => {
    loadFilters();
    loadAnalytics();
  }, []);

  const loadAnalytics = async () => {
    try {
      const [rankRes, wowRes, baseRes] = await Promise.all([
        api.getOrderRanking({ start_date: startDate, end_date: endDate, limit: '10' }),
        api.getWeekOverWeek(),
        api.getBaselineVsCurrent()
      ]);
      if (rankRes?.data) setRankings(rankRes.data);
      if (wowRes?.data) setWowData(wowRes.data);
      if (baseRes?.data) setBaselineData(baseRes.data);
    } catch (err) {
      console.error('Error loading matview analytics:', err);
    }
  };

  useEffect(() => {
    loadData();
  }, [tipeLaporan, selectedOwner, selectedOutlet, selectedBrand, startDate, endDate]);

  const loadFilters = async () => {
    try {
      const res = await api.getFilters();
      if (res.owners) setOwners(res.owners);
      if (res.outlets) setOutlets(res.outlets);
      if (res.brands) setBrands(res.brands);
    } catch (err) {
      console.error('Error loading filters:', err);
    }
  };

  const loadData = async () => {
    try {
      const params = {
        tipe_laporan: tipeLaporan,
        owner: selectedOwner,
        outlet: selectedOutlet,
        brand: selectedBrand,
        start_date: startDate,
        end_date: endDate
      };
      const res = await api.getLaporanPerforma(params);
      if (res.status === 'success') setData(res.data || []);
    } catch (err) {
      console.error('Error loading performa data:', err);
    }
  };

  const chartRows = data.filter(r => r.periode_label !== 'Grand Total');

  return (
    <DashboardLayout
      title="Laporan Performa & Analitik Growth"
      subtitle="Analisis tren keuangan, order ranking, perbandingan Week-over-Week (WoW), dan Baseline Growth"
    >
      {/* Filter Controls */}
      <div className="bg-white rounded-lg p-5">
        <div className="grid grid-cols-1 md:grid-cols-6 gap-4 items-end">
          <div>
            <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase mb-1">Tipe Laporan</label>
            <select value={tipeLaporan} onChange={(e: any) => setTipeLaporan(e.target.value)} className="w-full bg-[#FAFAFA] border border-[#E3E3E8] rounded-md px-3 py-2 text-xs font-semibold text-[#1A1A1F]">
              <option value="Bulanan">Bulanan</option>
              <option value="Mingguan">Mingguan</option>
              <option value="Harian">Harian</option>
            </select>
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase mb-1">Filter Owner</label>
            <select value={selectedOwner} onChange={(e) => setSelectedOwner(e.target.value)} className="w-full bg-[#FAFAFA] border border-[#E3E3E8] rounded-md px-3 py-2 text-xs text-[#1A1A1F]">
              <option value="">Semua Owner</option>
              {owners.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>
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

      {/* ── MatView Section 1: Order Ranking & Week-over-Week Growth ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top 10 Order Ranking */}
        <div className="bg-white rounded-lg p-5 border border-[#E3E3E8]">
          <div className="flex items-center justify-between border-b border-[#E3E3E8] pb-3 mb-3">
            <h2 className="text-sm font-bold text-[#1A1A1F]">Order Volume Ranking (Top Performers)</h2>
            <span className="text-[10px] font-semibold text-[#635BFF] bg-[#EBF3FF] px-2 py-0.5 rounded">
              mv_order_ranking
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-[#F5F5F7] text-[#6B6B76] uppercase text-[10px] font-semibold">
                  <th className="p-2 w-10">RANK</th>
                  <th className="p-2">OUTLET & BRAND</th>
                  <th className="p-2">OWNER</th>
                  <th className="p-2 text-right">ORDERS</th>
                  <th className="p-2 text-right">GMV</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E3E3E8]">
                {rankings.map((r) => (
                  <tr key={r.store_id} className="hover:bg-[#F5F5F7]">
                    <td className="p-2 font-bold text-[#635BFF]">#{r.rank}</td>
                    <td className="p-2">
                      <div className="font-semibold text-[#1A1A1F]">{r.outlet_name}</div>
                      <div className="text-[10px] text-[#6B6B76]">{r.brand}</div>
                    </td>
                    <td className="p-2 text-[#3D3D47]">{r.owner_name}</td>
                    <td className="p-2 text-right font-bold text-[#1A1A1F] tabular-nums">
                      {Number(r.total_orders).toLocaleString('id-ID')}
                    </td>
                    <td className="p-2 text-right font-medium text-[#14804A] tabular-nums">
                      {formatIDR(r.total_gmv)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Week-over-Week (WoW) Growth Comparison */}
        <div className="bg-white rounded-lg p-5 border border-[#E3E3E8]">
          <div className="flex items-center justify-between border-b border-[#E3E3E8] pb-3 mb-3">
            <h2 className="text-sm font-bold text-[#1A1A1F]">Perbandingan Week-over-Week (WoW Growth)</h2>
            <span className="text-[10px] font-semibold text-[#635BFF] bg-[#EBF3FF] px-2 py-0.5 rounded">
              mv_week_to_week
            </span>
          </div>
          <div className="overflow-x-auto max-h-[380px]">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-[#F5F5F7] text-[#6B6B76] uppercase text-[10px] font-semibold">
                  <th className="p-2">MINGGU</th>
                  <th className="p-2 text-right">TOTAL ORDER</th>
                  <th className="p-2 text-right">WOW ORDER</th>
                  <th className="p-2 text-right">TOTAL GMV</th>
                  <th className="p-2 text-right">WOW GMV</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E3E3E8]">
                {wowData.slice(-8).reverse().map((w) => {
                  const isOrderPos = w.orders_wow_pct > 0;
                  const isGmvPos = w.gmv_wow_pct > 0;
                  return (
                    <tr key={w.minggu} className="hover:bg-[#F5F5F7]">
                      <td className="p-2 font-semibold text-[#1A1A1F]">
                        {w.minggu}
                        <div className="text-[10px] text-[#9C9CA6]">{w.start_week} - {w.end_week}</div>
                      </td>
                      <td className="p-2 text-right font-bold text-[#1A1A1F] tabular-nums">
                        {Number(w.total_orders).toLocaleString('id-ID')}
                      </td>
                      <td className="p-2 text-right tabular-nums">
                        <span className={`text-[11px] font-bold px-1.5 py-0.5 rounded ${isOrderPos ? 'bg-[#E3FCEF] text-[#14804A]' : w.orders_wow_pct < 0 ? 'bg-[#FDE8EC] text-[#DF1B41]' : 'text-[#6B6B76]'}`}>
                          {w.orders_wow_pct > 0 ? '+' : ''}{w.orders_wow_pct}%
                        </span>
                      </td>
                      <td className="p-2 text-right font-medium text-[#3D3D47] tabular-nums">
                        {formatIDR(w.total_gmv)}
                      </td>
                      <td className="p-2 text-right tabular-nums">
                        <span className={`text-[11px] font-bold px-1.5 py-0.5 rounded ${isGmvPos ? 'bg-[#E3FCEF] text-[#14804A]' : w.gmv_wow_pct < 0 ? 'bg-[#FDE8EC] text-[#DF1B41]' : 'text-[#6B6B76]'}`}>
                          {w.gmv_wow_pct > 0 ? '+' : ''}{w.gmv_wow_pct}%
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ── MatView Section 2: Baseline vs Current Growth Matrix ── */}
      <div className="bg-white rounded-lg p-5 border border-[#E3E3E8]">
        <div className="flex items-center justify-between border-b border-[#E3E3E8] pb-3 mb-3">
          <div>
            <h2 className="text-sm font-bold text-[#1A1A1F]">Baseline vs Current Performance per Owner</h2>
            <p className="text-xs text-[#6B6B76]">Akumulasi performa awal sejak live date dibandingkan posisi terkini</p>
          </div>
          <span className="text-[10px] font-semibold text-[#635BFF] bg-[#EBF3FF] px-2 py-0.5 rounded">
            mv_baseline_vs_current
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {baselineData.slice(0, 6).map((b) => (
            <div key={b.owner_name} className="border border-[#E3E3E8] rounded-lg p-4 bg-[#FAFAFA] flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-bold text-sm text-[#1A1A1F]">{b.owner_name}</span>
                  <span className="text-xs font-semibold text-[#635BFF] bg-[#EBF3FF] px-2 py-0.5 rounded-full">
                    {b.total_outlets} Outlet
                  </span>
                </div>
                <div className="text-[11px] text-[#6B6B76] mb-3">
                  Live Sejak: <span className="font-medium text-[#1A1A1F]">{b.earliest_live || 'N/A'}</span>
                </div>
              </div>
              <div className="pt-2 border-t border-[#E3E3E8] flex items-center justify-between text-xs">
                <div>
                  <span className="text-[#6B6B76] block text-[10px] uppercase font-semibold">Total Orders</span>
                  <span className="font-bold text-[#1A1A1F] tabular-nums">{Number(b.total_orders).toLocaleString('id-ID')}</span>
                </div>
                <div className="text-right">
                  <span className="text-[#6B6B76] block text-[10px] uppercase font-semibold">Total GMV</span>
                  <span className="font-bold text-[#14804A] tabular-nums">{formatIDR(b.total_gmv)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 3 Recharts Bar Charts */}
      <div className="space-y-6">
        <div className="bg-white rounded-lg p-6 space-y-4">
          <h2 className="text-sm font-bold text-[#1A1A1F]">Bar Chart: Pendapatan Kotor</h2>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartRows}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E3E3E8" />
                <XAxis dataKey="periode_label" stroke="#6B6B76" fontSize={11} />
                <YAxis stroke="#6B6B76" fontSize={11} tickFormatter={formatYAxisCurrency} />
                <Tooltip formatter={(value: any) => formatIDR(Number(value))} />
                <Bar dataKey="pendapatan_kotor" fill="#635BFF" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white rounded-lg p-6 space-y-4">
          <h2 className="text-sm font-bold text-[#1A1A1F]">Bar Chart: Pendapatan Bersih</h2>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartRows}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E3E3E8" />
                <XAxis dataKey="periode_label" stroke="#6B6B76" fontSize={11} />
                <YAxis stroke="#6B6B76" fontSize={11} tickFormatter={formatYAxisCurrency} />
                <Tooltip formatter={(value: any) => formatIDR(Number(value))} />
                <Bar dataKey="pendapatan_bersih" fill="#14804A" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Data Table */}
      <div className="bg-white rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-[#E3E3E8] bg-[#F5F5F7]">
          <h2 className="text-sm font-bold text-[#1A1A1F]">Rincian Metrik Laporan Performa ({tipeLaporan})</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#F5F5F7] text-[#6B6B76] uppercase text-[11px] font-semibold border-b border-[#E3E3E8]">
                <th className="p-3">PERIODE</th>
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
              {data.map((r, i) => (
                <tr key={i} className={r.periode_label === 'Grand Total' ? 'bg-[#EBF3FF] font-bold border-t-2 border-[#635BFF]' : 'hover:bg-[#F5F5F7]'}>
                  <td className="p-3 font-semibold">{r.periode_label}</td>
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
    </DashboardLayout>
  );
};
