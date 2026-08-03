import React, { useState, useEffect } from 'react';
import { DashboardLayout } from '../components/layout/DashboardLayout';
import { Search } from 'lucide-react';

import { api, fetchCached } from '../services/api';

interface BillingRow {
  owner_name: string;
  outlet_name: string;
  brand: string;
  nama_resto_final: string;
  store_id: string;
  periode: string;
  jumlah_order_sukses: number;
  biaya: number;
  subtotal_tagihan: number;
  penyesuaian: number;
  total_tagihan: number;
  tanggal_tagihan: string | null;
  transfer_id: string | null;
  tanggal_pembayaran: string | null;
  link_bukti: string | null;
  status_pembayaran: string | null;
}

export const RekapBillingPage: React.FC = () => {
  const [viewMode, setViewMode] = useState<'summary' | 'daily_calculator'>('summary');
  const [cycle, setCycle] = useState<'Weekly' | 'Monthly'>('Weekly');
  const [periodes, setPeriodes] = useState<string[]>([]);
  const [selectedPeriode, setSelectedPeriode] = useState<string>('');
  const [owners, setOwners] = useState<string[]>([]);
  const [selectedOwner, setSelectedOwner] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [data, setData] = useState<BillingRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Daily Calculator State (matching screenshot)
  const [calcOwner, setCalcOwner] = useState<string>('Supriyanti');
  const [calcNominal, setCalcNominal] = useState<number>(1000);
  const [calcNominalStr, setCalcNominalStr] = useState<string>('1000');
  const [calcStart, setCalcStart] = useState<string>('2026-07-20');
  const [calcEnd, setCalcEnd] = useState<string>('2026-07-26');
  const [calcAdjAgency, setCalcAdjAgency] = useState<number>(0);
  const [calcAdjAgencyStr, setCalcAdjAgencyStr] = useState<string>('');
  const [calcAdjKlikit, setCalcAdjKlikit] = useState<number>(0);
  const [calcAdjKlikitStr, setCalcAdjKlikitStr] = useState<string>('');
  const [dailyData, setDailyData] = useState<any[]>([]);
  const [loadingDaily, setLoadingDaily] = useState<boolean>(false);

  const formatIDR = (val: number | null | undefined) => {
    const num = Math.round(Number(val || 0));
    return `Rp ${num.toLocaleString('id-ID')}`;
  };

  useEffect(() => {
    loadOwners();
  }, []);

  useEffect(() => {
    setSelectedPeriode('');
  }, [cycle]);

  useEffect(() => {
    if (viewMode === 'summary') {
      loadBillingData();
    } else {
      loadDailyCalculator();
    }
  }, [viewMode, cycle, selectedPeriode, selectedOwner, calcOwner, calcNominal, calcStart, calcEnd]);

  const loadOwners = async () => {
    try {
      const json = await fetchCached('/api/rekap-tagihan/owners');
      if (json.owners && json.owners.length > 0) {
        setOwners(json.owners);
        if (!calcOwner) setCalcOwner(json.owners[0]);
      }
    } catch (err) {
      console.error('Error loading owners:', err);
    }
  };

  const loadDailyCalculator = async () => {
    if (!calcOwner) return;
    setLoadingDaily(true);
    try {
      const res = await api.getRekapTagihanDaily(calcOwner, calcStart, calcEnd, calcNominal);
      if (res && res.data) {
        setDailyData(res.data);
      }
    } catch (err) {
      console.error('Error loading daily calculator data:', err);
    } finally {
      setLoadingDaily(false);
    }
  };

  const loadBillingData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ billing_cycle: cycle });
      if (selectedPeriode) params.set('periode', selectedPeriode);
      if (selectedOwner) params.set('owner', selectedOwner);

      const json = await fetchCached(`/api/rekap-tagihan-billing?${params.toString()}`);

      const rows: BillingRow[] = json.data || [];
      setData(rows);

      // Build unique periodes list from data
      const uniq = [...new Set(rows.map(r => r.periode).filter(Boolean))].sort().reverse();
      setPeriodes(uniq);
    } catch (err) {
      console.error('Error loading billing data:', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredRows = data.filter(r =>
    !searchQuery || r.owner_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    r.nama_resto_final?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const totalOrders = filteredRows.reduce((s, r) => s + Number(r.jumlah_order_sukses || 0), 0);
  const totalSubtotal = filteredRows.reduce((s, r) => s + Number(r.subtotal_tagihan || 0), 0);
  const totalPenyesuaian = filteredRows.reduce((s, r) => s + Number(r.penyesuaian || 0), 0);
  const totalTagihan = filteredRows.reduce((s, r) => s + Number(r.total_tagihan || 0), 0);

  const statusColor = (status: string | null) => {
    if (!status) return 'bg-[#F1F1F5] text-[#6B6B76] border-[#E3E3E8]';
    const s = status.toUpperCase();
    if (s === 'LUNAS' || s === 'PAID') return 'bg-[#EAF7ED] text-[#14804A] border-[#14804A]/20';
    if (s === 'PENDING') return 'bg-[#FEF3D6] text-[#B76E00] border-[#B76E00]/20';
    return 'bg-[#FDE8EC] text-[#DF1B41] border-[#DF1B41]/20';
  };

  return (
    <DashboardLayout
      title="Rekap Tagihan Billing"
      subtitle="Rekapitulasi tagihan billing mingguan & bulanan per outlet serta kalkulator rincian harian per owner"
    >
      {/* Top Main Mode Toggle */}
      <div className="flex items-center gap-2 border-b border-[#E3E3E8] pb-3 mb-5">
        <button
          onClick={() => setViewMode('summary')}
          className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${viewMode === 'summary'
            ? 'bg-[#635BFF] text-white shadow-sm'
            : 'bg-white text-[#6B6B76] border border-[#E3E3E8] hover:bg-[#F5F5F7]'
            }`}
        >
          Rekap Tagihan
        </button>
        <button
          onClick={() => setViewMode('daily_calculator')}
          className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${viewMode === 'daily_calculator'
            ? 'bg-[#635BFF] text-white shadow-sm'
            : 'bg-white text-[#6B6B76] border border-[#E3E3E8] hover:bg-[#F5F5F7]'
            }`}
        >
          27/05 Rekap Tagihan
        </button>
      </div>

      {viewMode === 'daily_calculator' ? (
        /* ── CALCULATOR MODE MATCHING SCREENSHOT ── */
        <div className="space-y-6">
          {/* Header Form matching Screenshot */}
          <div className="bg-white rounded-lg p-5 border border-[#E3E3E8] shadow-sm">
            <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase tracking-wider mb-1">Owner</label>
                <select
                  value={calcOwner}
                  onChange={(e) => setCalcOwner(e.target.value)}
                  className="w-full bg-[#FAFAFA] border border-[#E3E3E8] rounded-md px-3 py-2 text-xs font-medium text-[#1A1A1F]"
                >
                  {owners.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase tracking-wider mb-1">Nominal Bagi Hasil</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-[#9C9CA6]">Rp</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={calcNominalStr}
                    onChange={(e) => {
                      const raw = e.target.value;
                      if (raw === '' || raw === '-' || /^-?\d*$/.test(raw)) {
                        setCalcNominalStr(raw);
                        const parsed = parseInt(raw, 10);
                        if (!isNaN(parsed)) setCalcNominal(parsed);
                      }
                    }}
                    onBlur={() => {
                      const parsed = parseInt(calcNominalStr, 10);
                      const val = isNaN(parsed) ? 0 : parsed;
                      setCalcNominal(val);
                      setCalcNominalStr(String(val));
                    }}
                    className="w-full pl-8 pr-3 py-2 bg-[#FAFAFA] border border-[#E3E3E8] rounded-md text-xs font-medium text-[#1A1A1F]"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase tracking-wider mb-1">Dari</label>
                <input
                  type="date"
                  value={calcStart}
                  onChange={(e) => setCalcStart(e.target.value)}
                  className="w-full bg-[#FAFAFA] border border-[#E3E3E8] rounded-md px-3 py-2 text-xs font-medium text-[#1A1A1F]"
                />
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase tracking-wider mb-1">Hingga</label>
                <input
                  type="date"
                  value={calcEnd}
                  onChange={(e) => setCalcEnd(e.target.value)}
                  className="w-full bg-[#FAFAFA] border border-[#E3E3E8] rounded-md px-3 py-2 text-xs font-medium text-[#1A1A1F]"
                />
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase tracking-wider mb-1">Penyesuaian Agency</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-[#9C9CA6]">Rp</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={calcAdjAgencyStr}
                    placeholder="0"
                    onChange={(e) => {
                      const raw = e.target.value;
                      if (raw === '' || raw === '-' || /^-?\d*$/.test(raw)) {
                        setCalcAdjAgencyStr(raw);
                        const parsed = parseInt(raw, 10);
                        setCalcAdjAgency(isNaN(parsed) ? 0 : parsed);
                      }
                    }}
                    onBlur={() => {
                      const parsed = parseInt(calcAdjAgencyStr, 10);
                      const val = isNaN(parsed) ? 0 : parsed;
                      setCalcAdjAgency(val);
                      setCalcAdjAgencyStr(val === 0 ? '' : String(val));
                    }}
                    className="w-full pl-8 pr-3 py-2 bg-[#FAFAFA] border border-[#E3E3E8] rounded-md text-xs font-medium text-[#1A1A1F]"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase tracking-wider mb-1">Penyesuaian Klikit</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-[#9C9CA6]">Rp</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={calcAdjKlikitStr}
                    placeholder="0"
                    onChange={(e) => {
                      const raw = e.target.value;
                      if (raw === '' || raw === '-' || /^-?\d*$/.test(raw)) {
                        setCalcAdjKlikitStr(raw);
                        const parsed = parseInt(raw, 10);
                        setCalcAdjKlikit(isNaN(parsed) ? 0 : parsed);
                      }
                    }}
                    onBlur={() => {
                      const parsed = parseInt(calcAdjKlikitStr, 10);
                      const val = isNaN(parsed) ? 0 : parsed;
                      setCalcAdjKlikit(val);
                      setCalcAdjKlikitStr(val === 0 ? '' : String(val));
                    }}
                    className="w-full pl-8 pr-3 py-2 bg-[#FAFAFA] border border-[#E3E3E8] rounded-md text-xs font-medium text-[#1A1A1F]"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Daily Table matching Screenshot */}
          <div className="bg-white rounded-lg overflow-hidden border border-[#E3E3E8] shadow-sm">
            <div className="px-5 py-3 border-b border-[#E3E3E8] bg-[#F5F5F7] flex items-center justify-between">
              <h2 className="text-sm font-bold text-[#1A1A1F]">Rincian Perhitungan Tagihan Harian - Owner: {calcOwner}</h2>
              <span className="text-xs font-semibold text-[#635BFF] bg-[#EBF3FF] px-2.5 py-1 rounded">
                Rate: {formatIDR(calcNominal)} / Order
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-[#4A6B82] text-white uppercase text-[11px] font-semibold border-b border-[#3B576B]">
                    <th className="px-4 py-3">Tanggal</th>
                    <th className="px-4 py-3 text-right">Pendapatan Kotor</th>
                    <th className="px-4 py-3 text-right">Potongan Ojol</th>
                    <th className="px-4 py-3 text-right">Pendapatan Bersih</th>
                    <th className="px-4 py-3 text-right">Total Order Sukses</th>
                    <th className="px-4 py-3 text-right">Total Bagi Hasil (+ Penyesuaian)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E3E3E8]">
                  {loadingDaily ? (
                    [...Array(5)].map((_, i) => (
                      <tr key={i} className="animate-pulse">
                        <td className="px-4 py-3"><div className="h-4 w-24 bg-[#E3E3E8] rounded" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-20 bg-[#E3E3E8] rounded ml-auto" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-20 bg-[#E3E3E8] rounded ml-auto" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-20 bg-[#E3E3E8] rounded ml-auto" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-12 bg-[#E3E3E8] rounded ml-auto" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-20 bg-[#E3E3E8] rounded ml-auto" /></td>
                      </tr>
                    ))
                  ) : dailyData.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-[#6B6B76]">Tidak ada data transaksi ditemukan untuk owner ini.</td>
                    </tr>
                  ) : (
                    dailyData.map((r, i) => {
                      const isGrandTotal = r.tanggal === 'Grand Total';
                      const totalAdj = calcAdjAgency + calcAdjKlikit;
                      const displayBagiHasil = isGrandTotal
                        ? Number(r.total_bagi_hasil || 0) + totalAdj
                        : Number(r.total_bagi_hasil || 0);

                      return (
                        <React.Fragment key={i}>
                          {isGrandTotal && totalAdj !== 0 && (
                            <tr className="bg-[#FFFBEB] border-t border-[#FDE68A]">
                              <td className="px-4 py-2 text-xs font-semibold text-[#B76E00]" colSpan={5}>Rincian Penyesuaian</td>
                              <td className="px-4 py-2 text-right text-xs tabular-nums">
                                {calcAdjAgency !== 0 && (
                                  <div className="text-[#B76E00] font-semibold">Agency: {calcAdjAgency > 0 ? '+' : ''}{formatIDR(calcAdjAgency)}</div>
                                )}
                                {calcAdjKlikit !== 0 && (
                                  <div className="text-[#B76E00] font-semibold">Klikit: {calcAdjKlikit > 0 ? '+' : ''}{formatIDR(calcAdjKlikit)}</div>
                                )}
                              </td>
                            </tr>
                          )}
                          <tr
                            className={isGrandTotal ? 'bg-[#EBF3FF] font-bold border-t-2 border-[#4A6B82] text-sm' : 'hover:bg-[#F5F5F7] transition-colors'}
                          >
                            <td className="px-4 py-2.5 font-semibold text-[#1A1A1F]">{r.tanggal}</td>
                            <td className="px-4 py-2.5 text-right tabular-nums">{formatIDR(r.pendapatan_kotor)}</td>
                            <td className="px-4 py-2.5 text-right tabular-nums">{formatIDR(r.potongan_ojol)}</td>
                            <td className="px-4 py-2.5 text-right tabular-nums">{formatIDR(r.pendapatan_bersih)}</td>
                            <td className="px-4 py-2.5 text-right tabular-nums font-semibold">{Number(r.total_order_sukses || 0).toLocaleString('id-ID')}</td>
                            <td className="px-4 py-2.5 text-right tabular-nums font-bold text-[#14804A]">
                              {formatIDR(displayBagiHasil)}
                              {isGrandTotal && totalAdj !== 0 && (
                                <div className="text-[10px] font-normal text-[#6B6B76] mt-0.5">
                                  Dasar: {formatIDR(r.total_bagi_hasil)} + Penyesuaian: {totalAdj > 0 ? '+' : ''}{formatIDR(totalAdj)}
                                </div>
                              )}
                            </td>
                          </tr>
                        </React.Fragment>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : (
        /* ── SUMMARY MODE (WEEKLY / MONTHLY) ── */
        <div className="space-y-6">
          {/* Controls */}
          <div className="bg-white rounded-lg p-5 space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-4 border-b border-[#E3E3E8] pb-4">
              <div className="inline-flex bg-[#F5F5F7] border border-[#E3E3E8] rounded-md p-1">
                <button
                  onClick={() => setCycle('Weekly')}
                  className={`px-4 py-1.5 rounded-sm text-xs font-semibold transition-all ${cycle === 'Weekly' ? 'bg-[#635BFF] text-white shadow-sm' : 'text-[#6B6B76] hover:text-[#1A1A1F]'
                    }`}
                >
                  Mingguan
                </button>
                <button
                  onClick={() => setCycle('Monthly')}
                  className={`px-4 py-1.5 rounded-sm text-xs font-semibold transition-all ${cycle === 'Monthly' ? 'bg-[#635BFF] text-white shadow-sm' : 'text-[#6B6B76] hover:text-[#1A1A1F]'
                    }`}
                >
                  Bulanan
                </button>
              </div>

              <div className="relative">
                <Search className="w-4 h-4 text-[#9C9CA6] absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Cari owner atau nama resto..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9 pr-4 py-1.5 bg-[#FAFAFA] border border-[#E3E3E8] rounded-md text-xs text-[#1A1A1F] focus:outline-none focus:border-[#635BFF] w-72"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase tracking-wider mb-1">Pilih Periode</label>
                <select
                  value={selectedPeriode}
                  onChange={(e) => setSelectedPeriode(e.target.value)}
                  className="w-full bg-[#FAFAFA] border border-[#E3E3E8] rounded-md px-3 py-2 text-xs font-medium text-[#1A1A1F]"
                >
                  <option value="">Semua Periode</option>
                  {periodes.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B76] uppercase tracking-wider mb-1">Filter Owner</label>
                <select
                  value={selectedOwner}
                  onChange={(e) => setSelectedOwner(e.target.value)}
                  className="w-full bg-[#FAFAFA] border border-[#E3E3E8] rounded-md px-3 py-2 text-xs font-medium text-[#1A1A1F]"
                >
                  <option value="">Semua Owner</option>
                  {owners.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              </div>
            </div>
          </div>

          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-lg p-4">
              <div className="text-[11px] font-semibold text-[#6B6B76] uppercase tracking-wider">Total Order Sukses</div>
              {loading ? (
                <div className="h-7 w-28 bg-[#E3E3E8] animate-pulse rounded-md mt-1" />
              ) : (
                <div className="text-2xl font-bold text-[#1A1A1F] tabular-nums mt-1">{totalOrders.toLocaleString('id-ID')}</div>
              )}
            </div>
            <div className="bg-white rounded-lg p-4">
              <div className="text-[11px] font-semibold text-[#6B6B76] uppercase tracking-wider">Subtotal Tagihan</div>
              {loading ? (
                <div className="h-7 w-28 bg-[#E3E3E8] animate-pulse rounded-md mt-1" />
              ) : (
                <div className="text-xl font-bold text-[#1A1A1F] tabular-nums mt-1">{formatIDR(totalSubtotal)}</div>
              )}
            </div>
            <div className="bg-white rounded-lg p-4">
              <div className="text-[11px] font-semibold text-[#6B6B76] uppercase tracking-wider">Penyesuaian</div>
              {loading ? (
                <div className="h-7 w-28 bg-[#E3E3E8] animate-pulse rounded-md mt-1" />
              ) : (
                <div className={`text-xl font-bold tabular-nums mt-1 ${totalPenyesuaian >= 0 ? 'text-[#14804A]' : 'text-[#DF1B41]'}`}>{formatIDR(totalPenyesuaian)}</div>
              )}
            </div>
            <div className="bg-white rounded-lg p-4">
              <div className="text-[11px] font-semibold text-[#6B6B76] uppercase tracking-wider">Total Tagihan</div>
              {loading ? (
                <div className="h-7 w-28 bg-[#E3E3E8] animate-pulse rounded-md mt-1" />
              ) : (
                <div className="text-xl font-bold text-[#635BFF] tabular-nums mt-1">{formatIDR(totalTagihan)}</div>
              )}
            </div>
          </div>

          {/* Table */}
          <div className="bg-white rounded-lg overflow-hidden">
            <div className="px-5 py-3 border-b border-[#E3E3E8] bg-[#F5F5F7] flex items-center justify-between">
              <h2 className="text-sm font-bold text-[#1A1A1F]">Detail Tagihan Billing ({cycle})</h2>
              {loading ? (
                <div className="h-4 w-14 bg-[#E3E3E8] animate-pulse rounded" />
              ) : (
                <span className="text-xs text-[#6B6B76]">{filteredRows.length.toLocaleString('id-ID')} baris</span>
              )}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-[#F5F5F7] text-[#6B6B76] uppercase text-[11px] font-semibold border-b border-[#E3E3E8]">
                    <th className="px-4 py-3">No</th>
                    <th className="px-4 py-3">Owner</th>
                    <th className="px-4 py-3">Nama Resto</th>
                    <th className="px-4 py-3">Periode</th>
                    <th className="px-4 py-3 text-right">Order Sukses</th>
                    <th className="px-4 py-3 text-right">Biaya/Order</th>
                    <th className="px-4 py-3 text-right">Subtotal</th>
                    <th className="px-4 py-3 text-right">Penyesuaian</th>
                    <th className="px-4 py-3 text-right">Total Tagihan</th>
                    <th className="px-4 py-3">Tgl Tagihan</th>
                    <th className="px-4 py-3 text-center">Status</th>
                    <th className="px-4 py-3">Bukti</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E3E3E8]">
                  {loading ? (
                    [...Array(5)].map((_, i) => (
                      <tr key={i} className="animate-pulse">
                        <td className="px-4 py-3"><div className="h-4 w-4 bg-[#E3E3E8] rounded" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-28 bg-[#E3E3E8] rounded" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-36 bg-[#E3E3E8] rounded" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-20 bg-[#E3E3E8] rounded" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-12 bg-[#E3E3E8] rounded ml-auto" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-16 bg-[#E3E3E8] rounded ml-auto" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-20 bg-[#E3E3E8] rounded ml-auto" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-16 bg-[#E3E3E8] rounded ml-auto" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-20 bg-[#E3E3E8] rounded ml-auto" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-20 bg-[#E3E3E8] rounded" /></td>
                        <td className="px-4 py-3 text-center"><div className="h-5 w-20 bg-[#E3E3E8] rounded mx-auto" /></td>
                        <td className="px-4 py-3"><div className="h-4 w-10 bg-[#E3E3E8] rounded" /></td>
                      </tr>
                    ))
                  ) : filteredRows.length === 0 ? (
                    <tr>
                      <td colSpan={12} className="p-8 text-center text-[#6B6B76]">Tidak ada data tagihan ditemukan.</td>
                    </tr>
                  ) : (
                    filteredRows.map((r, i) => (
                      <tr key={i} className="hover:bg-[#F5F5F7] transition-colors">
                        <td className="px-4 py-2.5 text-[#9C9CA6]">{i + 1}</td>
                        <td className="px-4 py-2.5 font-medium text-[#1A1A1F] whitespace-nowrap">{r.owner_name}</td>
                        <td className="px-4 py-2.5 text-[#3D3D47] max-w-[200px] truncate" title={r.nama_resto_final}>{r.nama_resto_final}</td>
                        <td className="px-4 py-2.5">
                          <span className="inline-block bg-[#EBF3FF] text-[#1B4FD8] px-2 py-0.5 rounded text-[11px] font-semibold">{r.periode}</span>
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums font-semibold">{Number(r.jumlah_order_sukses || 0).toLocaleString('id-ID')}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{formatIDR(r.biaya)}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{formatIDR(r.subtotal_tagihan)}</td>
                        <td className={`px-4 py-2.5 text-right tabular-nums ${Number(r.penyesuaian || 0) < 0 ? 'text-[#DF1B41]' : 'text-[#14804A]'}`}>
                          {Number(r.penyesuaian || 0) !== 0 ? formatIDR(r.penyesuaian) : '-'}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums font-bold text-[#635BFF]">{formatIDR(r.total_tagihan)}</td>
                        <td className="px-4 py-2.5 whitespace-nowrap text-[#6B6B76]">{r.tanggal_tagihan || '-'}</td>
                        <td className="px-4 py-2.5 text-center">
                          <span className={`inline-block px-2 py-0.5 rounded text-[11px] font-semibold border ${statusColor(r.status_pembayaran)}`}>
                            {r.status_pembayaran || 'BELUM DIBAYAR'}
                          </span>
                        </td>
                        <td className="px-4 py-2.5">
                          {r.link_bukti ? (
                            <a href={r.link_bukti} target="_blank" rel="noreferrer" className="text-[#635BFF] underline text-[11px]">Lihat</a>
                          ) : <span className="text-[#9C9CA6]">-</span>}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
};
