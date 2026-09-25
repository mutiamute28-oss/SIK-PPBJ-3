import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import TourModal from "@/components/TourModal";
import {
  LayoutDashboard, FileText, Wallet, Receipt, ClipboardCheck, Coins, ReceiptText,
  BookOpen, PiggyBank, Percent, ListTree, Users, History, Search, PlayCircle,
  ChevronDown, ShieldCheck, ArrowRight, HelpCircle, Workflow, Info, BookMarked,
} from "lucide-react";

const ROLE_LABELS = {
  superadmin: "Super Admin",
  admin: "Admin",
  keuangan: "Keuangan",
  approver: "Approver",
  user: "User (Pemohon)",
};

const FLOW = [
  { code: "PPBJ", label: "Permintaan Pengadaan", desc: "Pemohon mengajukan kebutuhan barang/jasa." },
  { code: "PUM", label: "Permohonan Uang Muka", desc: "Pengajuan uang muka atas kegiatan yang disetujui." },
  { code: "PP", label: "Permohonan Pembayaran", desc: "Permohonan pembayaran kepada pihak ketiga." },
  { code: "PTUM", label: "Pertanggungjawaban UM", desc: "Laporan penggunaan uang muka." },
  { code: "Jurnal", label: "Jurnal Umum", desc: "Keuangan menjurnal & mengekspor ke Accurate." },
];

const ROLES = [
  { role: "superadmin", color: "bg-amber-100 text-amber-800 border-amber-200", can: ["Akses penuh ke seluruh modul", "Mengelola semua pengguna termasuk Admin", "Pengaturan sistem"] },
  { role: "admin", color: "bg-teal-100 text-teal-800 border-teal-200", can: ["Mengelola pengguna & hak akses", "Melihat Log Aktivitas", "Akses seluruh modul dokumen & master data"] },
  { role: "keuangan", color: "bg-blue-100 text-blue-800 border-blue-200", can: ["Memverifikasi dokumen", "Membuat Jurnal Umum & ekspor Accurate", "Mengelola Master Akun (COA) & Pajak", "Mengelola & mengekspor Anggaran"] },
  { role: "approver", color: "bg-purple-100 text-purple-800 border-purple-200", can: ["Meninjau & menyetujui/menolak pengajuan", "Melihat seluruh dokumen & anggaran"] },
  { role: "user", color: "bg-slate-100 text-slate-700 border-slate-200", can: ["Membuat & mengajukan dokumen (PPBJ, PUM, PP, PTUM, Kas Kecil, NRP)", "Memantau status pengajuan sendiri"] },
];

