import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  X, ArrowLeft, ArrowRight, CheckCircle2, BookOpen, LayoutDashboard,
  FilePlus2, ThumbsUp, BookMarked, PiggyBank, LifeBuoy,
} from "lucide-react";

const STEPS = [
  {
    logo: true,
    title: "Selamat datang!",
    body: "Kenali Sistem Keuangan PT. Sumber Berdaya Bersama dalam waktu singkat. Tur ini menjelaskan alur utama: membuat pengajuan, proses persetujuan, penjurnalan, hingga pemantauan anggaran.",
  },
  {
    icon: LayoutDashboard,
    title: "Dashboard",
    body: "Halaman utama menampilkan ringkasan: jumlah pengajuan per jenis, yang menunggu persetujuan, yang sudah disetujui, jurnal yang dibuat, serta total nilai pengajuan. Tabel 'Pengajuan Terbaru' membantu Anda memantau aktivitas terkini.",
  },
  {
    icon: FilePlus2,
    title: "Membuat Pengajuan",
    body: "Pilih modul di sidebar sesuai kebutuhan \u2014 PPBJ (pengadaan), PUM (uang muka), PP (pembayaran), PTUM (pertanggungjawaban), Kas Kecil, atau NRP. Klik 'Tambah', isi formulir, lalu Simpan atau Ajukan untuk diproses.",
  },
  {
    icon: ThumbsUp,
    title: "Alur Persetujuan",
    body: "Setiap dokumen berjalan melalui status: Draft \u2192 Menunggu \u2192 Disetujui/Ditolak. Approver meninjau dan menyetujui pengajuan. Anda dapat memantau status dokumen kapan saja dari daftar tiap modul.",
  },
  {
    icon: BookMarked,
    title: "Jurnal Umum",
    body: "Bagian Keuangan mengubah dokumen yang disetujui menjadi Jurnal Umum yang siap diekspor ke Accurate. Ini menjaga pencatatan akuntansi tetap rapi dan konsisten.",
  },
  {
    icon: PiggyBank,
    title: "Anggaran Bulanan",
    body: "Pantau Pagu vs Realisasi per unit kerja. Anda bisa mengunduh rekap Excel bulanan, rentang beberapa bulan, atau tahunan \u2014 lengkap dengan grafik & kolom tanda tangan untuk rapat manajemen.",
  },
  {
    icon: LifeBuoy,
    title: "Butuh bantuan?",
    body: "Buka menu 'Panduan' di sidebar kapan saja untuk membaca langkah lengkap tiap modul, penjelasan peran, status dokumen, FAQ, dan glosarium istilah.",
    last: true,
  },
];

export default function TourModal({ onClose, userName }) {
  const [i, setI] = useState(0);
  const nav = useNavigate();
  const step = STEPS[i];
  const Icon = step.icon;
  const isLast = i === STEPS.length - 1;

  const finish = () => {
    try { localStorage.setItem("tour-seen", "1"); } catch (e) { /* ignore */ }
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={finish} />
      <div className="relative w-full max-w-lg bg-white rounded-2xl shadow-2xl overflow-hidden animate-fade-up" data-testid="tour-modal">
        <div className="bg-[#0d3c45] px-6 pt-6 pb-8 relative">
          <button onClick={finish} data-testid="tour-close"
            className="absolute top-3 right-3 p-1.5 rounded-md text-teal-100/70 hover:text-white hover:bg-white/10">
            <X className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-xl bg-white/10 flex items-center justify-center shrink-0">
              {step.logo
                ? <img src="/logo-icon.png" alt="Logo" className="w-11 h-11 object-contain" />
                : Icon ? <Icon className="w-7 h-7 text-[#f2941f]" /> : null}
            </div>
            <div>
              <div className="text-teal-200/70 text-[11px] font-semibold uppercase tracking-widest">
                Langkah {i + 1} dari {STEPS.length}
              </div>
              <h3 className="text-white font-heading font-extrabold text-xl leading-tight">
                {i === 0 && userName ? `Halo, ${userName}!` : step.title}
              </h3>
            </div>
          </div>
        </div>

        <div className="px-6 py-6">
          {i === 0 && userName && (
            <p className="text-slate-800 font-semibold mb-2">{step.title}</p>
          )}
          <p className="text-slate-600 text-sm leading-relaxed">{step.body}</p>
        </div>

        <div className="px-6 pb-6 flex items-center justify-between gap-3">
          <div className="flex items-center gap-1.5">
            {STEPS.map((_, idx) => (
              <span key={idx}
                className={`h-1.5 rounded-full transition-all ${idx === i ? "w-5 bg-[#f2941f]" : "w-1.5 bg-slate-300"}`} />
            ))}
          </div>
          <div className="flex items-center gap-2">
            {i > 0 && (
              <button onClick={() => setI(i - 1)} data-testid="tour-prev"
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md border border-slate-300 text-slate-700 text-sm font-semibold hover:bg-slate-50">
                <ArrowLeft className="w-4 h-4" /> Kembali
              </button>
            )}
            {!isLast && (
              <button onClick={() => setI(i + 1)} data-testid="tour-next"
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-[#14758a] hover:bg-[#0d3c45] text-white text-sm font-semibold">
                Lanjut <ArrowRight className="w-4 h-4" />
              </button>
            )}
            {isLast && (
              <>
                <button onClick={() => { finish(); nav("/panduan"); }} data-testid="tour-open-guide"
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md border border-[#14758a] text-[#0d3c45] text-sm font-semibold hover:bg-teal-50">
                  <BookOpen className="w-4 h-4" /> Panduan Lengkap
                </button>
                <button onClick={finish} data-testid="tour-finish"
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-[#f2941f] hover:bg-[#d98014] text-white text-sm font-semibold">
                  <CheckCircle2 className="w-4 h-4" /> Selesai
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
