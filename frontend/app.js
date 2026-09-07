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
  }, 3000);
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
        max_results: parseInt($("#scrape-max").value, 10) || 100,
      },
    });
    addKeywordHistory(keyword); // catat ke Riwayat Kategori (unique)
    msg.textContent = `Scrape GMaps dimulai (Job ${job.id.slice(0, 8)}) — pantau progres di bawah.`;
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
  dapodik: "Dapodik Kemdikbud",
  jobstreet: "Jobstreet",
  glints: "Glints",
  lpse: "LPSE Daerah",
};
const FIELD_LABELS = {
  npsn: "NPSN",
  nama_kepsek: "Nama Kepsek",
  posisi_rekrutmen: "Posisi Rekrutmen",
  deskripsi_it: "Deskripsi IT",
  penanggung_jawab: "Penanggung Jawab",
};

// Muat meta enrichment dinamis: dropdown sumber manual (hanya yang scraper-nya
// aktif yang bisa dipilih) + tabel "Field yang Diisi per Sumber Enrichment".
async function loadEnrichmentMeta() {
  try {
    const s = await api("/api/sources");
    const list = s.enrichment_sources || [];
    enrichSourcesCache = list; // dipakai picker inline per baris job

    const sel = $("#enrich-source");
    if (sel) {
      sel.innerHTML =
        '<option value="">Auto (berdasarkan kategori)</option>' +
        list
          .map((e) => {
            const label = SOURCE_LABELS[e.source] || e.source;
            return e.available
              ? `<option value="${esc(e.source)}">${esc(label)}</option>`
              : `<option value="${esc(e.source)}" disabled>${esc(label)} — scraper belum tersedia (M2)</option>`;
          })
          .join("");
    }

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

// ---- Sinkronisasi Kategori ↔ Kota (data binding dari tabel Results) ----
// Opsi diambil dinamis dari /api/enrich/options → hanya kombinasi (Kategori,
// Kota) yang benar-benar punya data seed (gmaps) di Results yang tersedia.
// Saat Kategori dipilih/ketik, opsi Kota otomatis tersaring (filtered) ke kota
// yang memiliki data kategori tsb → mencegah enrichment kombinasi kosong.
const enrichOptions = { categories: [], cities_by_category: {}, all_cities: [] };
// Cache daftar sumber enrichment (dari /api/sources) untuk picker inline per baris job
let enrichSourcesCache = [];
// Cache job terakhir yang dirender (untuk tombol Enrich/Ulangi per baris)
let lastJobs = [];

function enrichCitiesFor(categoryRaw) {
  const map = enrichOptions.cities_by_category || {};
  const cat = String(categoryRaw || "").trim().toLowerCase();
  if (!cat) return [];
  if (Object.prototype.hasOwnProperty.call(map, cat)) return map[cat];
  const key = Object.keys(map).find((k) => k.toLowerCase() === cat);
  return key ? map[key] : [];
}

function renderEnrichOptions() {
  // Kategori = dropdown (select) — opsi dinamis dari data seed (Results).
  const catSel = $("#enrich-category");
  if (catSel) {
    const prev = catSel.value || "";
    catSel.innerHTML =
      '<option value="">— Pilih Kategori —</option>' +
      enrichOptions.categories
        .map((c) => `<option value="${esc(c)}">${esc(c)}</option>`)
        .join("");
    if (enrichOptions.categories.length) {
      // Pertahankan pilihan lama jika masih valid; jika kosong, preseleksi pertama
      catSel.value = enrichOptions.categories.includes(prev) ? prev : enrichOptions.categories[0];
    }
  }

  const catEl = $("#enrich-category");
  const selectedCat = catEl ? (catEl.value || "").trim() : "";
  const cities = enrichCitiesFor(selectedCat);
  const cityList = $("#enrich-city-list");
  if (cityList) {
    cityList.innerHTML = cities.map((c) => `<option value="${esc(c)}"></option>`).join("");
  }

  const cityInput = $("#enrich-city");
  // Preselect kota pertama saat kosong (dari kota valid utk kategori terpilih)
  if (cityInput && !cityInput.value.trim() && cities.length) {
    cityInput.value = cities[0];
  }
  // Kota terpilih tidak valid utk kategori yg dipilih → kosongkan (pilih ulang)
  if (cityInput && cities.length && cityInput.value.trim() &&
      !cities.some((c) => c.toLowerCase() === cityInput.value.trim().toLowerCase())) {
    cityInput.value = "";
  }

  const hint = $("#enrich-options-hint");
  if (hint) {
    if (!enrichOptions.categories.length) {
      hint.textContent = "Belum ada data seed di Results — jalankan Scrape (Google Maps) dulu, lalu kembali ke menu ini.";
      hint.className = "form-msg muted";
    } else {
      hint.textContent =
        `${enrichOptions.categories.length} kategori tersedia dari data seed (` +
        `${enrichOptions.all_cities.length} kota). Kota otomatis tersaring sesuai kategori terpilih.`;
      hint.className = "form-msg muted";
    }
  }
}

async function loadEnrichOptions(force = false) {
  try {
    const r = await api("/api/enrich/options");
    enrichOptions.categories = r.categories || [];
    enrichOptions.cities_by_category = r.cities_by_category || {};
    enrichOptions.all_cities = r.all_cities || [];
  } catch (_) { /* non-fatal */ }
  renderEnrichOptions();
}

// Re-render opsi Kota setiap kali kategori di dropdown diubah
document.addEventListener("DOMContentLoaded", () => {
  const catSel = $("#enrich-category");
  if (catSel) catSel.addEventListener("change", renderEnrichOptions);
});
if ($("#enrich-category")) renderEnrichOptions();

$("#btn-start-enrich")?.addEventListener("click", async () => {
  unlockAudio();
  const msg = $("#enrich-msg");
  msg.classList.add("hidden");
  try {
    const category = $("#enrich-category").value.trim();
    const city = $("#enrich-city").value.trim();
    if (!category) {
      msg.textContent = "Pilih kategori dari dropdown (opsi dari data seed di Results).";
      msg.style.color = "var(--danger)";
      msg.classList.remove("hidden");
      return;
    }
    if (!city) {
      msg.textContent = "Pilih / ketik kota (opsi otomatis tersaring sesuai kategori).";
      msg.style.color = "var(--danger)";
      msg.classList.remove("hidden");
      return;
    }
    if (!enrichOptions.categories.length) {
      msg.textContent = "Belum ada data seed di Results — jalankan Scrape (Google Maps) dulu sebelum enrichment.";
      msg.style.color = "var(--danger)";
      msg.classList.remove("hidden");
      return;
    }
    const allowedCities = enrichCitiesFor(category);
    if (!allowedCities.length) {
      msg.textContent = `Kategori '${category}' belum punya data seed di Results. Kategori tersedia: ${enrichOptions.categories.join(", ")}`;
      msg.style.color = "var(--danger)";
      msg.classList.remove("hidden");
      return;
    }
    if (!allowedCities.some((c) => c.toLowerCase() === city.toLowerCase())) {
      msg.textContent = `Kombinasi '${category}' + '${city}' tidak punya data seed di Results. Kota tersedia utk '${category}': ${allowedCities.join(", ")}`;
      msg.style.color = "var(--danger)";
      msg.classList.remove("hidden");
      return;
    }
    const job = await api("/api/enrich", {
      method: "POST",
      body: {
        category,
        city,
        enrichment_source: $("#enrich-source").value,
        max_results: parseInt($("#enrich-max").value, 10) || 100,
      },
    });
    msg.textContent = `Enrichment dimulai (Job ${job.id.slice(0, 8)}) — pantau progres di Riwayat Job.`;
    msg.classList.remove("hidden");
    startPolling();
    loadJobs();
  } catch (ex) {
    msg.textContent = ex.message;
    msg.style.color = "var(--danger)";
    msg.classList.remove("hidden");
  }
});

// ---- Load Enrichment Jobs ----
async function loadEnrichmentJobs(silent = false) {
  try {
    const r = await api("/api/jobs?limit=100");
    // Filter hanya job enrichment (bukan gmaps seed)
    const enrichJobs = (r.items || []).filter((j) => j.source !== "gmaps");
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

function renderEnrichmentJobs(jobs) {
  const fmtTime = (iso) =>
    iso ? new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "-";
  $("#enrich-jobs-body").innerHTML = jobs
    .map((j) => {
      const taken = (j.items_created || 0) + (j.items_updated || 0);
      return `
    <tr>
      <td class="mono">${fmtTime(j.started_at)}</td>
      <td><span class="tag tag-src">${esc(j.source)}</span></td>
      <td>${esc(j.category)}</td>
      <td>${esc(j.city)}</td>
      <td><span class="tag tag-${esc(j.status)}">${esc(j.status)}</span></td>
      <td>
        <div class="progress-track"><div class="progress-fill" style="width:${jobProgressPct(j)}%"></div></div>
        <span class="mono" style="font-size:11.5px;color:var(--muted)" title="${taken} lead field terisi">${jobProgressPct(j)}%</span>
      </td>
      <td class="mono">${j.total_found}${taken ? ` <span class="muted" style="font-size:11px">· ${taken} terambil</span>` : ""}</td>
      <td class="row-actions">
        ${j.status === "running" || j.status === "pending"
          ? `<button class="btn btn-ghost btn-sm" data-cancel="${j.id}">Stop</button>` : ""}
        <button class="btn btn-ghost-danger btn-sm" data-deljob="${j.id}" title="Hapus riwayat job">Hapus</button>
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
  document.querySelectorAll("#page-enrichment [data-deljob]").forEach((b) =>
    b.addEventListener("click", () => deleteJob(b.dataset.deljob, loadEnrichmentJobs))
  );
}

// Progress % = (Ditemukan / Maks. Hasil) × 100 — pembagi ikut input user,
// bukan 100 hardcoded. Cap 0–100 agar bar tidak overflow.
function jobProgressPct(j) {
  const max = parseInt(j.max_results, 10) || 0;
  const found = parseInt(j.total_found, 10) || 0;
  if (max <= 0) return Math.max(0, Math.min(100, parseInt(j.progress, 10) || 0));
  return Math.max(0, Math.min(100, Math.round((found / max) * 100)));
}

async function loadJobs(silent = false) {
  try {
    const r = await api("/api/jobs");
    // Sound saat transisi terminal (selesai -> done, gagal/cancel -> fail).
    // Gating `silent=true` (call dari polling) = hanya diputar lewat transition live,
    // bukan saat user buka ulang page scrape.
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
    const active = r.items.some((j) => j.status === "running" || j.status === "pending");
    if (active) startPolling(); else stopPolling();
  } catch (ex) {
    if (!silent) console.warn("loadJobs:", ex.message);
  }
}

function renderJobs(jobs) {
  lastJobs = jobs || [];
  const sorted = sortByKey(jobs, jobSort.key, jobSort.dir);
  const fmtTime = (iso) =>
    iso ? new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "-";
  const isTerminal = (j) => !["running", "pending"].includes(j.status);

  $("#jobs-body").innerHTML = sorted
    .map((j) => {
      const taken = (j.items_created || 0) + (j.items_updated || 0);
      const isSeed = j.source === "gmaps";
      const actions = [
        j.status === "running" || j.status === "pending"
          ? `<button class="btn btn-ghost btn-sm" data-cancel="${j.id}">Stop</button>` : "",
        isSeed && isTerminal(j)
          ? `<button class="btn btn-ghost btn-sm" data-enrich="${j.id}" title="Mulai enrichment utk kategori+kota job ini">⚡ Enrich</button>` : "",
        isTerminal(j)
          ? `<button class="btn btn-ghost btn-sm" data-rerun="${j.id}" title="Jalankan ulang job ini (aman — anti-duplikat / hanya isi field kosong)">↻ Ulangi</button>` : "",
        `<button class="btn btn-ghost-danger btn-sm" data-deljob="${j.id}" title="Hapus riwayat job">Hapus</button>`,
      ].join("");

      // Baris inline picker enrichment (expand di bawah job seed yang terminal)
      const enrichRow = isSeed && isTerminal(j)
        ? `<tr class="enrich-row hidden" data-enrichrow="${j.id}"><td colspan="8">
             <div class="enrich-inline">
               <span class="muted">Enrich <b>${esc(j.category)}</b> @ <b>${esc(j.city)}</b> — pilih sumber:</span>
               <select data-esrc="${j.id}">${enrichSourceOptions()}</select>
               <button class="btn btn-primary btn-sm" data-startenrich="${j.id}">Mulai Enrichment</button>
             </div>
             <p class="form-msg hidden" data-emsg="${j.id}"></p>
           </td></tr>`
        : "";

      return `
    <tr>
      <td class="mono">${fmtTime(j.started_at)}</td>
      <td><span class="tag tag-src">${esc(j.source)}</span></td>
      <td>${esc(j.category)}</td>
      <td>${esc(j.city)}</td>
      <td><span class="tag tag-${esc(j.status)}">${esc(j.status)}</span></td>
      <td>
        <div class="progress-track"><div class="progress-fill" style="width:${jobProgressPct(j)}%"></div></div>
        <span class="mono" style="font-size:11.5px;color:var(--muted)" title="Ditemukan ${j.total_found} dari maks. ${j.max_results}">${jobProgressPct(j)}%</span>
      </td>
      <td class="mono">${j.total_found}${taken ? ` <span class="muted" style="font-size:11px">· ${taken} terambil</span>` : ""}</td>
      <td class="row-actions">${actions}</td>
    </tr>${enrichRow}`;
    })
    .join("") || `<tr><td colspan="8" class="muted" style="text-align:center;padding:24px">Belum ada job</td></tr>`;

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
      const row = document.querySelector(`[data-enrichrow="${b.dataset.enrich}"]`);
      if (row) row.classList.toggle("hidden");
    })
  );
  document.querySelectorAll("#page-scrape [data-startenrich]").forEach((b) =>
    b.addEventListener("click", () => startInlineEnrich(b.dataset.startenrich))
  );
  document.querySelectorAll("#page-scrape [data-rerun]").forEach((b) =>
    b.addEventListener("click", () => rerunJob(b.dataset.rerun))
  );
}

function enrichSourceOptions() {
  return (
    '<option value="">Auto (berdasarkan kategori)</option>' +
    enrichSourcesCache
      .map((e) => {
        const label = SOURCE_LABELS[e.source] || e.source;
        return e.available
          ? `<option value="${esc(e.source)}">${esc(label)}</option>`
          : `<option value="${esc(e.source)}" disabled>${esc(label)} — belum tersedia</option>`;
      })
      .join("")
  );
}

// Mulai enrichment langsung dari baris job seed — kategori+kota ikut job,
// user hanya memilih sumber + maks hasil.
async function startInlineEnrich(jobId) {
  const job = lastJobs.find((j) => j.id === jobId);
  const row = document.querySelector(`[data-enrichrow="${jobId}"]`);
  const msg = row ? row.querySelector(`[data-emsg="${jobId}"]`) : null;
  if (!job || !msg) return;
  const source = row.querySelector(`[data-esrc="${jobId}"]`)?.value || "";
  msg.classList.add("hidden");
  try {
    // Tanpa max_results → enrichment memproses semua kandidat (ikut jumlah data seed)
    const newJob = await api("/api/enrich", {
      method: "POST",
      body: { category: job.category, city: job.city, enrichment_source: source },
    });
    msg.textContent = `✅ Enrichment dimulai (Job ${newJob.id.slice(0, 8)}) — lihat Riwayat Job / halaman Enrichment.`;
    msg.style.color = "var(--primary)";
    msg.classList.remove("hidden");
    startPolling();
    loadJobs();
  } catch (ex) {
    msg.textContent = ex.message;
    msg.style.color = "var(--danger)";
    msg.classList.remove("hidden");
  }
}

// Ulangi job (scrape/enrichment) dengan parameter yang sama.
// Aman diulang: seed pakai upsert anti-duplikat; enrichment hanya isi field kosong.
async function rerunJob(jobId) {
  const job = lastJobs.find((j) => j.id === jobId);
  if (!job) return;
  const ok = await confirmDialog(
    job.source === "gmaps"
      ? `Ulangi scrape '${job.category}' @ '${job.city}'? Data lama tidak akan dobel (anti-duplikat).`
      : `Ulangi enrichment ${job.source} untuk '${job.category}' @ '${job.city}'? Hanya field kosong yang diisi.`
  );
  if (!ok) return;
  try {
    if (job.source === "gmaps") {
      await api("/api/scrape", {
        method: "POST",
        body: { source: job.source, category: job.category, city: job.city, max_results: job.max_results || 100 },
      });
    } else {
      // Enrichment ulang: tanpa max (proses semua kandidat), aman (hanya isi field kosong)
      await api("/api/enrich", {
        method: "POST",
        body: { category: job.category, city: job.city, enrichment_source: job.source },
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
  "link_gmaps", "website", "sosmed", "npsn", "nama_kepsek",
  "posisi_rekrutmen", "deskripsi_it", "penanggung_jawab",
];
const PENCIL_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>`;

async function loadFilters() {
  try {
    const r = await api("/api/filters");
    // Sumber: gabungan registry + DB, hilangkan duplikat (Set)
    const uniqueSources = [...new Set(r.sources || [])];
    const sel = $("#f-source");
    const existing = new Set([...sel.options].map((o) => o.value));
    uniqueSources.forEach((s) => {
      if (!existing.has(s)) {
        const o = document.createElement("option");
        o.value = s;
        o.textContent = s.toUpperCase();
        sel.appendChild(o);
      }
    });
    // Kota: dropdown dari DB
    const uniqueCities = [...new Set(r.cities || [])];
    $("#f-kota").innerHTML =
      '<option value="">Semua kota</option>' +
      uniqueCities.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
    // Datalist untuk modal edit lead (kategori & kota dari DB)
    $("#kota-list").innerHTML = uniqueCities.map((c) => `<option value="${esc(c)}"></option>`).join("");
    const catOptions = [...new Set(r.categories || [])]
      .map((c) => `<option value="${esc(c)}"></option>`).join("");
    $("#kategori-list").innerHTML = catOptions;
    // Catatan: form Enrichment memakai /api/enrich/options (seed-based),
    // bukan /api/filters di sini — diisi oleh loadEnrichOptions().
  } catch (_) { /* non-fatal */ }
}

function leadParams() {
  return new URLSearchParams({
    search: $("#f-search").value.trim(),
    source: $("#f-source").value,
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

// Sel <td> dari Nama Instansi s.d. Sumber — dipakai tabel Results & Review Duplikat
function leadCells(l) {
  return `
      <td><b>${esc(l.nama_instansi)}</b></td>
      <td>${esc(l.kategori || "-")}</td>
      <td class="mono">${esc(l.telp || "-")}</td>
      <td class="mono">${esc(l.email || "-")}</td>
      <td>${esc(l.alamat || "-")}</td>
      <td>${esc(l.kota || "-")}</td>
      <td>${linkCell(l.link_gmaps, l.link_gmaps)}</td>
      <td>${linkCell(l.website, l.website)}</td>
      <td>${linkCell(l.sosmed, l.sosmed ? igLabel(l.sosmed) : "")}</td>
      <td class="mono">${esc(l.npsn || "-")}</td>
      <td>${esc(l.nama_kepsek || "-")}</td>
      <td>${esc(l.posisi_rekrutmen || "-")}</td>
      <td class="cell-trunc" title="${esc(l.deskripsi_it || "")}">${esc(l.deskripsi_it || "-")}</td>
      <td>${esc(l.penanggung_jawab || "-")}</td>
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
    .join("") || `<tr><td colspan="20" class="muted" style="text-align:center;padding:24px">Tidak ada lead</td></tr>`;
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
const TRASH_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/><path d="m19 6-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>`;

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
  } catch (ex) {
    const err = $("#edit-error");
    err.textContent = "Gagal menyimpan: " + ex.message;
    err.classList.remove("hidden");
  }
});

// ---- Filter: Enter → Terapkan, Reset, Sorting ----
["f-search", "f-source", "f-kota", "f-status"].forEach((id) => {
  const el = $(`#${id}`);
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); $("#btn-filter").click(); }
  });
});

$("#btn-reset-filter").addEventListener("click", () => {
  $("#f-search").value = "";
  $("#f-source").value = "";
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

// ---- Review Duplikat page ----
let dedupGroups = [];
const dedupSorts = {}; // groupKey -> { key, dir }

async function loadDedup() {
  const r = await api("/api/duplicates");
  const groups = r.groups;
  dedupGroups = groups;
  const badge = $("#dedup-badge");
  badge.classList.toggle("hidden", groups.length === 0);
  badge.textContent = groups.length || "";
  $("#dedup-empty").classList.toggle("hidden", groups.length > 0);
  $("#dedup-list").innerHTML = groups.map(renderGroup).join("");

  document.querySelectorAll("[data-resolve]").forEach((btn) =>
    btn.addEventListener("click", () => resolveGroup(btn))
  );

  // tombol pensil edit per baris member
  document.querySelectorAll("[data-dedit]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const id = parseInt(btn.dataset.dedit, 10);
      const g = btn.closest("[data-group]");
      const members = (dedupGroups.find((x) => x.key === g?.dataset.group) || {}).member_data || [];
      openEditModal(members.find((m) => m.id === id));
    })
  );

  // klik header kolom grup → sorting client-side
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

function renderDedupRows(g) {
  const sort = dedupSorts[g.key];
  const members = sort ? sortByKey(g.member_data, sort.key, sort.dir) : g.member_data;
  return members
    .map(
      (m, i) => `
    <tr>
      <td class="col-check"><input type="radio" name="winner-${esc(g.key)}" value="${m.id}" ${i === 0 ? "checked" : ""} aria-label="Jadikan lead #${m.id} (${esc(m.nama_instansi)}) sebagai pemenang" /></td>
      <td class="mono">${i + 1}</td>
      ${leadCells(m)}
      <td>${esc(m.status || "-")}</td>
      <td>
        <div class="row-actions">
          <button type="button" class="btn-icon btn-edit" data-dedit="${m.id}" aria-label="Edit lead ${esc(m.nama_instansi)}" title="Edit lead">${PENCIL_SVG}</button>
        </div>
      </td>
    </tr>`
    )
    .join("");
}

function dedupTableHead() {
  const cols = [
    ["nama_instansi", "Nama Instansi"],
    ["kategori", "Bidang Usaha / Kategori"],
    ["telp", "No. WA / Telepon"],
    ["email", "Alamat Email"],
    ["alamat", "Alamat Lengkap"],
    ["kota", "Kota"],
    ["link_gmaps", "Link Gmaps"],
    ["website", "Link Website"],
    ["sosmed", "Akun Media Sosial"],
    ["npsn", "NPSN"],
    ["nama_kepsek", "Nama Kepsek"],
    ["posisi_rekrutmen", "Posisi Rekrutmen"],
    ["deskripsi_it", "Deskripsi IT"],
    ["penanggung_jawab", "Penanggung Jawab"],
    ["link_source", "Link Kemendikdasmen"],
    ["source", "Sumber"],
    ["status", "Status"],
  ];
  return `<tr>
      <th class="col-check"><span class="sr-only">Pilih pemenang</span></th>
      <th>No</th>
      ${cols.map(([k, label]) => `<th class="th-sort" data-dsort="${k}">${label} <span class="sort-arrow" aria-hidden="true"></span></th>`).join("")}
      <th><span class="sr-only">Aksi</span></th>
    </tr>`;
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
  // bind ulang tombol edit
  card.querySelectorAll("[data-dedit]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const id = parseInt(btn.dataset.dedit, 10);
      openEditModal((g.member_data || []).find((m) => m.id === id));
    })
  );
}

function renderGroup(g) {
  return `
    <div class="card dup-group" data-group="${esc(g.key)}">
      <div class="dup-head">
        <b>Grup ${esc(g.key.split(":")[0])}</b>
        <span class="dup-reason">${esc(g.reason.join(", ") || "mirip")} (skor ${g.score})</span>
        <div class="dup-actions">
          <button class="btn btn-ghost btn-sm" data-resolve="delete_all">Hapus Semua</button>
          <button class="btn btn-ghost btn-sm" data-resolve="keep">Pertahankan Terpilih</button>
          <button class="btn btn-primary btn-sm" data-resolve="merge">Gabungkan</button>
        </div>
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