const MODULES = [
  {
    id: "dashboard", icon: LayoutDashboard, label: "Dashboard", path: "/", roles: ["Semua peran"],
    purpose: "Ringkasan cepat kondisi pengajuan & penjurnalan.",
    steps: [
      "Lihat jumlah pengajuan per jenis (PPBJ, PUM, PP, PTUM) pada kartu atas.",
      "Pantau status ringkas: Menunggu, Disetujui, Jurnal Dibuat, dan Total Nilai Pengajuan.",
      "Klik kartu jenis dokumen untuk langsung membuka daftarnya.",
      "Tinjau tabel 'Pengajuan Terbaru' untuk aktivitas terkini.",
    ],
  },
  {
    id: "ppbj", icon: FileText, label: "PPBJ \u2014 Permintaan Pengadaan", path: "/ppbj", roles: ["Semua peran"],
    purpose: "Mengajukan permintaan pengadaan barang & jasa.",
    steps: [
      "Buka menu PPBJ, klik 'Tambah'.",
      "Isi unit kerja, kegiatan, tanggal, dan rincian item (nama, qty, harga).",
      "Periksa total yang terhitung otomatis.",
      "Klik Simpan (draft) atau Ajukan agar masuk proses persetujuan.",
    ],
  },
  {
    id: "pum", icon: Wallet, label: "PUM \u2014 Permohonan Uang Muka", path: "/pum", roles: ["Semua peran"],
    purpose: "Mengajukan uang muka untuk kegiatan yang telah disetujui.",
    steps: [
      "Buka menu PUM, klik 'Tambah'.",
      "Isi keterangan, unit kerja, dan nilai uang muka yang diminta.",
      "Lampirkan rincian penggunaan bila diperlukan.",
      "Ajukan untuk ditinjau Approver/Keuangan.",
    ],
  },
  {
    id: "pp", icon: Receipt, label: "PP \u2014 Permohonan Pembayaran", path: "/pp", roles: ["Semua peran"],
    purpose: "Mengajukan pembayaran kepada pihak ketiga/vendor.",
    steps: [
      "Buka menu PP, klik 'Tambah'.",
      "Isi penerima, keterangan, dan rincian nilai pembayaran.",
      "Periksa perhitungan pajak bila berlaku (mengikuti Pengaturan Pajak).",
      "Ajukan untuk diproses.",
    ],
  },
  {
    id: "ptum", icon: ClipboardCheck, label: "PTUM \u2014 Pertanggungjawaban UM", path: "/ptum", roles: ["Semua peran"],
    purpose: "Melaporkan penggunaan uang muka (PUM) yang telah dicairkan.",
    steps: [
      "Buka menu PTUM, klik 'Tambah'.",
      "Kaitkan dengan PUM terkait, lalu rinci realisasi penggunaan.",
      "Sistem menghitung selisih (sisa/kelebihan) uang muka.",
      "Ajukan untuk diverifikasi Keuangan.",
    ],
  },
  {
    id: "kaskecil", icon: Coins, label: "Kas Kecil", path: "/kaskecil", roles: ["Semua peran"],
    purpose: "Mengajukan penggunaan/pengisian kas kecil.",
    steps: [
      "Buka menu Kas Kecil, klik 'Tambah'.",
      "Isi keterangan pengeluaran dan nominalnya.",
      "Ajukan untuk persetujuan.",
    ],
  },
  {
    id: "nrp", icon: ReceiptText, label: "NRP \u2014 No Receipt Payment", path: "/nrp", roles: ["Semua peran"],
    purpose: "Mencatat pembayaran tanpa kuitansi/bukti formal.",
    steps: [
      "Buka menu NRP, klik 'Tambah'.",
      "Isi tujuan pembayaran, keterangan, dan nilainya.",
      "Ajukan untuk ditinjau.",
    ],
  },
  {
    id: "jurnal", icon: BookOpen, label: "Jurnal Umum", path: "/jurnal", roles: ["Admin", "Keuangan", "Approver"],
    purpose: "Mengubah dokumen yang disetujui menjadi jurnal akuntansi siap ekspor Accurate.",
    steps: [
      "Buka menu Jurnal Umum.",
      "Pilih dokumen yang telah disetujui untuk dijurnal.",
      "Periksa akun debit/kredit sesuai Master Akun (COA).",
      "Ekspor jurnal untuk diunggah ke Accurate.",
    ],
  },
  {
    id: "anggaran", icon: PiggyBank, label: "Anggaran Bulanan", path: "/anggaran", roles: ["Semua peran"],
    purpose: "Memantau Pagu vs Realisasi per unit kerja dan mengekspor rekap.",
    steps: [
      "Buka menu Anggaran Bulanan.",
      "Tab 'Bulanan': pilih periode untuk melihat pagu, realisasi, sisa, dan serapan per unit.",
      "Klik 'Export Excel' untuk rekap satu bulan, atau 'Rentang' untuk beberapa bulan sekaligus.",
      "Tab 'Tahunan': lihat tren 12 bulan & 'Export Excel' rekap tahunan untuk rapat evaluasi.",
    ],
    tip: "File Excel sudah dilengkapi kop/logo, grafik, dan kolom tanda tangan \u2014 siap dicetak & ditandatangani.",
  },
  {
    id: "pajak", icon: Percent, label: "Pengaturan Pajak", path: "/pajak", roles: ["Admin", "Keuangan"],
    purpose: "Mengatur tarif & jenis pajak yang dipakai pada perhitungan dokumen.",
    steps: [
      "Buka menu Pengaturan Pajak.",
      "Tambah/ubah tarif (mis. PPN, PPh) sesuai ketentuan.",
      "Simpan \u2014 tarif otomatis dipakai pada modul terkait.",
    ],
  },
  {
    id: "akun", icon: ListTree, label: "Master Akun (COA)", path: "/akun", roles: ["Admin", "Keuangan"],
    purpose: "Mengelola Chart of Accounts sebagai dasar penjurnalan.",
    steps: [
      "Buka menu Master Akun (COA).",
      "Tambah/ubah kode & nama akun sesuai struktur Accurate.",
      "Akun ini menjadi pilihan saat membuat Jurnal Umum.",
    ],
  },
  {
    id: "pengguna", icon: Users, label: "Pengguna & Peran", path: "/pengguna", roles: ["Admin", "Super Admin"],
    purpose: "Mengelola akun pengguna, peran, aktif/nonaktif, dan reset kata sandi.",
    steps: [
      "Buka menu Pengguna.",
      "Tambah pengguna baru & tetapkan peran yang sesuai.",
      "Nonaktifkan akun yang tidak dipakai atau reset kata sandi bila diperlukan.",
    ],
  },
  {
    id: "log", icon: History, label: "Log Aktivitas", path: "/log-aktivitas", roles: ["Admin", "Super Admin"],
    purpose: "Menelusuri jejak audit tindakan akun (buat, nonaktif, reset sandi, dll.).",
    steps: [
      "Buka menu Log Aktivitas.",
      "Telusuri siapa melakukan apa dan kapan.",
      "Gunakan untuk audit & keamanan.",
    ],
  },
];

