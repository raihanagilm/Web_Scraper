/* Edtekno Lead Scraper — frontend logic (vanilla JS) */
"use strict";

const $ = (sel) => document.querySelector(sel);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

const STATUS_OPTS = ["New", "Contacted", "Follow Up", "Deal", "Rejected"];

// ---- Sound effects (diputar saat job selesai / gagal) ----
const sfx = {
  done: new Audio("/audio/anjir-wibu.mp3"),
  fail: new Audio("/audio/faaah.mp3"),
};
sfx.done.preload = "auto";
sfx.fail.preload = "auto";

function unlockAudio() {
  [sfx.done, sfx.fail].forEach((a) => {
    try {
      a.muted = true;
      a.currentTime = 0;
      a.play().then(() => { a.pause(); a.muted = false; }).catch(() => { a.muted = false; });
    } catch (_) {}
  });
}

// Status job terakhir yang terlihat (untuk deteksi transisi terminal utk sound)
const jobPrevStatus = new Map();

function playSound(kind) {
  const a = sfx[kind];
  if (!a) return;
  try {
    a.muted = false;
    a.currentTime = 0;
    a.play().catch(() => {});
  } catch (_) {}
}

// ---- API helper ----
async function api(path, opts = {}) {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: opts.body && !(opts.body instanceof FormData)
      ? { "Content-Type": "application/json" }
      : undefined,
    ...opts,
    body: opts.body && !(opts.body instanceof FormData) ? JSON.stringify(opts.body) : opts.body,
  });
  if (res.status === 401) {
    showLogin();
    throw new Error("Not authenticated");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.headers.get("content-type")?.includes("json") ? res.json() : res;
}

// ---- Auth & view switching ----
function showLogin() {
  $("#login-view").classList.remove("hidden");
  $("#app-view").classList.add("hidden");
  stopPolling();
}

function showApp() {
  $("#login-view").classList.add("hidden");
  $("#app-view").classList.remove("hidden");
}

async function bootstrap() {
  try {
    const me = await api("/api/auth/me");
    $("#user-name").textContent = me.username || "user";
    showApp();
    navigate(location.hash.replace("#", "") || "dashboard");
  } catch (_) {
    showLogin();
  }
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("#login-error");
  err.classList.add("hidden");
  try {
    const r = await api("/api/auth/login", {
      method: "POST",
      body: {
        username: $("#login-username").value.trim(),
        password: $("#login-password").value,
      },
    });
    $("#user-name").textContent = r.user?.username || "user";
    showApp();
    navigate("dashboard");
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
  }
});

$("#btn-logout").addEventListener("click", async () => {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (_) {}
  showLogin();
});

// ---- Router ----
function navigate(page) {
  document.querySelectorAll(".page").forEach((p) => p.classList.add("hidden"));
  const el = $(`#page-${page}`) || $("#page-dashboard");
  el.classList.remove("hidden");
  document.querySelectorAll(".nav-item").forEach((b) =>
    b.classList.toggle("active", b.dataset.page === page)
  );
  location.hash = page;
  if (page === "dashboard") loadDashboard();
  if (page === "scrape") { loadJobs(); loadBrowserStatus(); loadEnrichmentMeta(); }
  if (page === "enrichment") { loadEnrichmentMeta(); loadEnrichmentJobs(); }
  if (page === "results") { loadFilters(); loadLeads(); }
  if (page === "dedup") loadDedup();
}

document.querySelectorAll(".nav-item").forEach((b) =>
  b.addEventListener("click", () => navigate(b.dataset.page))
);
window.addEventListener("hashchange", () => {
  const page = location.hash.replace("#", "");
  if (document.body.contains($(`#page-${page}`))) navigate(page);
});

// ---- Dashboard ----
async function loadDashboard() {
  const s = await api("/api/stats");
  const list = (obj) =>
    Object.entries(obj)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([k, v]) => `<li><span>${esc(k || "-")}</span><span class="val">${v}</span></li>`)
      .join("");

  $("#stats-cards").innerHTML = `
    <div class="stat-card"><div class="num">${s.total_leads}</div><div class="lbl">Total Leads</div></div>
    <div class="stat-card"><div class="num">${Object.keys(s.by_source).length}</div><div class="lbl">Sumber Data</div></div>
    <div class="stat-card"><div class="num">${Object.keys(s.by_city).length}</div><div class="lbl">Kota Terjangkau</div></div>`;

  $("#stats-source").innerHTML = list(s.by_source) || `<li class="muted">Belum ada data</li>`;
  $("#stats-status").innerHTML = list(s.by_status) || `<li class="muted">Belum ada data</li>`;
  $("#stats-city").innerHTML = list(s.by_city) || `<li class="muted">Belum ada data</li>`;
}

// ---- Polling job progress ----
let pollTimer = null;

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    if (!$("#page-scrape").classList.contains("hidden")) loadJobs(true);
    if (!$("#page-enrichment").classList.contains("hidden")) loadEnrichmentJobs(true);
  }, 2000);
}

function stopPolling() {
  clearInterval(pollTimer);
  pollTimer = null;
}

// ---- Scrape page ----
const jobSort = { key: "started_at", dir: "desc" };

function renderJobSortIndicators() {
  document.querySelectorAll("#page-scrape th[data-jsort]").forEach((th) => {
    const active = th.dataset.jsort === jobSort.key;
    th.classList.toggle("sorted", active);
    const arrow = th.querySelector(".sort-arrow");
    if (arrow) arrow.textContent = active ? (jobSort.dir === "asc" ? "▲" : "▼") : "";
  });
}

// ---- Scraping (GMaps) ----
$("#btn-start-scrape").addEventListener("click", async () => {
  unlockAudio();
  const msg = $("#scrape-msg");
  msg.classList.add("hidden");
  try {
    const keyword = $("#scrape-keyword").value.trim();
    const city = $("#scrape-city").value.trim();
    if (!keyword) {
      msg.textContent = "Masukkan kata kunci pencarian.";
      msg.style.color = "var(--danger)";
      msg.classList.remove("hidden");
      return;
    }
    const job = await api("/api/scrape", {
      method: "POST",
      body: {
        source: "gmaps",
        category: keyword,
        city: city,
        max_results: parseInt($("#scrape-max").value, 10) || 50,
      },
    });
    addKeywordHistory(keyword); // catat ke Riwayat Kategori (unique)
    msg.textContent = `Scrape GMaps dimulai (${job.id}) — pantau progres di bawah.`;
    msg.classList.remove("hidden");
    startPolling();
    loadJobs();
  } catch (ex) {
    msg.textContent = ex.message;
    msg.style.color = "var(--danger)";
    msg.classList.remove("hidden");
  }
});

// ---- Riwayat Kategori (Quick Fill) ----
// Setiap scrape dijalankan → kata kunci disimpan (unique, case-insensitive,
// terbaru di depan) ke localStorage → chips selalu bisa diklik untuk mengisi input.
const KW_HISTORY_KEY = "edtekno_keyword_history";
const KW_HISTORY_MAX = 16;
// Seed awal agar section tidak kosong saat pertama kali dipakai.
const KW_DEFAULTS = [
  "sekolah", "perusahaan", "umkm", "retail", "restoran", "kafe",
  "vendor pengadaan", "kontraktor", "toko elektronik", "rumah sakit", "klinik", "hotel",
];

function loadKeywordHistory() {
  try {
    const raw = JSON.parse(localStorage.getItem(KW_HISTORY_KEY) || "null");
    if (Array.isArray(raw)) return raw.filter((k) => typeof k === "string" && k.trim());
  } catch (_) { /* storage rusak → pakai default */ }
  return null;
}

function saveKeywordHistory(list) {
  try { localStorage.setItem(KW_HISTORY_KEY, JSON.stringify(list)); } catch (_) {}
}

function addKeywordHistory(keyword) {
  const kw = String(keyword || "").trim();
  if (!kw) return;
  let list = loadKeywordHistory() || [...KW_DEFAULTS];
  // Filter unique (case-insensitive) + taruh terbaru di depan + batasi panjang
  list = [kw, ...list.filter((k) => k.toLowerCase() !== kw.toLowerCase())].slice(0, KW_HISTORY_MAX);
  saveKeywordHistory(list);
  renderKeywordChips();
}

function renderKeywordChips() {
  const wrap = $("#keyword-history");
  if (!wrap) return;
  const list = loadKeywordHistory() || [...KW_DEFAULTS];
  wrap.innerHTML = list
    .map((k) => `<button class="tag tag-clickable" data-keyword="${esc(k)}">${esc(k)}</button>`)
    .join("");
  wrap.querySelectorAll(".tag-clickable").forEach((btn) =>
    btn.addEventListener("click", () => {
      $("#scrape-keyword").value = btn.dataset.keyword;
      $("#scrape-keyword").focus();
    })
  );
}
renderKeywordChips();

// ---- Enrichment ----
// Label tampilan per sumber & field (meta selengkapnya dinamis dari /api/sources)
const SOURCE_LABELS = {
  google: "Pencarian Google / Web",
  dapodik: "Dapodik Kemdikbud",
  jobstreet: "Jobstreet",
  glints: "Glints",
  lpse: "LPSE Daerah",
};
const FIELD_LABELS = {
  telp: "No. WA/Telepon",
  email: "Email",
  website: "Website",
  sosmed: "Instagram",
  npsn: "NPSN",
  nama_kepsek: "Nama Kepsek",
  link_source: "Sumber Data",
};

