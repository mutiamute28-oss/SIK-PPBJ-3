import { rupiahNum } from "@/lib/api";

const TITLES = {
  PPBJ: "PERMINTAAN PENGADAAN BARANG & JASA",
  PUM: "PERMOHONAN UANG MUKA",
  PP: "PERMOHONAN PEMBAYARAN",
  PTUM: "PERTANGGUNGJAWABAN UANG MUKA",
  KASKECIL: "PERMINTAAN KAS KECIL",
  NRP: "NO RECEIPT PAYMENT",
};

const esc = (s) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

export function printDocument(doc) {
  const items = doc.items || [];
  const itemsRows = items.length
    ? items.map((it, i) => `<tr>
        <td style="text-align:center">${i + 1}</td>
        <td>${esc(it.uraian)}</td>
        <td style="text-align:right">${rupiahNum(it.kuantitas)}</td>
        <td style="text-align:center">${esc(it.satuan)}</td>
        <td style="text-align:right">${rupiahNum(it.harga_estimasi)}</td>
        <td style="text-align:right">${rupiahNum(it.total)}</td></tr>`).join("")
    : `<tr><td colspan="6" style="text-align:center;color:#888">Tidak ada rincian item</td></tr>`;

  const taxBlock = ["PP", "PTUM", "KASKECIL"].includes(doc.doc_type)
    ? `<div class="box"><b>Aspek Pajak:</b>
        DPP: Rp ${rupiahNum(doc.dpp || doc.total)} &nbsp;|&nbsp;
        PPN: ${doc.ppn_enabled ? "Ya" : "Tidak"} &nbsp;|&nbsp;
        PPh: ${esc(doc.pph_code || "Tanpa PPh")} &nbsp;|&nbsp;
        Faktur Pajak: ${esc(doc.faktur_pajak || "-")}</div>`
    : "";

  const approvals = (doc.approvals || []).map((a) => `
    <td style="width:${100 / Math.max(doc.approvals.length, 1)}%">
      <div class="ap-role">${esc(a.role_label)}</div>
      <div class="ap-sign">${a.status === "approved" ? "✓ Disetujui" : a.status === "rejected" ? "✗ Ditolak" : ""}</div>
      <div class="ap-name">${esc(a.name || "(............................)")}</div>
      <div class="ap-date">${a.at ? new Date(a.at).toLocaleDateString("id-ID") : "Tgl. ................"}</div>
    </td>`).join("");

  const attach = (doc.attachments || []).filter((x) => x.name || x.link);
  const attachBlock = attach.length
    ? `<div class="box"><b>Lampiran Bukti:</b><ol style="margin:4px 0 0 18px;padding:0">${attach.map((x) => `<li>${esc(x.name)}${x.link ? ` — <span style="color:#14758a">${esc(x.link)}</span>` : ""}</li>`).join("")}</ol></div>`
    : "";

  const html = `<!doctype html><html><head><meta charset="utf-8"><title>${esc(doc.no)}</title>
  <style>
    @page { size: A4; margin: 15mm; }
    * { font-family: Arial, sans-serif; box-sizing: border-box; }
    body { color: #1a1a1a; font-size: 12px; margin: 0; }
    .kop { display:flex; align-items:center; gap:14px; border-bottom:3px solid #14758a; padding-bottom:10px; }
    .kop img { width:52px; height:52px; object-fit:contain; }
    .kop h1 { margin:0; font-size:17px; font-weight:800; letter-spacing:.5px; color:#0d3c45; }
    .kop .kop-sub { margin:1px 0 0; font-size:9px; font-weight:700; letter-spacing:1px; color:#14758a; }
    .kop .kop-co { margin:3px 0 0; font-size:10px; color:#555; }
    .title { text-align:center; margin:14px 0 6px; }
    .title h2 { margin:0; font-size:15px; letter-spacing:.5px; color:#0d3c45; }
    .title .no { font-size:11px; color:#666; font-family:monospace; }
    table { width:100%; border-collapse:collapse; margin-top:8px; }
    .info td { padding:3px 6px; vertical-align:top; }
    .info .lbl { color:#666; width:130px; }
    .items th, .items td { border:1px solid #bbb; padding:5px 7px; font-size:11px; }
    .items th { background:#eef8f9; color:#0d3c45; text-align:left; }
    .total-row td { font-weight:bold; background:#f5f5f5; }
    .box { border:1px solid #ddd; background:#fafafa; padding:8px 10px; margin-top:10px; font-size:11px; border-radius:4px; }
    .appr { margin-top:22px; }
    .appr td { border:1px solid #ccc; text-align:center; padding:6px 4px; vertical-align:top; height:70px; }
    .ap-role { font-size:10px; font-weight:bold; color:#0d3c45; }
    .ap-sign { font-size:10px; color:green; margin-top:20px; }
    .ap-name { font-size:11px; font-weight:600; border-top:1px solid #999; margin:4px 6px 0; padding-top:2px; }
    .ap-date { font-size:9px; color:#777; }
    .foot { margin-top:14px; font-size:9px; color:#999; text-align:right; }
  </style></head><body>
    <div class="kop">
      <img src="/logo-icon.png" />
      <div>
        <h1>PERMINTAAN KEUANGAN</h1>
        <p class="kop-sub">SISTEM PENGAJUAN BARANG &amp; JASA</p>
        <p class="kop-co">PT. Sumber Berdaya Bersama · Formulir Administrasi Keuangan</p>
      </div>
    </div>
    <div class="title"><h2>${esc(TITLES[doc.doc_type] || doc.doc_type)}</h2><div class="no">No: ${esc(doc.no)}</div></div>
    <table class="info">
      <tr><td class="lbl">Entitas / Unit</td><td>: ${esc(doc.entitas)} ${doc.unit_kerja ? "/ " + esc(doc.unit_kerja) : ""}</td>
          <td class="lbl">Tanggal</td><td>: ${esc(doc.tanggal || "-")}</td></tr>
      <tr><td class="lbl">Kegiatan / Proyek</td><td>: ${esc(doc.kegiatan || "-")}</td>
          <td class="lbl">Status Anggaran</td><td>: ${esc(doc.anggaran_status || "-")}</td></tr>
      <tr><td class="lbl">Supplier / Penerima</td><td>: ${esc(doc.supplier || "-")}</td>
          <td class="lbl">Nilai Total</td><td>: <b>Rp ${rupiahNum(doc.total)}</b></td></tr>
    </table>
    <table class="items">
      <thead><tr><th style="width:30px">No</th><th>Uraian Spesifikasi Barang / Jasa</th><th style="width:50px">Qty</th><th style="width:50px">Satuan</th><th style="width:110px">Harga</th><th style="width:120px">Total</th></tr></thead>
      <tbody>${itemsRows}</tbody>
      <tfoot><tr class="total-row"><td colspan="5" style="text-align:right;border:1px solid #bbb;padding:5px 7px">TOTAL</td><td style="text-align:right;border:1px solid #bbb;padding:5px 7px">Rp ${rupiahNum(doc.total)}</td></tr></tfoot>
    </table>
    ${taxBlock}
    ${doc.keterangan ? `<div class="box"><b>Keterangan / Alasan:</b> ${esc(doc.keterangan)}</div>` : ""}
    ${attachBlock}
    <table class="appr"><tr>${approvals}</tr></table>
    <div class="foot">No. Form: FM.05.18.02 rev 01 · Dicetak ${new Date().toLocaleString("id-ID")}</div>
    <script>window.onload=function(){window.print();}</script>
  </body></html>`;

  const w = window.open("", "_blank");
  if (!w) { alert("Popup diblokir. Izinkan popup untuk mencetak."); return; }
  w.document.open();
  w.document.write(html);
  w.document.close();
}