const STATUSES = [
  { label: "Draft", cls: "bg-slate-100 text-slate-700", desc: "Tersimpan namun belum diajukan. Masih bisa diedit." },
  { label: "Menunggu", cls: "bg-orange-100 text-orange-700", desc: "Sudah diajukan, menunggu tinjauan Approver/Keuangan." },
  { label: "Disetujui", cls: "bg-green-100 text-green-700", desc: "Telah disetujui dan siap diproses lebih lanjut." },
  { label: "Ditolak", cls: "bg-red-100 text-red-700", desc: "Ditolak; periksa catatan dan ajukan perbaikan." },
  { label: "Dijurnal", cls: "bg-blue-100 text-blue-700", desc: "Sudah dibuatkan Jurnal Umum oleh Keuangan." },
];

const FAQ = [
  { q: "Bagaimana cara membuat pengajuan baru?", a: "Pilih modul yang sesuai di sidebar (mis. PPBJ), klik tombol 'Tambah', isi formulir, lalu klik Ajukan." },
  { q: "Kenapa saya tidak melihat menu tertentu?", a: "Menu ditampilkan sesuai peran Anda. Misalnya Jurnal Umum, Pajak, dan Pengguna hanya untuk peran tertentu. Hubungi Admin bila butuh akses." },
  { q: "Apa arti status 'Menunggu'?", a: "Dokumen sudah Anda ajukan dan sedang menunggu ditinjau oleh Approver atau Keuangan." },
  { q: "Bagaimana mengunduh rekap anggaran untuk rapat?", a: "Buka Anggaran Bulanan. Gunakan 'Export Excel' (satu bulan), 'Rentang' (beberapa bulan), atau tab Tahunan untuk rekap 12 bulan." },
  { q: "Saya lupa kata sandi, apa yang harus dilakukan?", a: "Gunakan 'Lupa kata sandi' di halaman login, atau minta Admin melakukan reset kata sandi dari menu Pengguna." },
  { q: "Bagaimana dokumen menjadi jurnal akuntansi?", a: "Setelah dokumen disetujui, Bagian Keuangan membuat Jurnal Umum dan mengekspornya untuk diunggah ke Accurate." },
];