// Cache daftar sumber enrichment (dari /api/sources)
let enrichSourcesCache = [];
// Cache job terakhir yang dirender
let lastJobs = [];

// Muat meta enrichment dinamis untuk tabel "Field yang Diisi per Sumber Enrichment".
async function loadEnrichmentMeta() {
  try {
    const s = await api("/api/sources");
    const list = s.enrichment_sources || [];
    enrichSourcesCache = list;

    const fmtFields = (fields) =>
      (fields || []).map((f) => FIELD_LABELS[f] || f).join(", ") || "-";
    const fieldsBody = $("#enrich-fields-body");
    if (fieldsBody) {
      fieldsBody.innerHTML = list
        .map(
          (e) => `
        <tr>
          <td><span class="enrich-badge ${esc(e.source)}">${esc(SOURCE_LABELS[e.source] || e.source)}</span></td>
          <td>${e.available
            ? '<span class="tag tag-completed">tersedia</span>'
            : '<span class="tag tag-pending">belum tersedia</span>'}</td>
          <td>${esc(fmtFields(e.fields))}</td>
        </tr>`
        )
        .join("");
    }
  } catch (ex) {
    console.warn("loadEnrichmentMeta:", ex.message);
  }
}

// ===== MODAL PILIHAN SUMBER ENRICHMENT =====
let currentEnrichJob = null;

function openEnrichModal(job) {
  if (!job) return;
  currentEnrichJob = job;

  const modalTarget = $("#enrich-modal-target-text");
  if (modalTarget) {
    modalTarget.textContent = `Kategori "${job.category}" di Kota "${job.city}"`;
  }

  const errEl = $("#modal-enrich-error");
  if (errEl) {
    errEl.textContent = "";
    errEl.classList.add("hidden");
  }

  // Rekomendasi pintar sumber enrichment berdasarkan nama kategori
  const cat = String(job.category || "").toLowerCase();
  let defaultSource = "google";

  // Sembunyikan semua badge rekomendasi dulu
  ["google", "dapodik", "jobstreet", "glints", "lpse"].forEach((src) => {
    const b = $(`#badge-rec-${src}`);
    if (b) b.classList.add("hidden");
  });

  if (
    cat.includes("sekolah") || cat.includes("sd") || cat.includes("smp") ||
    cat.includes("sma") || cat.includes("smk") || cat.includes("madrasah") ||
    cat.includes("pesantren") || cat.includes("school")
  ) {
    defaultSource = "dapodik";
    const b = $("#badge-rec-dapodik");
    if (b) b.classList.remove("hidden");
  } else if (cat.includes("vendor") || cat.includes("kontraktor") || cat.includes("b2g") || cat.includes("pengadaan")) {
    defaultSource = "lpse";
    const b = $("#badge-rec-lpse");
    if (b) b.classList.remove("hidden");
  } else if (cat.includes("corporate") || cat.includes("perusahaan")) {
    defaultSource = "jobstreet";
    const b = $("#badge-rec-jobstreet");
    if (b) b.classList.remove("hidden");
  } else {
    // Default umum (rumah sakit, klinik, faskes, hotel, kafe, resto, umkm, toko, dll.)
    defaultSource = "google";
    const b = $("#badge-rec-google");
    if (b) b.classList.remove("hidden");
  }

  selectEnrichRadio(defaultSource);

  const overlay = $("#modal-enrich-overlay");
  if (overlay) overlay.classList.remove("hidden");
}

function closeEnrichModal() {
  const overlay = $("#modal-enrich-overlay");
  if (overlay) overlay.classList.add("hidden");
  currentEnrichJob = null;
}

function selectEnrichRadio(sourceVal) {
  const cards = document.querySelectorAll(".enrich-source-card");
  cards.forEach((card) => {
    const radio = card.querySelector('input[type="radio"]');
    if (card.dataset.source === sourceVal) {
      if (radio) radio.checked = true;
      card.classList.add("selected");
    } else {
      card.classList.remove("selected");
    }
  });
}

async function submitEnrichModal() {
  if (!currentEnrichJob) return;
  const checkedRadio = document.querySelector('input[name="modal_enrich_source"]:checked');
  const selectedSource = checkedRadio ? checkedRadio.value : "google";
  const errEl = $("#modal-enrich-error");
  const submitBtn = $("#modal-enrich-submit");

  try {
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = "Memulai...";
    }
    unlockAudio();
    await api("/api/enrich", {
      method: "POST",
      body: {
        category: currentEnrichJob.category,
        city: currentEnrichJob.city,
        enrichment_source: selectedSource,
        max_results: 0,
      },
    });
    closeEnrichModal();
    navigate("enrichment");
    startPolling();
    loadEnrichmentJobs();
  } catch (ex) {
    if (errEl) {
      errEl.textContent = "Gagal memulai enrichment: " + ex.message;
      errEl.classList.remove("hidden");
    }
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = "⚡ Mulai Enrichment";
    }
  }
}

// Inisialisasi event listener interaktif modal pilihan enrichment
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".enrich-source-card").forEach((card) => {
    card.addEventListener("click", () => {
      const src = card.dataset.source;
      if (src) selectEnrichRadio(src);
    });
  });

  $("#modal-enrich-close")?.addEventListener("click", closeEnrichModal);
  $("#modal-enrich-cancel")?.addEventListener("click", closeEnrichModal);
  $("#modal-enrich-submit")?.addEventListener("click", submitEnrichModal);
  $("#modal-enrich-overlay")?.addEventListener("click", (e) => {
    if (e.target.id === "modal-enrich-overlay") closeEnrichModal();
  });
});

// ---- Load Enrichment Jobs ----
let lastEnrichJobs = [];

async function loadEnrichmentJobs(silent = false) {
  try {
    const r = await api("/api/jobs?limit=100");
    // Filter hanya job enrichment (bukan gmaps seed)
    const enrichJobs = (r.items || []).filter((j) => j.source !== "gmaps");
    lastEnrichJobs = enrichJobs;
    if (silent) {
      enrichJobs.forEach((j) => {
        const prev = jobPrevStatus.get(j.id);
        jobPrevStatus.set(j.id, j.status);
        if (prev && prev !== j.status && (prev === "running" || prev === "pending")) {
          if (j.status === "completed") playSound("done");
          else if (j.status === "error" || j.status === "cancelled") playSound("fail");
        }
      });
    }
    renderEnrichmentJobs(enrichJobs);
    const active = enrichJobs.some((j) => j.status === "running" || j.status === "pending");
    if (active) startPolling(); else stopPolling();
  } catch (ex) {
    console.warn("loadEnrichmentJobs:", ex.message);
  }
}

// Format tampilan Ditemukan / Terambil: misal "12/50 dari 120"
function formatJobResult(j) {
  const isTerminal = ["completed", "error", "cancelled"].includes(j.status);
  const taken = (j.items_created || 0) + (j.items_updated || 0);
  const progress = parseInt(j.progress, 10) || 0;
  // Saat proses running, gunakan progress ekstraksi real-time agar tidak macet di 0
  const currentCount = isTerminal ? taken : Math.max(progress, taken);

  const target = parseInt(j.max_results, 10) || 0;
  const found = parseInt(j.total_found, 10) || 0;
  if (found > target && target > 0) {
    return `${currentCount}/${target} dari ${found}`;
  }
  if (target > 0 && found > 0) {
    return `${currentCount}/${target}`;
  }
  if (found > 0) {
    return `${currentCount}/${found}`;
  }
  return `${currentCount}/${target || 0}`;
}

function renderEnrichmentJobs(jobs) {
  const fmtTime = (iso) =>
    iso ? new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "-";
  $("#enrich-jobs-body").innerHTML = (jobs || [])
    .map((j) => {
      const taken = (j.items_created || 0) + (j.items_updated || 0);
      return `
    <tr data-ejob="${j.id}">
      <td class="mono">${fmtTime(j.started_at)}</td>
      <td><span class="tag tag-src">${esc(j.source)}</span></td>
      <td>${esc(j.category)}</td>
      <td>${esc(j.city)}</td>
      <td><span class="tag tag-${esc(j.status)}">${esc(j.status)}</span></td>
      <td>
        <div class="progress-track"><div class="progress-fill" style="width:${jobProgressPct(j)}%"></div></div>
        <span class="mono" style="font-size:11.5px;color:var(--muted)" title="${taken} lead field terisi">${jobProgressPct(j)}%</span>
      </td>
      <td class="mono">${formatJobResult(j)}</td>
      <td class="row-actions">
        ${j.status === "running" || j.status === "pending"
          ? `<button class="btn btn-ghost btn-sm" data-cancel="${j.id}">Stop</button>`
          : `<button class="btn btn-ghost btn-sm" data-rerunenrich="${j.id}" title="Ulangi enrichment ini (update waktu & data)">↻ Ulangi</button>`}
        <button class="btn btn-ghost btn-sm" data-incompletetoggle="${j.id}" title="Lihat daftar instansi yang belum lengkap atau gagal di-enrich">📋 Data Belum Lengkap</button>
        <button class="btn btn-ghost-danger btn-sm" data-deljob="${j.id}" title="Hapus riwayat job">Hapus</button>
      </td>
    </tr>
    <tr class="incomplete-row hidden" data-incompleterow="${j.id}">
      <td colspan="8">
        <div class="incomplete-box" data-incompletebox="${j.id}">
          <div class="incomplete-loading muted">Memuat data belum lengkap…</div>
        </div>
      </td>
    </tr>`;
    })
    .join("") || `<tr><td colspan="8" class="muted" style="text-align:center;padding:24px">Belum ada job enrichment</td></tr>`;

  document.querySelectorAll("#page-enrichment [data-cancel]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        await api(`/api/jobs/${b.dataset.cancel}/cancel`, { method: "POST" });
        loadEnrichmentJobs();
      } catch (ex) { console.warn("cancel:", ex.message); }
    })
  );
  document.querySelectorAll("#page-enrichment [data-rerunenrich]").forEach((b) =>
    b.addEventListener("click", () => rerunEnrichmentJob(b.dataset.rerunenrich))
  );
  document.querySelectorAll("#page-enrichment [data-deljob]").forEach((b) =>
    b.addEventListener("click", () => deleteJob(b.dataset.deljob, loadEnrichmentJobs))
  );
  document.querySelectorAll("#page-enrichment [data-incompletetoggle]").forEach((b) =>
    b.addEventListener("click", () => toggleIncompleteRow(b.dataset.incompletetoggle))
  );
}

