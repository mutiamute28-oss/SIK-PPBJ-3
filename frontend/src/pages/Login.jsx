import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth, formatApiErrorDetail } from "@/context/AuthContext";
import { toast } from "sonner";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true); setError("");
    try {
      await login(email, password);
      toast.success("Selamat datang!");
      nav("/");
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex">
      <div className="hidden lg:flex flex-col justify-between w-1/2 bg-[#0d3c45] p-12 relative overflow-hidden">
        <div className="absolute -right-20 -top-20 w-96 h-96 rounded-full bg-[#14758a]/30 blur-3xl" />
        <div className="absolute right-10 bottom-10 w-72 h-72 rounded-full bg-[#f2941f]/10 blur-3xl" />
        <div className="flex items-center gap-3 relative z-10">
          <img src="/logo-icon.png" alt="Logo" className="w-14 h-14 object-contain drop-shadow" />
          <div className="text-white font-heading font-extrabold text-xl">PERMINTAAN KEUANGAN</div>
        </div>
        <div className="relative z-10">
          <h1 className="text-white font-heading text-4xl font-extrabold leading-tight mb-4">
            Sistem Keuangan<br />PT. Sumber Berdaya Bersama
          </h1>
          <p className="text-teal-100/80 text-base max-w-md">
            Kelola PPBJ, Uang Muka, Pembayaran & Pertanggungjawaban — otomatis menghasilkan
            <span className="text-[#f2941f] font-semibold"> Jurnal Umum </span>
            siap input ke Accurate Online, lengkap rincian pajak Indonesia.
          </p>
        </div>
        <div className="text-teal-200/50 text-xs relative z-10">© 2026 PT. SBB · Formulir Administrasi Keuangan</div>
      </div>

      <div className="flex-1 flex items-center justify-center p-6 bg-[#f8fafc]">
        <div className="w-full max-w-md">
          <div className="lg:hidden flex items-center gap-3 mb-8 justify-center">
            <img src="/logo-icon.png" alt="Logo" className="w-12 h-12 object-contain" />
            <div className="font-heading font-extrabold text-xl text-[#0d3c45]">PERMINTAAN KEUANGAN</div>
          </div>
          <h2 className="font-heading text-2xl font-bold text-slate-900 mb-1">Masuk ke Akun</h2>
          <p className="text-slate-500 text-sm mb-6">Silakan masuk untuk melanjutkan.</p>

          {error && <div data-testid="login-error" className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">{error}</div>}

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-1.5">Email</label>
              <input data-testid="login-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-white border border-slate-300 rounded-md px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#14758a] focus:border-[#14758a]"
                placeholder="email@perusahaan.co.id" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-1.5">Kata Sandi</label>
              <input data-testid="login-password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-white border border-slate-300 rounded-md px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#14758a] focus:border-[#14758a]"
                placeholder="••••••••" />
            </div>
            <button data-testid="login-submit" type="submit" disabled={loading}
              className="w-full bg-[#14758a] hover:bg-[#106071] text-white font-semibold py-2.5 rounded-md transition-colors disabled:opacity-60">
              {loading ? "Memproses…" : "Masuk"}
            </button>
          </form>
          <div className="mt-4 text-center">
            <Link to="/forgot-password" className="text-sm text-[#14758a] hover:underline">Lupa kata sandi?</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