const GLOSSARY = [
  { term: "PPBJ", def: "Permintaan Pengadaan Barang & Jasa." },
  { term: "PUM", def: "Permohonan Uang Muka." },
  { term: "PP", def: "Permohonan Pembayaran." },
  { term: "PTUM", def: "Pertanggungjawaban Uang Muka." },
  { term: "NRP", def: "No Receipt Payment \u2014 pembayaran tanpa kuitansi formal." },
  { term: "COA", def: "Chart of Accounts \u2014 daftar akun akuntansi (Master Akun)." },
  { term: "Pagu", def: "Batas/plafon anggaran yang ditetapkan." },
  { term: "Realisasi", def: "Nilai yang benar-benar terpakai dari anggaran." },
  { term: "Serapan", def: "Persentase realisasi terhadap pagu." },
  { term: "Jurnal Umum", def: "Pencatatan transaksi akuntansi debit-kredit." },
  { term: "Approver", def: "Pihak yang berwenang menyetujui/menolak pengajuan." },
  { term: "Accurate", def: "Software akuntansi tujuan ekspor jurnal." },
];

const TOC = [
  { id: "ikhtisar", label: "Ikhtisar Sistem", icon: Info },
  { id: "alur", label: "Alur Keuangan", icon: Workflow },
  { id: "peran", label: "Peran & Hak Akses", icon: ShieldCheck },
  { id: "modul", label: "Panduan Modul", icon: BookMarked },
  { id: "status", label: "Status Dokumen", icon: ClipboardCheck },
  { id: "faq", label: "FAQ", icon: HelpCircle },
  { id: "glosarium", label: "Glosarium", icon: BookOpen },
];