// Ulangi job enrichment yang sudah selesai/error dengan update waktu started_at
async function rerunEnrichmentJob(jobId) {
  const job = (lastEnrichJobs || []).find((j) => j.id === jobId);
  if (!job) return;
  const ok = await confirmDialog(
    `Ulangi enrichment ${job.source.toUpperCase()} untuk '${job.category}' @ '${job.city}'? Riwayat job akan diperbarui (waktu di-update).`
  );
  if (!ok) return;
  try {
    await api("/api/enrich", {
      method: "POST",
      body: {
        job_id: job.id,
        category: job.category,
        city: job.city,
        enrichment_source: job.source,
        max_results: 0,
      },
    });
    startPolling();
    loadEnrichmentJobs();
  } catch (ex) {
    alert("Gagal menjalankan ulang enrichment: " + ex.message);
  }
}

async function toggleIncompleteRow(jobId) {
  const row = document.querySelector(`[data-incompleterow="${jobId}"]`);
  if (!row) return;
  const isHidden = row.classList.contains("hidden");
  row.classList.toggle("hidden");
  if (isHidden) {
    await loadIncompleteLeads(jobId);
  }
}

async function loadIncompleteLeads(jobId) {
  const box = document.querySelector(`[data-incompletebox="${jobId}"]`);
  if (!box) return;
  box.innerHTML = '<div class="incomplete-loading muted">Memuat data lokasi yang belum lengkap…</div>';
  try {
    const res = await api(`/api/jobs/${jobId}/incomplete`);
    const items = res.items || [];
    if (!items.length) {
      box.innerHTML = `
        <div class="incomplete-empty">
          <span class="tag tag-completed">Semua Lengkap</span>
          <span class="muted" style="margin-left:8px">Semua lead (${esc(res.category)} @ ${esc(res.city)}) sudah memiliki data ${(res.fields || []).map((f) => FIELD_LABELS[f] || f).join(", ")}.</span>
        </div>`;
      return;
    }

    const rows = items
      .map((item, idx) => {
        const missingBadges = (item.missing_fields || [])
          .map((f) => `<span class="tag tag-pending" style="font-size:11px">${esc(FIELD_LABELS[f] || f)}: kosong</span>`)
          .join(" ");

        const loc = [item.alamat, item.kota].filter(Boolean).join(", ") || "-";
        return `
        <div class="incomplete-item" data-incleadid="${item.id}">
          <div class="incomplete-info">
            <div class="incomplete-title">
              <b>${idx + 1}. ${esc(item.nama_instansi || "Tanpa Nama")}</b>
              <span class="tag tag-src" style="font-size:10px">${esc(item.source || "seed")}</span>
            </div>
            <div class="incomplete-loc">
              📍 <b>Lokasi:</b> ${esc(loc)}
            </div>
            <div class="incomplete-fields">
              <span class="muted" style="font-size:11.5px;margin-right:6px">Status Data:</span>
              ${missingBadges}
            </div>
          </div>
          <div class="incomplete-actions">
            <button type="button" class="btn btn-primary btn-sm btn-edit-inc" data-editinc="${item.id}" title="Isi data enrichment secara manual">
              ✏️ Isi Manual
            </button>
          </div>
        </div>`;
      })
      .join("");

    box.innerHTML = `
      <div class="incomplete-header">
        <span style="font-weight:600;font-size:13px">Data Belum Lengkap / Gagal Enrich (${items.length} lokasi di ${esc(res.city)}):</span>
        <span class="muted" style="font-size:12px">Anda dapat mengisi field yang belum ada (${(res.fields || []).map((f) => FIELD_LABELS[f] || f).join(", ")}) secara manual di bawah ini.</span>
      </div>
      <div class="incomplete-list">${rows}</div>
    `;

    box.querySelectorAll(".btn-edit-inc").forEach((btn) => {
      btn.addEventListener("click", () => {
        const leadId = parseInt(btn.dataset.editinc, 10);
        const leadObj = items.find((x) => x.id === leadId);
        if (leadObj) {
          openEditModal(leadObj);
          window._onModalSaveCallback = () => loadIncompleteLeads(jobId);
        }
      });
    });
  } catch (err) {
    box.innerHTML = `<div class="incomplete-error form-msg" style="color:var(--danger)">Gagal memuat data: ${esc(err.message)}</div>`;
  }
}

// Perhitungan persentase progres yang akurat dan bertahap secara real-time.
function jobProgressPct(j) {
  if (j.status === "completed") return 100;

  const max = parseInt(j.max_results, 10) || 0;
  const found = parseInt(j.total_found, 10) || 0;
  const progress = parseInt(j.progress, 10) || 0;
  const taken = (j.items_created || 0) + (j.items_updated || 0);
  const currentCount = Math.max(progress, taken);

  // Jika error atau cancelled
  if (["error", "cancelled"].includes(j.status)) {
    if (currentCount <= 0) return 0;
    const target = max > 0 ? max : (found || 1);
    return Math.max(0, Math.min(100, Math.round((currentCount / target) * 100)));
  }

  // Jika pending, progress 0%
  if (j.status === "pending") return 0;

  // Target efektif: jika listing Maps yang ditemukan lebih sedikit dari target max_results,
  // gunakan jumlah yang ditemukan sebagai batas target.
  const effectiveTarget = (found > 0 && found < max) ? found : (max > 0 ? max : (found || 1));

  if (currentCount <= 0) {
    // Saat baru mulai running (membuka browser atau scrolling feed)
    return found > 0 ? 5 : 2;
  }

  // Hitung persentase progres bertahap (1/50 = 2%, 10/50 = 20%, dst)
  const pct = Math.round((currentCount / effectiveTarget) * 100);
  // Selama status masih running, jangan loncat ke 100% sebelum selesai seutuhnya
  return Math.max(2, Math.min(99, pct));
}

async function loadJobs(silent = false) {
  try {
    const r = await api("/api/jobs");
    if (silent) {
      (r.items || []).forEach((j) => {
        const prev = jobPrevStatus.get(j.id);
        jobPrevStatus.set(j.id, j.status);
        if (prev && prev !== j.status && (prev === "running" || prev === "pending")) {
          if (j.status === "completed") playSound("done");
          else if (j.status === "error" || j.status === "cancelled") playSound("fail");
        }
      });
    }
    renderJobs(r.items);
    const active = (r.items || []).some((j) => j.status === "running" || j.status === "pending");
    if (active) startPolling(); else stopPolling();
  } catch (ex) {
    if (!silent) console.warn("loadJobs:", ex.message);
  }
}

