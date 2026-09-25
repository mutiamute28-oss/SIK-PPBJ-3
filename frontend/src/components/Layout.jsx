import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  LayoutDashboard, FileText, Wallet, Receipt, ClipboardCheck,
  BookOpen, Percent, ListTree, Users, LogOut, Menu, X, Coins, ReceiptText, PiggyBank, History,
  PanelLeftClose, PanelLeftOpen, LifeBuoy,
} from "lucide-react";
import { useState } from "react";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, roles: ["admin", "keuangan", "approver", "user"] },
  { to: "/ppbj", label: "PPBJ", desc: "Permintaan Pengadaan", icon: FileText, roles: ["admin", "keuangan", "approver", "user"] },
  { to: "/pum", label: "PUM", desc: "Permohonan Uang Muka", icon: Wallet, roles: ["admin", "keuangan", "approver", "user"] },
  { to: "/pp", label: "PP", desc: "Permohonan Pembayaran", icon: Receipt, roles: ["admin", "keuangan", "approver", "user"] },
  { to: "/ptum", label: "PTUM", desc: "Pertanggungjawaban UM", icon: ClipboardCheck, roles: ["admin", "keuangan", "approver", "user"] },
  { to: "/kaskecil", label: "Kas Kecil", desc: "Permintaan Kas Kecil", icon: Coins, roles: ["admin", "keuangan", "approver", "user"] },
  { to: "/nrp", label: "NRP", desc: "No Receipt Payment", icon: ReceiptText, roles: ["admin", "keuangan", "approver", "user"] },
  { to: "/jurnal", label: "Jurnal Umum", desc: "Output Accurate", icon: BookOpen, roles: ["admin", "keuangan", "approver"] },
  { to: "/anggaran", label: "Anggaran Bulanan", desc: "Pagu vs Realisasi", icon: PiggyBank, roles: ["admin", "keuangan", "approver", "user"] },
  { to: "/pajak", label: "Pengaturan Pajak", icon: Percent, roles: ["admin", "keuangan"] },
  { to: "/akun", label: "Master Akun (COA)", icon: ListTree, roles: ["admin", "keuangan"] },
  { to: "/pengguna", label: "Pengguna", icon: Users, roles: ["admin"] },
  { to: "/log-aktivitas", label: "Log Aktivitas", desc: "Jejak Audit Akun", icon: History, roles: ["admin"] },
  { to: "/panduan", label: "Panduan", desc: "Panduan Pengguna", icon: LifeBuoy, roles: ["admin", "keuangan", "approver", "user"] },
];

const ROLE_LABELS = {
  superadmin: "Super Admin",
  admin: "Admin",
  keuangan: "Keuangan",
  approver: "Approver",
  user: "User (Pemohon)",
};

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem("sidebar-collapsed") === "1"; } catch { return false; }
  });
  const toggleCollapsed = () => setCollapsed((c) => {
    const next = !c;
    try { localStorage.setItem("sidebar-collapsed", next ? "1" : "0"); } catch {}
    return next;
  });
  const role = user?.role || "user";
  const items = NAV.filter((n) => role === "superadmin" || n.roles.includes(role));

  const SideContent = ({ mini = false }) => (
    <>
      <div className={`flex items-center gap-3 h-16 border-b border-white/10 ${mini ? "justify-center px-2" : "px-5"}`}>
        <img src="/logo-icon.png" alt="Logo" className="w-10 h-10 object-contain drop-shadow shrink-0" />
        {!mini && (
          <div className="leading-tight">
            <div className="text-white font-heading font-extrabold text-sm tracking-wide">PERMINTAAN KEUANGAN</div>
            <div className="text-teal-200/80 text-[9px] font-medium">SISTEM PENGAJUAN BARANG & JASA</div>
          </div>
        )}
      </div>
      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
        {items.map((n) => {
          const Icon = n.icon;
          return (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} onClick={() => setOpen(false)}
              title={mini ? n.label : undefined}
              data-testid={`nav-${n.to.replace("/", "") || "dashboard"}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${mini ? "justify-center" : ""} ${
                  isActive ? "bg-[#14758a] text-white font-semibold shadow" : "text-teal-100/80 hover:bg-white/10 hover:text-white"
                }`}>
              <Icon className="w-[18px] h-[18px] shrink-0" />
              {!mini && (
                <span className="flex-1">
                  {n.label}
                  {n.desc && <span className="block text-[10px] font-normal opacity-60">{n.desc}</span>}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>
      <div className={`border-t border-white/10 ${mini ? "p-2" : "p-3"}`}>
        {!mini && (
          <div className="px-3 py-2 mb-2">
            <div className="text-white text-sm font-semibold truncate">{user?.name}</div>
            <div className="text-teal-200/70 text-xs">{ROLE_LABELS[role] || role}</div>
          </div>
        )}
        <button data-testid="logout-button" onClick={() => { logout(); nav("/login"); }}
          title={mini ? "Keluar" : undefined}
          className={`flex items-center gap-2 w-full px-3 py-2.5 rounded-lg text-sm text-red-200 hover:bg-red-500/20 transition-colors ${mini ? "justify-center" : ""}`}>
          <LogOut className="w-[18px] h-[18px]" /> {!mini && "Keluar"}
        </button>
      </div>
    </>
  );

  return (
    <div className="min-h-screen flex bg-[#f8fafc]">
      <aside className={`hidden lg:flex flex-col bg-[#0d3c45] fixed inset-y-0 left-0 z-30 transition-[width] duration-300 ${collapsed ? "w-[76px]" : "w-[260px]"}`}>
        <SideContent mini={collapsed} />
      </aside>

      {open && (
        <div className="lg:hidden fixed inset-0 z-40 flex">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <aside className="relative flex flex-col w-[260px] bg-[#0d3c45]">
            <SideContent mini={false} />
          </aside>
        </div>
      )}

      <div className={`flex-1 min-w-0 transition-[margin] duration-300 ${collapsed ? "lg:ml-[76px]" : "lg:ml-[260px]"}`}>
        <header className="h-16 bg-white border-b border-slate-200 flex items-center px-4 md:px-6 sticky top-0 z-20">
          <button className="lg:hidden mr-3 p-2 text-slate-600" onClick={() => setOpen(!open)} data-testid="menu-toggle">
            {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
          <button className="hidden lg:inline-flex mr-3 p-2 text-slate-500 hover:text-[#14758a] hover:bg-slate-100 rounded-md transition-colors"
            onClick={toggleCollapsed} data-testid="sidebar-collapse-toggle"
            title={collapsed ? "Perbesar menu" : "Perkecil menu"}
            aria-label={collapsed ? "Perbesar menu" : "Perkecil menu"}>
            {collapsed ? <PanelLeftOpen className="w-5 h-5" /> : <PanelLeftClose className="w-5 h-5" />}
          </button>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider hidden sm:block">PT. SUMBER BERDAYA BERSAMA</span>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <div className="text-right hidden sm:block">
              <div className="text-sm font-semibold text-slate-800">{user?.name}</div>
              <div className="text-xs text-slate-500">{user?.email}</div>
            </div>
            <div className="w-9 h-9 rounded-full bg-[#14758a] text-white flex items-center justify-center font-bold text-sm">
              {(user?.name || "?").charAt(0).toUpperCase()}
            </div>
          </div>
        </header>
        <main className="p-4 md:p-6 lg:p-8 max-w-[1400px] mx-auto animate-fade-up">{children}</main>
      </div>
    </div>
  );
}