function scrollToId(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

export default function Panduan() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [openMod, setOpenMod] = useState("ppbj");
  const [openFaq, setOpenFaq] = useState(null);
  const [tour, setTour] = useState(false);

  const query = q.trim().toLowerCase();
  const modules = useMemo(
    () => MODULES.filter((m) => !query || `${m.label} ${m.purpose} ${m.steps.join(" ")}`.toLowerCase().includes(query)),
    [query]
  );
  const faqs = useMemo(
    () => FAQ.filter((f) => !query || `${f.q} ${f.a}`.toLowerCase().includes(query)),
    [query]
  );
  const glossary = useMemo(
    () => GLOSSARY.filter((g) => !query || `${g.term} ${g.def}`.toLowerCase().includes(query)),
    [query]
  );

  return (
    <div className="space-y-6" data-testid="panduan-page">
      {/* Hero */}
      <div className="rounded-2xl bg-[#0d3c45] text-white p-6 lg:p-8 relative overflow-hidden">
        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center gap-5">
          <img src="/logo-icon.png" alt="Logo" className="w-16 h-16 object-contain drop-shadow shrink-0" />
          <div className="flex-1">
            <h1 className="font-heading text-2xl lg:text-3xl font-extrabold">Panduan Pengguna</h1>
            <p className="text-teal-100/80 text-sm mt-1 max-w-2xl">
              Pelajari cara menggunakan Sistem Keuangan PT. Sumber Berdaya Bersama \u2014 dari membuat pengajuan,
              proses persetujuan, penjurnalan, hingga pemantauan anggaran.
            </p>
          </div>
          <button onClick={() => setTour(true)} data-testid="start-tour-btn"
            className="inline-flex items-center gap-2 px-5 py-3 rounded-lg bg-[#f2941f] hover:bg-[#d98014] text-white text-sm font-bold shadow-lg whitespace-nowrap">
            <PlayCircle className="w-5 h-5" /> Mulai Tur Singkat
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
        <input data-testid="panduan-search" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Cari topik, modul, atau istilah\u2026"
          className="w-full pl-10 pr-4 py-3 rounded-lg border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-[#14758a]/30 focus:border-[#14758a]" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* TOC */}
        <aside className="hidden lg:block">
          <nav className="sticky top-20 space-y-1">
            {TOC.map((t) => {
              const Icon = t.icon;
              return (
                <button key={t.id} onClick={() => scrollToId(t.id)}
                  className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm text-slate-600 hover:bg-teal-50 hover:text-[#0d3c45] transition-colors text-left">
                  <Icon className="w-4 h-4 text-[#14758a] shrink-0" /> {t.label}
                </button>
              );
            })}
          </nav>
        </aside>

        {/* Content */}
        <div className="lg:col-span-3 space-y-8">
          {/* Ikhtisar */}
          <section id="ikhtisar" className="bg-white border border-slate-200 rounded-xl shadow-sm p-6">
            <SectionTitle icon={Info}>Ikhtisar Sistem</SectionTitle>
            <p className="text-slate-600 text-sm leading-relaxed">
              Sistem ini membantu seluruh proses administrasi keuangan secara terpusat dan transparan:
              mulai dari pengajuan oleh pemohon, persetujuan bertingkat, hingga pencatatan akuntansi yang siap
              diekspor ke Accurate. Setiap dokumen memiliki jejak status yang jelas sehingga mudah dipantau.
            </p>
            <div className="grid sm:grid-cols-3 gap-3 mt-4">
              {[
                { t: "Terpusat", d: "Semua pengajuan dalam satu sistem." },
                { t: "Transparan", d: "Status & riwayat dokumen jelas." },
                { t: "Rapi", d: "Output jurnal & rekap siap dipakai." },
              ].map((c) => (
                <div key={c.t} className="rounded-lg bg-teal-50/60 border border-teal-100 p-4">
                  <div className="font-heading font-bold text-[#0d3c45]">{c.t}</div>
                  <div className="text-xs text-slate-600 mt-1">{c.d}</div>
                </div>
              ))}
            </div>
          </section>

          {/* Alur */}
          <section id="alur" className="bg-white border border-slate-200 rounded-xl shadow-sm p-6">
            <SectionTitle icon={Workflow}>Alur Keuangan</SectionTitle>
            <div className="flex flex-col md:flex-row md:items-stretch gap-3">
              {FLOW.map((f, idx) => (
                <div key={f.code} className="flex items-center gap-3 md:flex-1">
                  <div className="flex-1 rounded-lg border border-slate-200 p-3 bg-slate-50/60">
                    <div className="inline-flex items-center justify-center px-2 py-0.5 rounded bg-[#14758a] text-white text-[11px] font-bold">{f.code}</div>
                    <div className="font-semibold text-slate-800 text-sm mt-1.5">{f.label}</div>
                    <div className="text-xs text-slate-500 mt-0.5">{f.desc}</div>
                  </div>
                  {idx < FLOW.length - 1 && (
                    <ArrowRight className="w-5 h-5 text-[#f2941f] shrink-0 rotate-90 md:rotate-0" />
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* Peran */}
          <section id="peran" className="bg-white border border-slate-200 rounded-xl shadow-sm p-6">
            <SectionTitle icon={ShieldCheck}>Peran & Hak Akses</SectionTitle>
            <div className="space-y-3">
              {ROLES.map((r) => (
                <div key={r.role} className={`rounded-lg border p-4 ${user?.role === r.role ? "ring-2 ring-[#14758a]/40" : ""}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${r.color}`}>{ROLE_LABELS[r.role]}</span>
                    {user?.role === r.role && <span className="text-[11px] font-semibold text-[#14758a]">(Peran Anda)</span>}
                  </div>
                  <ul className="list-disc list-inside text-sm text-slate-600 space-y-0.5">
                    {r.can.map((c, i) => <li key={i}>{c}</li>)}
                  </ul>
                </div>
              ))}
            </div>
          </section>

          {/* Modul */}
          <section id="modul" className="bg-white border border-slate-200 rounded-xl shadow-sm p-6">
            <SectionTitle icon={BookMarked}>Panduan Modul</SectionTitle>
            {modules.length === 0 && <p className="text-slate-400 text-sm">Tidak ada modul yang cocok dengan pencarian.</p>}
            <div className="space-y-2">
              {modules.map((m) => {
                const Icon = m.icon;
                const isOpen = openMod === m.id;
                return (
                  <div key={m.id} className="border border-slate-200 rounded-lg overflow-hidden">
                    <button onClick={() => setOpenMod(isOpen ? null : m.id)} data-testid={`mod-${m.id}`}
                      className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-50">
                      <div className="w-9 h-9 rounded-lg bg-teal-50 text-[#14758a] flex items-center justify-center shrink-0">
                        <Icon className="w-5 h-5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-slate-800 text-sm">{m.label}</div>
                        <div className="text-xs text-slate-500 truncate">{m.purpose}</div>
                      </div>
                      <ChevronDown className={`w-5 h-5 text-slate-400 shrink-0 transition-transform ${isOpen ? "rotate-180" : ""}`} />
                    </button>
                    {isOpen && (
                      <div className="px-4 pb-4 pt-1">
                        <div className="flex flex-wrap gap-1.5 mb-3">
                          {m.roles.map((r) => (
                            <span key={r} className="inline-flex items-center px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[11px] font-medium">{r}</span>
                          ))}
                        </div>
                        <ol className="list-decimal list-inside text-sm text-slate-600 space-y-1">
                          {m.steps.map((s, i) => <li key={i}>{s}</li>)}
                        </ol>
                        {m.tip && (
                          <div className="mt-3 flex items-start gap-2 text-xs text-[#0d3c45] bg-orange-50 border border-orange-100 rounded-lg p-3">
                            <Info className="w-4 h-4 text-[#f2941f] shrink-0 mt-0.5" /> <span>{m.tip}</span>
                          </div>
                        )}
                        <button onClick={() => nav(m.path)}
                          className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-[#14758a] hover:text-[#0d3c45]">
                          Buka modul <ArrowRight className="w-4 h-4" />
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>

          {/* Status */}
          <section id="status" className="bg-white border border-slate-200 rounded-xl shadow-sm p-6">
            <SectionTitle icon={ClipboardCheck}>Status Dokumen</SectionTitle>
            <div className="space-y-2">
              {STATUSES.map((s) => (
                <div key={s.label} className="flex items-start gap-3 py-1">
                  <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold shrink-0 ${s.cls}`}>{s.label}</span>
                  <span className="text-sm text-slate-600">{s.desc}</span>
                </div>
              ))}
            </div>
          </section>

          {/* FAQ */}
          <section id="faq" className="bg-white border border-slate-200 rounded-xl shadow-sm p-6">
            <SectionTitle icon={HelpCircle}>Pertanyaan Umum (FAQ)</SectionTitle>
            {faqs.length === 0 && <p className="text-slate-400 text-sm">Tidak ada FAQ yang cocok dengan pencarian.</p>}
            <div className="divide-y divide-slate-100">
              {faqs.map((f, i) => {
                const isOpen = openFaq === i;
                return (
                  <div key={i}>
                    <button onClick={() => setOpenFaq(isOpen ? null : i)}
                      className="w-full flex items-center justify-between gap-3 py-3 text-left">
                      <span className="text-sm font-semibold text-slate-800">{f.q}</span>
                      <ChevronDown className={`w-5 h-5 text-slate-400 shrink-0 transition-transform ${isOpen ? "rotate-180" : ""}`} />
                    </button>
                    {isOpen && <p className="text-sm text-slate-600 pb-3 -mt-1">{f.a}</p>}
                  </div>
                );
              })}
            </div>
          </section>

          {/* Glosarium */}
          <section id="glosarium" className="bg-white border border-slate-200 rounded-xl shadow-sm p-6">
            <SectionTitle icon={BookOpen}>Glosarium</SectionTitle>
            {glossary.length === 0 && <p className="text-slate-400 text-sm">Tidak ada istilah yang cocok dengan pencarian.</p>}
            <div className="grid sm:grid-cols-2 gap-x-6 gap-y-2">
              {glossary.map((g) => (
                <div key={g.term} className="flex gap-2 text-sm py-1 border-b border-slate-50">
                  <span className="font-bold text-[#0d3c45] min-w-[90px]">{g.term}</span>
                  <span className="text-slate-600">{g.def}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>

      {tour && <TourModal onClose={() => setTour(false)} userName={user?.name} />}
    </div>
  );
}

function SectionTitle({ icon: Icon, children }) {
  return (
    <h2 className="flex items-center gap-2.5 font-heading text-lg font-bold text-slate-900 mb-4">
      <span className="w-8 h-8 rounded-lg bg-[#0d3c45] text-white flex items-center justify-center">
        <Icon className="w-4.5 h-4.5" />
      </span>
      {children}
    </h2>
  );
}