function renderJobs(jobs) {
  // Riwayat Job di menu Scrape KHUSUS data Google Maps (PRD/user request)
  const gmapsJobs = (jobs || []).filter((j) => j.source === "gmaps");
  lastJobs = gmapsJobs;
  const sorted = sortByKey(gmapsJobs, jobSort.key, jobSort.dir);
  const fmtTime = (iso) =>
    iso ? new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "-";
  const isTerminal = (j) => !["running", "pending"].includes(j.status);

  $("#jobs-body").innerHTML = sorted
    .map((j) => {
      const isSeed = j.source === "gmaps";
      const isTerminalState = isTerminal(j);
      const isCompleted = j.status === "completed";
      const quotaReached = (j.progress || 0) >= (j.max_results || 0);
      const hasMoreFound = (j.total_found || 0) > (j.progress || 0);

      let actionBtn = "";
      if (j.status === "running" || j.status === "pending") {
        actionBtn = `<button class="btn btn-ghost btn-sm" data-cancel="${j.id}">Stop</button>`;
      } else if (isCompleted && quotaReached && hasMoreFound) {
        // Kuota sudah selesai (misal 5/5), tapi di Maps masih ada sisa listing (total_found > progress misal 120 > 5)
        // Tombolnya adalah "➕ Lengkapi" (bukan Ulangi)
        actionBtn = `<button class="btn btn-ghost btn-sm" data-complete="${j.id}" title="Lengkapi data (ditemukan ${j.total_found}, baru terambil ${j.progress})">➕ Lengkapi</button>`;
      } else if (!isCompleted || (!quotaReached && hasMoreFound)) {
        // Belum selesai (error, cancelled, atau kuota belum terpenuhi)
        // Tombolnya adalah "↻ Ulangi"
        actionBtn = `<button class="btn btn-ghost btn-sm" data-rerun="${j.id}" title="Ulangi job yang belum selesai ini">↻ Ulangi</button>`;
      }

      const actions = [
        actionBtn,
        isSeed && isTerminalState
          ? `<button class="btn btn-ghost btn-sm" data-enrich="${j.id}" title="Pindah ke menu Enrichment utk kategori & kota job ini">⚡ Enrich</button>` : "",
        `<button class="btn btn-ghost-danger btn-sm" data-deljob="${j.id}" title="Hapus riwayat job">Hapus</button>`,
      ].filter(Boolean).join(" ");

      return `
    <tr>
      <td class="mono">${fmtTime(j.started_at)}</td>
      <td class="mono font-bold" style="font-size:11px;letter-spacing:-0.2px;color:var(--text-main)">${esc(j.id || '')}</td>
      <td>${esc(j.category)}</td>
      <td>${esc(j.city)}</td>
      <td><span class="tag tag-${esc(j.status)}">${esc(j.status)}</span></td>
      <td>
        <div class="progress-track"><div class="progress-fill" style="width:${jobProgressPct(j)}%"></div></div>
        <span class="mono" style="font-size:11.5px;color:var(--muted)" title="${j.progress || 0} diproses dari target ${j.max_results || j.total_found || 0} (total listing: ${j.total_found || 0})">${jobProgressPct(j)}%</span>
      </td>
      <td class="mono">${formatJobResult(j)}</td>
      <td class="row-actions">${actions}</td>
    </tr>`;
    })
    .join("") || `<tr><td colspan="8" class="muted" style="text-align:center;padding:24px">Belum ada job Google Maps</td></tr>`;

  renderJobSortIndicators();
  document.querySelectorAll("[data-cancel]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        await api(`/api/jobs/${b.dataset.cancel}/cancel`, { method: "POST" });
        loadJobs();
      } catch (ex) { console.warn("cancel:", ex.message); }
    })
  );
  document.querySelectorAll("#page-scrape [data-deljob]").forEach((b) =>
    b.addEventListener("click", () => deleteJob(b.dataset.deljob))
  );
  document.querySelectorAll("#page-scrape [data-enrich]").forEach((b) =>
    b.addEventListener("click", () => {
      const job = lastJobs.find((j) => j.id === b.dataset.enrich);
      if (job) goToEnrichmentFromJob(job);
    })
  );
  document.querySelectorAll("#page-scrape [data-rerun]").forEach((b) =>
    b.addEventListener("click", () => rerunJob(b.dataset.rerun))
  );
  document.querySelectorAll("#page-scrape [data-complete]").forEach((b) =>
    b.addEventListener("click", () => completeJob(b.dataset.complete))
  );
}

// Membuka modal pilihan sumber enrichment untuk job terkait
function goToEnrichmentFromJob(job) {
  if (!job) return;
  openEnrichModal(job);
}

// Lengkapi data jika total_found > progress (misal 5/5 dari 120).
// Memperbarui job yang sudah ada (update waktu & status) tanpa membuat baris baru.
async function completeJob(jobId) {
  const job = lastJobs.find((j) => j.id === jobId);
  if (!job) return;
  const sisa = Math.max(0, (job.total_found || 0) - (job.progress || 0));
  const defaultTarget = job.total_found || 100;
  const input = prompt(
    `Lengkapi data '${job.category}' @ '${job.city}'?\n` +
    `Total listing ditemukan di Google Maps: ${job.total_found}\n` +
    `Sudah terambil: ${job.progress} data (tersisa ${sisa} data lagi).\n\n` +
    `Masukkan target maksimal hasil baru:`,
    defaultTarget
  );
  if (!input) return;
  const newMax = parseInt(input, 10);
  if (isNaN(newMax) || newMax <= 0) {
    alert("Jumlah target harus berupa angka positif.");
    return;
  }
  try {
    await api("/api/scrape", {
      method: "POST",
      body: {
        job_id: job.id,
        source: job.source,
        category: job.category,
        city: job.city,
        max_results: newMax,
      },
    });
    startPolling();
    loadJobs();
  } catch (ex) {
    alert("Gagal melengkapi data: " + ex.message);
  }
}

// Ulangi job (scrape/enrichment) yang belum selesai atau error.
// Memperbarui job yang sudah ada (waktu di-update) tanpa membuat baris baru.
async function rerunJob(jobId) {
  const job = lastJobs.find((j) => j.id === jobId);
  if (!job) return;
  const ok = await confirmDialog(
    job.source === "gmaps"
      ? `Ulangi scrape '${job.category}' @ '${job.city}'? Riwayat job akan diperbarui (waktu di-update).`
      : `Ulangi enrichment ${job.source} untuk '${job.category}' @ '${job.city}'? Riwayat job akan diperbarui.`
  );
  if (!ok) return;
  try {
    if (job.source === "gmaps") {
      await api("/api/scrape", {
        method: "POST",
        body: {
          job_id: job.id,
          source: job.source,
          category: job.category,
          city: job.city,
          max_results: job.max_results || 100,
        },
      });
    } else {
      await api("/api/enrich", {
        method: "POST",
        body: {
          job_id: job.id,
          category: job.category,
          city: job.city,
          enrichment_source: job.source,
        },
      });
    }
    startPolling();
    loadJobs();
  } catch (ex) {
    alert("Gagal menjalankan ulang: " + ex.message);
  }
}

// Hapus satu baris riwayat job (log audit). Lead yang sudah tersimpan tidak terpengaruh.
// `reload` = fungsi refresh tabel pemanggil (loadJobs / loadEnrichmentJobs).
async function deleteJob(jobId, reload = loadJobs) {
  const ok = await confirmDialog("Hapus baris riwayat job ini? Lead yang sudah tersimpan tidak ikut terhapus.");
  if (!ok) return;
  try {
    await api(`/api/jobs/${jobId}`, { method: "DELETE" });
    await reload();
  } catch (ex) {
    alert("Gagal menghapus riwayat: " + ex.message);
  }
}

// Klik header tabel Riwayat Job → toggle sorting asc/desc
document.querySelectorAll("#page-scrape th[data-jsort]").forEach((th) =>
  th.addEventListener("click", () => {
    const key = th.dataset.jsort;
    if (jobSort.key === key) {
      jobSort.dir = jobSort.dir === "asc" ? "desc" : "asc";
    } else {
      jobSort.key = key;
      jobSort.dir = "desc";
    }
    renderJobSortIndicators();
    loadJobs();
  })
);

// ---- Browser login (Google) ----
let browserPollTimer = null;

function stopBrowserPolling() {
  clearInterval(browserPollTimer);
  browserPollTimer = null;
}

async function loadBrowserStatus() {
  const el = $("#browser-login-status");
  try {
    const s = await api("/api/browser-status");
    if (s.has_cookies) {
      el.textContent = "✅ Profil browser siap — sesi Google tersimpan.";
      el.style.color = "var(--success, #16a34a)";
      stopBrowserPolling();
    } else {
      el.textContent = "⚠️ Belum login ke Google — klik \"Buka Browser Login\".";
      el.style.color = "var(--warning, #d97706)";
    }
  } catch (_) {
    el.textContent = "Tidak dapat memeriksa status browser.";
    el.style.color = "var(--danger)";
  }
}

$("#btn-browser-login").addEventListener("click", async () => {
  const el = $("#browser-login-status");
  try {
    await api("/api/browser-login", { method: "POST" });
    el.textContent = "Chrome terbuka — login ke akun Google, lalu tutup jendelanya.";
    el.style.color = "var(--muted)";
    stopBrowserPolling();
    browserPollTimer = setInterval(() => {
      if ($("#page-scrape").classList.contains("hidden")) { stopBrowserPolling(); return; }
      loadBrowserStatus();
    }, 5000);
  } catch (ex) {
    el.textContent = "Gagal membuka browser: " + ex.message;
    el.style.color = "var(--danger)";
  }
});

// ---- Results page ----
const leadState = { page: 1, size: 25, sort_by: "updated_at", sort_dir: "desc" };
let currentItems = []; // cache item halaman aktif (untuk modal edit)
const EDITABLE_FIELDS = [
  "nama_instansi", "kategori", "telp", "email", "alamat", "kota",
  "link_gmaps", "website", "instagram", "facebook", "linkedin", "twitter_x", "tiktok", "sosmed", "npsn", "nama_kepsek",
];
// ---- SVG Icons (Lucide / Feather style — profesional, bukan emoji keyboard) ----
const PENCIL_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>`;
const TRASH_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/><path d="m19 6-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>`;
const GMAPS_SVG = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>`;
const CLOSE_SVG = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
const GLOBE_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`;
const PHONE_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>`;
const INSTAGRAM_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"/></svg>`;
const FACEBOOK_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"/></svg>`;
const LINKEDIN_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"/><rect x="2" y="9" width="4" height="12"/><circle cx="4" cy="4" r="2"/></svg>`;
const TWITTER_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4l11.733 16h4.267l-11.733 -16z"/><path d="M4 20l6.768 -6.768m2.46 -2.46l6.772 -6.772"/></svg>`;
const TIKTOK_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 12a4 4 0 1 0 4 4V4a5 5 0 0 0 5 5"/></svg>`;
const MAIL_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>`;
const ID_CARD_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><line x1="7" y1="8" x2="17" y2="8"/><line x1="7" y1="12" x2="13" y2="12"/><line x1="7" y1="16" x2="10" y2="16"/></svg>`;
const MERGE_SVG = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/></svg>`;
const CHECK_SHIELD_SVG = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>`;


