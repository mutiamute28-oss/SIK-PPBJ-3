import { useEffect, useState, useCallback } from "react";
import api, { rupiah, formatApiErrorDetail } from "@/lib/api";
import Modal from "@/components/Modal";
import { useAuth } from "@/context/AuthContext";
import { Wallet, Plus, Pencil, Trash2, TrendingUp, AlertTriangle, FileSpreadsheet, CalendarRange, CalendarDays } from "lucide-react";
import { toast } from "sonner";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid } from "recharts";

const MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
  "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];

const monthLabel = (p) => {
  if (!p) return "";
  const [y, m] = p.split("-");
  return `${MONTHS[Number(m) - 1] || m} ${y}`;
};

const compact = (n) => {
  const v = Number(n) || 0;
  if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(1)} M`;
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(0)} jt`;
  if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(0)} rb`;
  return String(v);
};

export default function AnggaranBulanan() {
  const { user } = useAuth();
  const canEdit = ["admin", "keuangan"].includes(user?.role);
  const now = new Date();
  const [view, setView] = useState("bulanan");
  const [units, setUnits] = useState([]);

  useEffect(() => { api.get("/budget-units").then((r) => setUnits(r.data)).catch(() => {}); }, []);

  return (
    <div className="space-y-5" data-testid="anggaran-bulanan">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl lg:text-3xl font-bold text-slate-900">Anggaran</h1>
          <p className="text-slate-500 text-sm mt-1">Pagu anggaran per unit kerja dibandingkan realisasi dokumen disetujui &amp; terjurnal.</p>
        </div>
        <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1">
          <button data-testid="tab-bulanan" onClick={() => setView("bulanan")}
            className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-md text-sm font-semibold transition-colors ${view === "bulanan" ? "bg-[#14758a] text-white" : "text-slate-600 hover:bg-slate-50"}`}>
            <CalendarDays className="w-4 h-4" /> Bulanan
          </button>
          <button data-testid="tab-tahunan" onClick={() => setView("tahunan")}
            className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-md text-sm font-semibold transition-colors ${view === "tahunan" ? "bg-[#14758a] text-white" : "text-slate-600 hover:bg-slate-50"}`}>
            <CalendarRange className="w-4 h-4" /> Tahunan
          </button>
        </div>
      </div>

      {view === "bulanan"
        ? <MonthlyView canEdit={canEdit} units={units} now={now} />
        : <AnnualView units={units} now={now} />}
    </div>
  );
}

function MonthlyView({ canEdit, units, now }) {
  const [period, setPeriod] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const { data } = await api.get(`/budgets?period=${period}`);
    setData(data);
    setLoading(false);
  }, [period]);

  useEffect(() => { load(); }, [load]);

  const remove = async (bid) => {
    if (!window.confirm("Hapus anggaran unit ini?")) return;
    await api.delete(`/budgets/${bid}`);
    toast.success("Anggaran dihapus");
    load();
  };

  const rows = data?.rows || [];
  const totalPagu = data?.total_pagu || 0;
  const totalReal = data?.total_realisasi || 0;
  const totalSisa = totalPagu - totalReal;
  const overCount = rows.filter((r) => !r.no_budget && r.sisa < 0).length;

  const exportExcel = async () => {
    setExporting(true);
    try {
      const res = await api.get(`/budgets/export?period=${period}`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Rekap_Anggaran_${period}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Excel berhasil diunduh");
    } catch (e) {
      toast.error("Gagal mengunduh Excel. Coba lagi.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase mb-1">Periode</label>
          <input data-testid="period-picker" type="month" value={period} onChange={(e) => setPeriod(e.target.value)}
            className="border border-slate-300 rounded-md px-3 py-2 text-sm" />
        </div>
        <div className="flex gap-2">
          <button data-testid="export-anggaran-excel" onClick={exportExcel} disabled={exporting}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md bg-[#f2941f] hover:bg-[#d98014] text-white text-sm font-semibold disabled:opacity-60">
            <FileSpreadsheet className="w-4 h-4" /> {exporting ? "Menyiapkan…" : "Export Excel"}
          </button>
          {canEdit && (
            <button data-testid="add-budget-btn" onClick={() => setEditing({ unit_kerja: "", period, amount: 0, catatan: "" })}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md bg-[#14758a] hover:bg-[#0f5e6f] text-white text-sm font-semibold">
              <Plus className="w-4 h-4" /> Tambah Anggaran
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Total Pagu" value={rupiah(totalPagu)} icon={Wallet} tone="text-teal-600 bg-teal-50" />
        <Stat label="Total Realisasi" value={rupiah(totalReal)} icon={TrendingUp} tone="text-indigo-600 bg-indigo-50" />
        <Stat label="Sisa Anggaran" value={rupiah(totalSisa)} icon={Wallet}
          tone={totalSisa < 0 ? "text-red-600 bg-red-50" : "text-green-600 bg-green-50"} />
        <Stat label="Unit Melebihi Pagu" value={`${overCount} unit`} icon={AlertTriangle}
          tone={overCount ? "text-red-600 bg-red-50" : "text-slate-500 bg-slate-100"} />
      </div>

      <div className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <h3 className="font-heading font-semibold text-slate-900">Perbandingan {monthLabel(period)}</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 text-slate-600 text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left px-4 py-3 font-semibold">Unit Kerja</th>
                <th className="text-right px-4 py-3 font-semibold">Pagu</th>
                <th className="text-right px-4 py-3 font-semibold">Realisasi</th>
                <th className="text-right px-4 py-3 font-semibold">Sisa</th>
                <th className="text-left px-4 py-3 font-semibold w-[220px]">Serapan</th>
                {canEdit && <th className="text-right px-4 py-3 font-semibold">Aksi</th>}
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={canEdit ? 6 : 5} className="px-4 py-8 text-center text-slate-400">Memuat…</td></tr>}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={canEdit ? 6 : 5} className="px-4 py-12 text-center text-slate-400">
                  <Wallet className="w-8 h-8 mx-auto mb-2 opacity-40" />
                  Belum ada anggaran atau realisasi untuk periode ini.
                </td></tr>
              )}
              {rows.map((r, i) => {
                const pct = r.persen || 0;
                const over = !r.no_budget && r.sisa < 0;
                return (
                  <tr key={r.id || `nb-${i}`} className="border-t border-slate-100 hover:bg-teal-50/40" data-testid={`budget-row-${r.unit_kerja}`}>
                    <td className="px-4 py-3 text-slate-800 font-medium">
                      {r.unit_kerja}
                      {r.no_budget && <span className="ml-2 text-[10px] font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full">Belum dianggarkan</span>}
                      {r.catatan && <div className="text-xs text-slate-400 font-normal">{r.catatan}</div>}
                    </td>
                    <td className="px-4 py-3 text-right tabular text-slate-700">{r.no_budget ? "—" : rupiah(r.amount)}</td>
                    <td className="px-4 py-3 text-right tabular text-slate-700">{rupiah(r.realisasi)}<span className="block text-[10px] text-slate-400">{r.doc_count} dok.</span></td>
                    <td className={`px-4 py-3 text-right tabular font-semibold ${over ? "text-red-600" : "text-slate-800"}`}>{r.no_budget ? "—" : rupiah(r.sisa)}</td>
                    <td className="px-4 py-3">
                      {r.no_budget ? <span className="text-xs text-slate-400">—</span> : (
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full ${over ? "bg-red-500" : pct > 85 ? "bg-amber-500" : "bg-[#14758a]"}`}
                              style={{ width: `${Math.min(pct, 100)}%` }} />
                          </div>
                          <span className={`text-xs font-semibold tabular ${over ? "text-red-600" : "text-slate-500"}`}>{pct}%</span>
                        </div>
                      )}
                    </td>
                    {canEdit && (
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <button data-testid={`edit-budget-${r.unit_kerja}`} onClick={() => setEditing(r.no_budget
                          ? { unit_kerja: r.unit_kerja, period, amount: 0, catatan: "" }
                          : { id: r.id, unit_kerja: r.unit_kerja, period: r.period, amount: r.amount, catatan: r.catatan || "" })}
                          className="p-2 text-slate-500 hover:text-[#14758a] hover:bg-slate-100 rounded-md"><Pencil className="w-4 h-4" /></button>
                        {!r.no_budget && (
                          <button data-testid={`delete-budget-${r.unit_kerja}`} onClick={() => remove(r.id)}
                            className="p-2 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-md"><Trash2 className="w-4 h-4" /></button>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {editing && <BudgetModal editing={editing} setEditing={setEditing} units={units} onSaved={load} />}
    </>
  );
}

function AnnualView({ units, now }) {
  const [year, setYear] = useState(now.getFullYear());
  const [unit, setUnit] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ year: String(year) });
    if (unit) params.set("unit_kerja", unit);
    api.get(`/budgets/annual?${params.toString()}`).then((r) => setData(r.data)).finally(() => setLoading(false));
  }, [year, unit]);

  const chartData = (data?.months || []).map((m) => ({
    name: MONTHS_SHORT[m.month - 1], Pagu: m.pagu, Realisasi: m.realisasi,
  }));
  const totalPagu = data?.total_pagu || 0;
  const totalReal = data?.total_realisasi || 0;

  return (
    <>
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase mb-1">Tahun</label>
          <input data-testid="year-picker" type="number" min="2020" max="2100" value={year}
            onChange={(e) => setYear(Number(e.target.value))} className="border border-slate-300 rounded-md px-3 py-2 text-sm w-28" />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase mb-1">Unit Kerja</label>
          <select data-testid="unit-filter" value={unit} onChange={(e) => setUnit(e.target.value)}
            className="border border-slate-300 rounded-md px-3 py-2 text-sm min-w-[200px]">
            <option value="">Semua Unit</option>
            {units.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
        </div>
        <div className="ml-auto flex gap-4 text-sm">
          <div><span className="text-slate-400 text-xs uppercase">Pagu {year}</span><div className="font-bold tabular text-slate-900">{rupiah(totalPagu)}</div></div>
          <div><span className="text-slate-400 text-xs uppercase">Realisasi {year}</span><div className="font-bold tabular text-slate-900">{rupiah(totalReal)}</div></div>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-5" data-testid="annual-chart">
        <h3 className="font-heading font-semibold text-slate-900 mb-4">Tren Pagu vs Realisasi {year}{unit ? ` — ${unit}` : ""}</h3>
        {loading ? (
          <div className="h-[340px] flex items-center justify-center text-slate-400">Memuat grafik…</div>
        ) : (
          <div style={{ width: "100%", height: 340 }}>
            <ResponsiveContainer>
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12, fill: "#64748b" }} axisLine={{ stroke: "#cbd5e1" }} tickLine={false} />
                <YAxis tickFormatter={compact} tick={{ fontSize: 12, fill: "#64748b" }} axisLine={false} tickLine={false} width={56} />
                <Tooltip formatter={(v) => rupiah(v)} contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13 }} />
                <Legend wrapperStyle={{ fontSize: 13 }} />
                <Bar dataKey="Pagu" fill="#14758a" radius={[4, 4, 0, 0]} maxBarSize={28} />
                <Bar dataKey="Realisasi" fill="#f2941f" radius={[4, 4, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </>
  );
}

