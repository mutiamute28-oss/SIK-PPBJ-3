export default function Splash({ label = "Memuat…" }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-5 bg-[#0d3c45]">
      <img
        src="/logo-icon.png"
        alt="Permintaan Keuangan"
        className="w-20 h-20 object-contain drop-shadow-lg animate-pulse"
      />
      <div className="text-center">
        <div className="text-white font-heading font-extrabold tracking-wide text-lg">PERMINTAAN KEUANGAN</div>
        <div className="text-teal-200/70 text-[10px] font-semibold tracking-[2px] mt-0.5">SISTEM PENGAJUAN BARANG & JASA</div>
      </div>
      <div className="w-40 h-[3px] rounded-full bg-white/15 overflow-hidden">
        <div className="h-full w-2/5 rounded-full bg-[#f2941f] animate-[splash-slide_1.1s_ease-in-out_infinite]" />
      </div>
      <span className="sr-only">{label}</span>
    </div>
  );
}