async function loadFilters() {
  try {
    const r = await api("/api/filters");
    // Kategori: dropdown dari DB (menggantikan filter sumber per permintaan user)
    const uniqueCategories = [...new Set(r.categories || [])];
    const catSel = $("#f-category");
    if (catSel) {
      catSel.innerHTML =
        '<option value="">Semua kategori</option>' +
        uniqueCategories.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
    }
    // Kota: dropdown dari DB
    const uniqueCities = [...new Set(r.cities || [])];
    $("#f-kota").innerHTML =
      '<option value="">Semua kota</option>' +
      uniqueCities.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
    // Datalist untuk modal edit lead (kategori & kota dari DB)
    $("#kota-list").innerHTML = uniqueCities.map((c) => `<option value="${esc(c)}"></option>`).join("");
    const catOptions = uniqueCategories.map((c) => `<option value="${esc(c)}"></option>`).join("");
    $("#kategori-list").innerHTML = catOptions;
  } catch (_) { /* non-fatal */ }
}

function leadParams() {
  return new URLSearchParams({
    search: $("#f-search").value.trim(),
    category: $("#f-category") ? $("#f-category").value : "",
    kota: $("#f-kota").value,
    status: $("#f-status").value,
    page: leadState.page,
    size: leadState.size,
    sort_by: leadState.sort_by,
    sort_dir: leadState.sort_dir,
  }).toString();
}

function renderSortIndicators() {
  document.querySelectorAll("#page-results th.th-sort").forEach((th) => {
    const active = th.dataset.sort === leadState.sort_by;
    th.classList.toggle("sorted", active);
    const arrow = th.querySelector(".sort-arrow");
    if (arrow) arrow.textContent = active ? (leadState.sort_dir === "asc" ? "▲" : "▼") : "";
  });
}

// ---- Shortcut Cepat Hapus Field di Result Table (Gambar 1 style) ----
function formatResultPhone(l) {
  if (!l.telp) return "-";
  return `
    <div class="result-field-chip chip-telp">
      <span class="chip-icon">${PHONE_SVG}</span>
      <span class="chip-label">TELP:</span>
      <span class="mono chip-val" title="${esc(l.telp)}">${esc(l.telp)}</span>
      <button type="button" class="btn-result-clear" data-rclear="${l.id}" data-rfield="telp" title="Hapus nomor telepon">${CLOSE_SVG}</button>
    </div>`;
}

function formatResultEmail(l) {
  if (!l.email) return "-";
  const list = String(l.email).split(",").map((e) => e.trim()).filter(Boolean);
  if (!list.length) return "-";
  return `<div class="result-chip-box">${list
    .map(
      (e) => `
    <div class="result-field-chip chip-email">
      <span class="chip-icon">${MAIL_SVG}</span>
      <span class="chip-label">EMAIL:</span>
      <a href="mailto:${esc(e)}" class="cell-url chip-val" title="${esc(e)}">${esc(e)}</a>
      <button type="button" class="btn-result-clear" data-rclear="${l.id}" data-rfield="email" data-rval="${esc(e)}" title="Hapus email ini">${CLOSE_SVG}</button>
    </div>`
    )
    .join("")}</div>`;
}

function formatResultWebsite(l) {
  if (!l.website) return "-";
  return `
    <div class="result-field-chip chip-web">
      <span class="chip-icon">${GLOBE_SVG}</span>
      <span class="chip-label">WEB:</span>
      <a href="${esc(l.website)}" target="_blank" rel="noopener" class="cell-url chip-val" title="${esc(l.website)}">${esc(l.website)}</a>
      <button type="button" class="btn-result-clear" data-rclear="${l.id}" data-rfield="website" title="Hapus link website">${CLOSE_SVG}</button>
    </div>`;
}

function formatResultSocial(l) {
  const items = [];
  if (l.instagram) {
    items.push(`
      <div class="result-field-chip">
        <span class="chip-icon">${INSTAGRAM_SVG}</span>
        <span class="chip-label">IG:</span>
        <a href="${esc(l.instagram)}" target="_blank" rel="noopener" class="cell-url chip-val" title="${esc(l.instagram)}">${esc(l.instagram)}</a>
        <button type="button" class="btn-result-clear" data-rclear="${l.id}" data-rfield="instagram" title="Hapus Instagram">${CLOSE_SVG}</button>
      </div>`);
  }
  if (l.tiktok) {
    items.push(`
      <div class="result-field-chip">
        <span class="chip-icon">${TIKTOK_SVG}</span>
        <span class="chip-label">TikTok:</span>
        <a href="${esc(l.tiktok)}" target="_blank" rel="noopener" class="cell-url chip-val" title="${esc(l.tiktok)}">${esc(l.tiktok)}</a>
        <button type="button" class="btn-result-clear" data-rclear="${l.id}" data-rfield="tiktok" title="Hapus TikTok">${CLOSE_SVG}</button>
      </div>`);
  }
  if (l.facebook) {
    items.push(`
      <div class="result-field-chip">
        <span class="chip-icon">${FACEBOOK_SVG}</span>
        <span class="chip-label">FB:</span>
        <a href="${esc(l.facebook)}" target="_blank" rel="noopener" class="cell-url chip-val" title="${esc(l.facebook)}">${esc(l.facebook)}</a>
        <button type="button" class="btn-result-clear" data-rclear="${l.id}" data-rfield="facebook" title="Hapus Facebook">${CLOSE_SVG}</button>
      </div>`);
  }
  if (l.linkedin) {
    items.push(`
      <div class="result-field-chip">
        <span class="chip-icon">${LINKEDIN_SVG}</span>
        <span class="chip-label">LinkedIn:</span>
        <a href="${esc(l.linkedin)}" target="_blank" rel="noopener" class="cell-url chip-val" title="${esc(l.linkedin)}">${esc(l.linkedin)}</a>
        <button type="button" class="btn-result-clear" data-rclear="${l.id}" data-rfield="linkedin" title="Hapus LinkedIn">${CLOSE_SVG}</button>
      </div>`);
  }
  if (l.twitter_x) {
    items.push(`
      <div class="result-field-chip">
        <span class="chip-icon">${TWITTER_SVG}</span>
        <span class="chip-label">X:</span>
        <a href="${esc(l.twitter_x)}" target="_blank" rel="noopener" class="cell-url chip-val" title="${esc(l.twitter_x)}">${esc(l.twitter_x)}</a>
        <button type="button" class="btn-result-clear" data-rclear="${l.id}" data-rfield="twitter_x" title="Hapus Twitter/X">${CLOSE_SVG}</button>
      </div>`);
  }
  if (l.sosmed && !l.instagram && !l.tiktok && !l.facebook && !l.linkedin && !l.twitter_x) {
    items.push(`
      <div class="result-field-chip">
        <span class="chip-icon">${GLOBE_SVG}</span>
        <span class="chip-label">MEDSOS:</span>
        <a href="${esc(l.sosmed)}" target="_blank" rel="noopener" class="cell-url chip-val" title="${esc(l.sosmed)}">${esc(l.sosmed)}</a>
        <button type="button" class="btn-result-clear" data-rclear="${l.id}" data-rfield="sosmed" title="Hapus Media Sosial">${CLOSE_SVG}</button>
      </div>`);
  }
  if (!items.length) return "-";
  return `<div class="result-chip-box">${items.join("")}</div>`;
}

// Sel <td> dari Nama Instansi s.d. Sumber — dipakai tabel Results
function leadCells(l) {
  return `
      <td class="mono font-bold" style="color:var(--primary); font-size:11.5px; white-space:nowrap;">${esc(l.kode || ('LD-' + l.id))}</td>
      <td><b>${esc(l.nama_instansi)}</b></td>
      <td>${esc(l.kategori || "-")}</td>
      <td>${formatResultPhone(l)}</td>
      <td>${formatResultEmail(l)}</td>
      <td>${esc(l.alamat || "-")}</td>
      <td>${esc(l.kota || "-")}</td>
      <td>${linkCell(l.link_gmaps, l.link_gmaps)}</td>
      <td>${formatResultWebsite(l)}</td>
      <td>${formatResultSocial(l)}</td>
      <td class="mono">${esc(l.npsn || "-")}</td>
      <td>${esc(l.nama_kepsek || "-")}</td>
      <td>${linkCell(l.link_source, l.link_source)}</td>
      <td><span class="tag tag-src">${esc(l.source)}</span></td>`;
}