function Stat({ label, value, icon: Icon, tone }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-5">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center mb-3 ${tone}`}><Icon className="w-5 h-5" /></div>
      <div className="text-xl font-bold text-slate-900 tabular">{value}</div>
      <div className="text-xs text-slate-500 mt-0.5">{label}</div>
    </div>
  );
}

function BudgetModal({ editing, setEditing, units, onSaved }) {
  const [form, setForm] = useState(editing);
  const [saving, setSaving] = useState(false);
  const isEdit = !!editing.id;

  const save = async () => {
    if (!form.unit_kerja.trim()) { toast.error("Unit kerja wajib diisi"); return; }
    setSaving(true);
    try {
      if (isEdit) await api.put(`/budgets/${form.id}`, form);
      else await api.post("/budgets", form);
      toast.success("Anggaran disimpan");
      setEditing(null);
      onSaved();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open onClose={() => setEditing(null)} title={isEdit ? "Ubah Anggaran" : "Tambah Anggaran"}>
      <div className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase mb-1">Unit Kerja</label>
          <input data-testid="budget-unit-input" list="unit-options" value={form.unit_kerja}
            onChange={(e) => setForm({ ...form, unit_kerja: e.target.value })}
            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" placeholder="cth. Bagian Umum" />
          <datalist id="unit-options">{units.map((u) => <option key={u} value={u} />)}</datalist>
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase mb-1">Periode</label>
          <input data-testid="budget-period-input" type="month" value={form.period}
            onChange={(e) => setForm({ ...form, period: e.target.value })}
            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase mb-1">Pagu Anggaran (Rp)</label>
          <input data-testid="budget-amount-input" type="number" min="0" value={form.amount}
            onChange={(e) => setForm({ ...form, amount: Number(e.target.value) })}
            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm tabular" />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase mb-1">Catatan (opsional)</label>
          <input data-testid="budget-note-input" value={form.catatan}
            onChange={(e) => setForm({ ...form, catatan: e.target.value })}
            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={() => setEditing(null)} className="px-4 py-2.5 rounded-md border border-slate-300 text-slate-700 text-sm font-semibold hover:bg-slate-50">Batal</button>
          <button data-testid="save-budget-btn" onClick={save} disabled={saving}
            className="px-4 py-2.5 rounded-md bg-[#14758a] hover:bg-[#0f5e6f] text-white text-sm font-semibold disabled:opacity-60">
            {saving ? "Menyimpan…" : "Simpan"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