// Sorting client-side untuk data array (tabel Jobs & Review Duplikat)
function sortByKey(arr, key, dir) {
  const mul = dir === "asc" ? 1 : -1;
  return [...arr].sort((a, b) => {
    const va = a[key], vb = b[key];
    if (va == null || va === "") return 1;   // kosong selalu di belakang
    if (vb == null || vb === "") return -1;
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * mul;
    return String(va).localeCompare(String(vb), "id", { numeric: true }) * mul;
  });
}

async function quickClearResultItem(leadId, field, specificVal) {
  const item = currentItems.find((x) => x.id === leadId);
  const instName = item ? item.nama_instansi : `Lead #${leadId}`;
  let promptMsg = `Hapus data ${field} dari "${instName}"?`;
  let payload = {};

  if (field === "email" && specificVal) {
    promptMsg = `Hapus email "${specificVal}" dari "${instName}"?`;
    const curEmails = String(item?.email || "").split(",").map((e) => e.trim()).filter(Boolean);
    const updatedEmails = curEmails.filter((e) => e.toLowerCase() !== specificVal.toLowerCase()).join(", ");
    payload = { email: updatedEmails };
  } else {
    payload = { [field]: "" };
  }

  const ok = await confirmDialog(promptMsg, false);
  if (!ok) return;

  try {
    await api(`/api/leads/${leadId}`, { method: "PATCH", body: payload });
    loadLeads();
  } catch (ex) {
    alert("Gagal menghapus data: " + ex.message);
  }
}

async function loadLeads() {
  const r = await api(`/api/leads?${leadParams()}`);
  const offset = (r.page - 1) * r.size;
  currentPageIds = r.items.map((l) => l.id);
  currentItems = r.items;

  const rows = r.items
    .map(
      (l, i) => `
    <tr>
      <td class="col-check"><input type="checkbox" class="lead-check" data-id="${l.id}" ${selectedLeads.has(l.id) ? "checked" : ""} aria-label="Pilih lead ${esc(l.nama_instansi)}" /></td>
      <td class="mono">${offset + i + 1}</td>
      ${leadCells(l)}
      <td>
        <select data-status="${l.id}" aria-label="Ubah status lead ${esc(l.nama_instansi)}">
          ${STATUS_OPTS.map((s) => `<option ${s === l.status ? "selected" : ""}>${s}</option>`).join("")}
        </select>
      </td>
      <td>
        <div class="row-actions">
          <button type="button" class="btn-icon btn-edit" data-edit="${l.id}" aria-label="Edit lead ${esc(l.nama_instansi)}" title="Edit lead">${PENCIL_SVG}</button>
          <button type="button" class="btn-icon" data-del="${l.id}" aria-label="Hapus lead ${esc(l.nama_instansi)}" title="Hapus lead">${TRASH_SVG}</button>
        </div>
      </td>
    </tr>`
    )
    .join("") || `<tr><td colspan="21" class="muted" style="text-align:center;padding:24px">Tidak ada lead</td></tr>`;
  $("#leads-body").innerHTML = rows;
  renderSortIndicators();

  // status header select-all (tercentang / indeterminate)
  const selAll = $("#sel-all");
  syncSelAll(selAll);

  const lastPage = Math.max(1, Math.ceil(r.total / r.size));
  $("#pg-info").textContent = `Hal. ${r.page} / ${lastPage} — ${r.total} lead`;
  $("#pg-prev").disabled = r.page <= 1;
  $("#pg-next").disabled = r.page >= lastPage;

  document.querySelectorAll(".lead-check").forEach((cb) =>
    cb.addEventListener("change", () => {
      const id = parseInt(cb.dataset.id, 10);
      if (cb.checked) selectedLeads.add(id);
      else selectedLeads.delete(id);
      syncSelAll(selAll);
      updateBulkBar();
    })
  );

  document.querySelectorAll("[data-del]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const ok = await confirmDialog("Hapus lead ini secara permanen?");
      if (!ok) return;
      try {
        await api(`/api/leads/${btn.dataset.del}`, { method: "DELETE" });
        selectedLeads.delete(parseInt(btn.dataset.del, 10));
        updateBulkBar();
        loadLeads();
      } catch (ex) { alert("Hapus gagal: " + ex.message); }
    })
  );

  document.querySelectorAll("[data-edit]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const item = currentItems.find((x) => x.id === parseInt(btn.dataset.edit, 10));
      openEditModal(item);
    })
  );

  document.querySelectorAll("[data-rclear]").forEach((btn) =>
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const id = parseInt(btn.dataset.rclear, 10);
      const field = btn.dataset.rfield;
      const val = btn.dataset.rval || null;
      quickClearResultItem(id, field, val);
    })
  );

  document.querySelectorAll("[data-status]").forEach((sel) => {
    sel.dataset.prev = sel.value;
    sel.addEventListener("change", async () => {
      const ok = await confirmDialog(`Ubah status lead menjadi "${sel.value}"?`, false);
      if (!ok) { sel.value = sel.dataset.prev; return; }
      try {
        await api(`/api/leads/${sel.dataset.status}`, { method: "PATCH", body: { status: sel.value } });
        sel.dataset.prev = sel.value;
        loadLeads();
      } catch (ex) {
        sel.value = sel.dataset.prev;
        alert("Gagal mengubah status: " + ex.message);
      }
    });
  });
  updateBulkBar();
}

// ---- Results: seleksi baris & hapus ----
const selectedLeads = new Set();
let currentPageIds = [];

function syncSelAll(selAll) {
  const all = currentPageIds.length > 0 && currentPageIds.every((id) => selectedLeads.has(id));
  const some = currentPageIds.some((id) => selectedLeads.has(id));
  selAll.checked = all;
  selAll.indeterminate = !all && some;
}

function updateBulkBar() {
  $("#bulk-bar").classList.toggle("hidden", selectedLeads.size === 0);
  $("#bulk-count").textContent = `${selectedLeads.size} lead dipilih`;
}

function linkCell(url, label) {
  if (!url) return "-";
  const text = label || url;
  return `<a class="cell-url" href="${esc(url)}" target="_blank" rel="noopener" title="${esc(url)}">${esc(text)}</a>`;
}

function igLabel(url) {
  return url.replace(/^https?:\/\/(www\.)?instagram\.com\//i, "@").replace(/\/+$/, "");
}

$("#sel-all").addEventListener("change", () => {
  const on = $("#sel-all").checked;
  currentPageIds.forEach((id) => (on ? selectedLeads.add(id) : selectedLeads.delete(id)));
  document.querySelectorAll(".lead-check").forEach((cb) => { cb.checked = on; });
  updateBulkBar();
});

$("#btn-bulk-delete").addEventListener("click", async () => {
  const ids = [...selectedLeads];
  if (!ids.length) return;
  const ok = await confirmDialog(`Hapus ${ids.length} lead terpilih secara permanen?`);
  if (!ok) return;
  try {
    await api("/api/leads/delete-bulk", { method: "POST", body: { ids } });
    selectedLeads.clear();
    updateBulkBar();
    loadLeads();
  } catch (ex) { alert("Hapus gagal: " + ex.message); }
});

// Batal / ✕ — kosongkan seleksi
$("#btn-clear-selection").addEventListener("click", () => {
  selectedLeads.clear();
  document.querySelectorAll(".lead-check").forEach((cb) => (cb.checked = false));
  const selAll = $("#sel-all");
  selAll.checked = false;
  selAll.indeterminate = false;
  updateBulkBar();
});

// ---- Modal konfirmasi custom (pop up konfirmasi perubahan data) ----
let confirmResolve = null;

function confirmDialog(message, danger = true) {
  $("#confirm-msg").textContent = message;
  $("#confirm-ok").classList.toggle("btn-danger", danger);
  $("#confirm-ok").classList.toggle("btn-primary", !danger);
  $("#confirm-overlay").classList.remove("hidden");
  return new Promise((resolve) => { confirmResolve = resolve; });
}

function settleConfirm(val) {
  $("#confirm-overlay").classList.add("hidden");
  if (confirmResolve) { confirmResolve(val); confirmResolve = null; }
}

$("#confirm-ok").addEventListener("click", () => settleConfirm(true));
$("#confirm-cancel").addEventListener("click", () => settleConfirm(false));
$("#confirm-overlay").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) settleConfirm(false);
});

// ---- Modal edit data ----
function openEditModal(leadObj) {
  if (!leadObj) return;
  const l = leadObj;
  $("#edit-id").value = l.id;
  const kodeEl = $("#edit-kode");
  if (kodeEl) kodeEl.value = l.kode || ("LD-" + l.id);
  EDITABLE_FIELDS.forEach((f) => {
    const el = $(`#edit-${f}`);
    if (el) el.value = l[f] || "";
  });
  $("#edit-status").value = l.status || "New";
  $("#edit-error").classList.add("hidden");
  $("#modal-overlay").classList.remove("hidden");
  $("#edit-nama_instansi").focus();
}

function closeEditModal() {
  $("#modal-overlay").classList.add("hidden");
}

// Reload data halaman yang sedang aktif setelah edit tersimpan
function reloadActivePage() {
  if (!$("#page-dedup").classList.contains("hidden")) loadDedup();
  else loadLeads();
}

$("#modal-close").addEventListener("click", closeEditModal);
$("#edit-cancel").addEventListener("click", closeEditModal);
$("#modal-overlay").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeEditModal();
});

$("#edit-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = $("#edit-id").value;
  if (!id) return;
  const payload = { status: $("#edit-status").value };
  EDITABLE_FIELDS.forEach((f) => {
    const el = $(`#edit-${f}`);
    if (el) payload[f] = el.value;
  });
  const ok = await confirmDialog("Simpan perubahan data lead ini?", false);
  if (!ok) return;
  try {
    await api(`/api/leads/${id}`, { method: "PATCH", body: payload });
    closeEditModal();
    reloadActivePage();
    if (typeof window._onModalSaveCallback === "function") {
      try { window._onModalSaveCallback(); } catch (_) {}
      window._onModalSaveCallback = null;
    }
  } catch (ex) {
    const err = $("#edit-error");
    err.textContent = "Gagal menyimpan: " + ex.message;
    err.classList.remove("hidden");
  }
});

// ---- Filter: Enter → Terapkan, Reset, Sorting ----
["f-search", "f-category", "f-kota", "f-status"].forEach((id) => {
  const el = $(`#${id}`);
  if (!el) return;
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); $("#btn-filter").click(); }
  });
});

$("#btn-reset-filter").addEventListener("click", () => {
  $("#f-search").value = "";
  if ($("#f-category")) $("#f-category").value = "";
  $("#f-kota").value = "";
  $("#f-status").value = "";
  leadState.sort_by = "updated_at";
  leadState.sort_dir = "desc";
  leadState.page = 1;
  // kosongkan juga seleksi baris
  selectedLeads.clear();
  document.querySelectorAll(".lead-check").forEach((cb) => (cb.checked = false));
  const selAll = $("#sel-all");
  selAll.checked = false;
  selAll.indeterminate = false;
  updateBulkBar();
  renderSortIndicators();
  loadLeads();
});

// Sorting semua kolom: klik header → toggle asc/desc
document.querySelectorAll("#page-results th.th-sort").forEach((th) =>
  th.addEventListener("click", () => {
    const key = th.dataset.sort;
    if (leadState.sort_by === key) {
      leadState.sort_dir = leadState.sort_dir === "asc" ? "desc" : "asc";
    } else {
      leadState.sort_by = key;
      leadState.sort_dir = "asc";
    }
    leadState.page = 1;
    renderSortIndicators();
    loadLeads();
  })
);

$("#btn-filter").addEventListener("click", () => { leadState.page = 1; loadLeads(); });
$("#pg-prev").addEventListener("click", () => { leadState.page--; loadLeads(); });
$("#pg-next").addEventListener("click", () => { leadState.page++; loadLeads(); });

$("#btn-export").addEventListener("click", async () => {
  try {
    const res = await fetch(`/api/export?${leadParams()}`, { credentials: "same-origin" });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      alert(j.detail || "Export gagal");
      return;
    }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (res.headers.get("content-disposition") || "").match(/filename="?([^"]+)"?/)?.[1] || "leads.xlsx";
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (ex) { alert("Export gagal: " + ex.message); }
});

$("#btn-export-csv").addEventListener("click", async () => {
  try {
    const res = await fetch(`/api/export-csv?${leadParams()}`, { credentials: "same-origin" });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      alert(j.detail || "Export CSV gagal");
      return;
    }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (res.headers.get("content-disposition") || "").match(/filename=\"?([^\"]+)\"?/)?.[1] || "leads.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (ex) { alert("Export CSV gagal: " + ex.message); }
});

$("#btn-import").addEventListener("click", () => $("#import-file").click());
$("#import-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await api(`/api/import?source=${encodeURIComponent(file.name.replace(/\.csv$/i, ""))}`, {
      method: "POST",
      body: fd,
    });
    alert(`Import selesai: ${r.created ?? 0} baru, ${r.updated ?? 0} diperbarui.`);
    loadLeads();
  } catch (ex) { alert("Import gagal: " + ex.message); }
  e.target.value = "";
});

function reloadActivePage() {
  const hash = location.hash.replace("#", "") || "dashboard";
  if (hash === "results") loadLeads();
  else if (hash === "dedup") loadDedup();
  else if (hash === "dashboard") loadDashboard();
  else if (hash === "enrichment") loadEnrichmentJobs();
}

// ---- Review Duplikat page ----
let dedupGroups = [];
const dedupSorts = {}; // groupKey -> { key, dir }

async function loadDedup() {
  const r = await api("/api/duplicates");
  const groups = r.groups || [];
  dedupGroups = groups;
  const badge = $("#dedup-badge");
  if (badge) {
    badge.classList.toggle("hidden", groups.length === 0);
    badge.textContent = groups.length || "";
  }
  $("#dedup-empty").classList.toggle("hidden", groups.length > 0);
  $("#dedup-list").innerHTML = groups.map(renderGroup).join("");

  bindDedupEvents();
}

function bindDedupEvents() {
  document.querySelectorAll("[data-resolve]").forEach((btn) =>
    btn.addEventListener("click", () => resolveGroup(btn))
  );

  // Tombol quick clear field (hapus nilai pemicu duplikat secara instan)
  document.querySelectorAll("[data-qclear]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const id = parseInt(btn.dataset.qclear, 10);
      const field = btn.dataset.qfield;
      const label = btn.dataset.qlabel || field;
      quickClearLeadField(id, field, label);
    })
  );

  // Tombol hapus 1 lead baris ini
  document.querySelectorAll("[data-ddel]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const id = parseInt(btn.dataset.ddel, 10);
      const name = btn.dataset.dname || "Lead";
      deleteSingleLeadInGroup(id, name);
    })
  );

  // Tombol pensil edit per baris member
  document.querySelectorAll("[data-dedit]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const id = parseInt(btn.dataset.dedit, 10);
      const g = btn.closest("[data-group]");
      const members = (dedupGroups.find((x) => x.key === g?.dataset.group) || {}).member_data || [];
      const item = members.find((m) => m.id === id);
      if (item) {
        openEditModal(item);
        window._onModalSaveCallback = loadDedup;
      }
    })
  );

  // Klik header kolom grup → sorting client-side
  document.querySelectorAll("#dedup-list .dup-group").forEach((card) => {
    const g = dedupGroups.find((x) => x.key === card.dataset.group);
    if (!g) return;
    card.querySelectorAll("th[data-dsort]").forEach((th) =>
      th.addEventListener("click", () => {
        const key = th.dataset.dsort;
        const cur = dedupSorts[g.key];
        if (cur && cur.key === key) {
          cur.dir = cur.dir === "asc" ? "desc" : "asc";
        } else {
          dedupSorts[g.key] = { key, dir: "asc" };
        }
        renderDedupGroupBody(card, g);
      })
    );
  });
}

function dedupTableHead() {
  return `<tr>
      <th style="width:36px; text-align:center;">No</th>
      <th class="th-sort col-instansi" data-dsort="nama_instansi">Nama Instansi <span class="sort-arrow" aria-hidden="true"></span></th>
      <th class="th-sort col-kategori" data-dsort="kategori">Bidang Usaha / Kategori <span class="sort-arrow" aria-hidden="true"></span></th>
      <th class="th-sort col-alamat" data-dsort="alamat">Alamat Lengkap <span class="sort-arrow" aria-hidden="true"></span></th>
      <th class="th-sort col-kota" data-dsort="kota">Kota <span class="sort-arrow" aria-hidden="true"></span></th>
      <th class="th-sort col-gmaps" data-dsort="link_gmaps">Link Gmaps <span class="sort-arrow" aria-hidden="true"></span></th>
      <th class="th-sort col-dups" data-dsort="dup_fields">Data Terindikasi Duplikat (Kontak & Pemicu) <span class="sort-arrow" aria-hidden="true"></span></th>
      <th class="col-aksi">Aksi</th>
    </tr>`;
}

function formatGmapsTruncated(url, maxLen = 75) {
  if (!url) return `<span class="muted">-</span>`;
  const full = String(url);
  if (full.length <= maxLen) {
    return `<a href="${esc(full)}" target="_blank" rel="noopener noreferrer" class="link-gmaps-truncated" title="${esc(full)}">[${esc(full)}]</a>`;
  }
  const prefix = full.substring(0, maxLen);
  return `<a href="${esc(full)}" target="_blank" rel="noopener noreferrer" class="link-gmaps-truncated" title="${esc(full)}">[${esc(prefix)}].................</a>`;
}

function renderDupItemBadge(leadId, fieldName, fieldLabel, val, isTrigger) {
  if (!val) return "";
  let icon = "";
  if (fieldName === "website") icon = GLOBE_SVG;
  else if (fieldName === "instagram") icon = INSTAGRAM_SVG;
  else if (fieldName === "tiktok") icon = TIKTOK_SVG;
  else if (fieldName === "facebook") icon = FACEBOOK_SVG;
  else if (fieldName === "linkedin") icon = LINKEDIN_SVG;
  else if (fieldName === "twitter_x") icon = TWITTER_SVG;
  else if (fieldName === "sosmed") icon = GLOBE_SVG;
  else if (fieldName === "telp") icon = PHONE_SVG;
  else if (fieldName === "email") icon = MAIL_SVG;
  else if (fieldName === "npsn") icon = ID_CARD_SVG;

  const cls = isTrigger ? "dup-field-chip is-duplicate" : "dup-field-chip";
  const clearBtn = isTrigger
    ? `<button type="button" class="btn-chip-clear" data-qclear="${leadId}" data-qfield="${fieldName}" data-qlabel="${fieldLabel}" title="Kosongkan ${fieldLabel} dari baris ini agar tidak terduplikasi">${CLOSE_SVG} <span>Hapus ${fieldLabel}</span></button>`
    : `<button type="button" class="btn-chip-clear-mini" data-qclear="${leadId}" data-qfield="${fieldName}" data-qlabel="${fieldLabel}" title="Kosongkan ${fieldLabel}">${CLOSE_SVG}</button>`;

  let displayVal = esc(val);
  if (["website", "sosmed", "instagram", "tiktok", "facebook", "linkedin", "twitter_x"].includes(fieldName)) {
    displayVal = `<a href="${esc(val)}" target="_blank" rel="noopener noreferrer">${esc(val)}</a>`;
  }

  return `
    <div class="${cls}">
      <span class="dup-chip-icon" aria-hidden="true">${icon}</span>
      <span class="dup-chip-label">${esc(fieldLabel)}:</span>
      <span class="dup-chip-val" title="${esc(val)}">${displayVal}</span>
      ${clearBtn}
    </div>`;
}

function renderDedupRows(g) {
  const sort = dedupSorts[g.key];
  const members = sort ? sortByKey(g.member_data, sort.key, sort.dir) : g.member_data;
  const triggerField = g.trigger_field || "";

  return members
    .map((m, i) => {
      // Kumpulkan badge field yang terisi
      const badges = [];
      if (m.website) badges.push(renderDupItemBadge(m.id, "website", "Web", m.website, triggerField === "website"));
      if (m.instagram) badges.push(renderDupItemBadge(m.id, "instagram", "Instagram", m.instagram, triggerField === "instagram"));
      if (m.tiktok) badges.push(renderDupItemBadge(m.id, "tiktok", "TikTok", m.tiktok, triggerField === "tiktok"));
      if (m.facebook) badges.push(renderDupItemBadge(m.id, "facebook", "Facebook", m.facebook, triggerField === "facebook"));
      if (m.linkedin) badges.push(renderDupItemBadge(m.id, "linkedin", "LinkedIn", m.linkedin, triggerField === "linkedin"));
      if (m.twitter_x) badges.push(renderDupItemBadge(m.id, "twitter_x", "Twitter/X", m.twitter_x, triggerField === "twitter_x"));
      if (m.sosmed) badges.push(renderDupItemBadge(m.id, "sosmed", "Medsos", m.sosmed, triggerField === "sosmed"));
      if (m.telp) badges.push(renderDupItemBadge(m.id, "telp", "Telp", m.telp, triggerField === "telp"));
      if (m.email) badges.push(renderDupItemBadge(m.id, "email", "Email", m.email, triggerField === "email"));
      if (m.npsn) badges.push(renderDupItemBadge(m.id, "npsn", "NPSN", m.npsn, triggerField === "npsn"));

      const dupContent = badges.length
        ? `<div class="dup-items-box">${badges.join("")}</div>`
        : `<span class="muted" style="font-size:12px">Nama &amp; Lokasi Mirip</span>`;

      const gmapsLink = `<div class="dup-link-wrap">${formatGmapsTruncated(m.link_gmaps)}</div>`;

      return `
    <tr>
      <td class="mono" style="text-align:center;">${i + 1}</td>
      <td class="col-instansi">
        <div style="font-weight:600; line-height:1.3;">${esc(m.nama_instansi)}</div>
        <div class="muted" style="font-size:11px; margin-top:2px;">Kode: <span class="mono font-bold" style="color:var(--primary)">${esc(m.kode || ('LD-' + m.id))}</span></div>
      </td>
      <td class="col-kategori"><span class="tag tag-src">${esc(m.kategori || "-")}</span></td>
      <td class="col-alamat" title="${esc(m.alamat || "-")}">${esc(m.alamat || "-")}</td>
      <td class="col-kota">${esc(m.kota || "-")}</td>
      <td class="col-gmaps">${gmapsLink}</td>
      <td class="col-dups">${dupContent}</td>
      <td class="col-aksi">
        <div class="row-actions" style="justify-content:center; gap:4px;">
          <button type="button" class="btn-action-icon btn-action-edit" data-dedit="${m.id}" aria-label="Edit lead ${esc(m.nama_instansi)}" title="Koreksi manual">${PENCIL_SVG}</button>
          <button type="button" class="btn-action-icon btn-action-delete" data-ddel="${m.id}" data-dname="${esc(m.nama_instansi)}" aria-label="Hapus lead ${esc(m.nama_instansi)}" title="Hapus baris lead ini">${TRASH_SVG}</button>
        </div>
      </td>
    </tr>`;
    })
    .join("");
}

function renderDedupGroupBody(card, g) {
  const tbody = card.querySelector("tbody");
  if (tbody) tbody.innerHTML = renderDedupRows(g);
  const sort = dedupSorts[g.key];
  card.querySelectorAll("th[data-dsort]").forEach((th) => {
    const active = sort && th.dataset.dsort === sort.key;
    th.classList.toggle("sorted", !!active);
    const arrow = th.querySelector(".sort-arrow");
    if (arrow) arrow.textContent = active ? (sort.dir === "asc" ? "▲" : "▼") : "";
  });

  // Rebind tombol di card ini
  card.querySelectorAll("[data-qclear]").forEach((btn) =>
    btn.addEventListener("click", () => {
      quickClearLeadField(parseInt(btn.dataset.qclear, 10), btn.dataset.qfield, btn.dataset.qlabel);
    })
  );
  card.querySelectorAll("[data-ddel]").forEach((btn) =>
    btn.addEventListener("click", () => {
      deleteSingleLeadInGroup(parseInt(btn.dataset.ddel, 10), btn.dataset.dname);
    })
  );
  card.querySelectorAll("[data-dedit]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const id = parseInt(btn.dataset.dedit, 10);
      const item = (g.member_data || []).find((m) => m.id === id);
      if (item) {
        openEditModal(item);
        window._onModalSaveCallback = loadDedup;
      }
    })
  );
}

function formatGroupTitle(g) {
  const trigger = g.trigger_field || "";
  const val = g.trigger_value ? ` (${g.trigger_value})` : "";
  if (trigger === "website") return `Grup Website Sama${val}`;
  if (trigger === "telp") return `Grup No. Telepon Sama${val}`;
  if (trigger === "email") return `Grup Email Sama${val}`;
  if (trigger === "npsn") return `Grup NPSN Sama${val}`;
  if (trigger === "nama_instansi") return `Grup Nama & Kota Sama`;
  return `Grup Duplikat ${esc(g.reason.join(", ") || "mirip")}`;
}

function renderGroup(g) {
  return `
    <div class="card dup-group" data-group="${esc(g.key)}">
      <div class="dup-head">
        <b>${esc(formatGroupTitle(g))}</b>
        <span class="dup-reason">${esc(g.reason.join(", ") || "mirip")} (skor ${g.score})</span>
      </div>
      <div class="table-card">
        <div class="table-scroll">
        <table>
          <thead>${dedupTableHead()}</thead>
          <tbody>${renderDedupRows(g)}</tbody>
        </table>
        </div>
      </div>
    </div>`;
}

async function quickClearLeadField(leadId, fieldName, fieldLabel) {
  const ok = await confirmDialog(`Kosongkan ${fieldLabel} dari instansi ini agar tidak terduplikasi?`, false);
  if (!ok) return;

  try {
    await api(`/api/leads/${leadId}`, {
      method: "PATCH",
      body: { [fieldName]: "" },
    });
    await loadDedup();
  } catch (err) {
    alert("Gagal mengosongkan data: " + err.message);
  }
}

async function deleteSingleLeadInGroup(leadId, leadName) {
  const ok = await confirmDialog(`Hapus instansi "${leadName}" (#${leadId}) dari database?`);
  if (!ok) return;

  try {
    await api(`/api/leads/${leadId}`, { method: "DELETE" });
    await loadDedup();
  } catch (err) {
    alert("Gagal menghapus lead: " + err.message);
  }
}

async function resolveGroup(btn) {
  const card = btn.closest("[data-group]");
  const gKey = card.dataset.group;
  const memberIds = [...card.querySelectorAll('input[type="radio"]')].map((r) => parseInt(r.value, 10));
  const winnerId = parseInt(card.querySelector('input[type="radio"]:checked')?.value, 10) || null;
  const action = btn.dataset.resolve;

  if (action !== "delete_all" && !winnerId) {
    alert("Pilih lead yang dipertahankan terlebih dahulu.");
    return;
  }

  const fieldChoices = {};
  if (action === "merge") {
    card.querySelectorAll("[data-field]").forEach((s) => {
      if (s.value) fieldChoices[s.dataset.field] = parseInt(s.value, 10);
    });
  }

  try {
    await api("/api/duplicates/resolve", {
      method: "POST",
      body: { group_key: gKey, member_ids: memberIds, action, winner_id: winnerId, field_choices: fieldChoices },
    });
    await loadDedup();
  } catch (ex) {
    alert("Gagal: " + ex.message);
  }
}

$("#btn-dedup-reload").addEventListener("click", loadDedup);

// ---- Init ----
bootstrap();
