"""Unit test core logic Enrichment (PRD v1.1 §5.3 + requirement menu Enrichment).

Memvalidasi:
1. Target lead diambil dari DB (seed gmaps) berdasar filter kategori & kota.
2. Hanya field yang KOSONG yang diisi; data yang sudah terisi TIDAK di-replace.
3. Enrichment TIDAK membuat lead baru (hasil yang tidak cocok hanya di-log).
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models import Category, City, Lead, ScrapeJob, Base
from backend.services import enrichment_service as enrich
from backend.services import storage_service as store


@pytest.fixture()
def db() -> Session:
    """Database SQLite in-memory — terisolasi dari MySQL/TiDB."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def _get_or_create(db: Session, model, name: str):
    """Auto-create master data Category/City + return objeknya."""
    found = db.query(model).filter(model.name == name).first()
    if found:
        return found
    obj = model(name=name)
    db.add(obj)
    db.flush()
    return obj


def _seed_lead(db: Session, nama: str, category: str, city: str, **extra) -> Lead:
    cat = _get_or_create(db, Category, category)
    ct = _get_or_create(db, City, city)
    lead = Lead(
        source="gmaps",
        nama_instansi=nama,
        category_id=cat.id,
        city_id=ct.id,
        **extra,
    )
    db.add(lead)
    db.commit()
    return lead


def test_find_incomplete_leads_filter_kategori_kota(db: Session):
    """Hanya lead seed yang cocok kategori+kota dan field-nya kosong yang jadi target."""
    _seed_lead(db, "SMP A", "sekolah", "salatiga")            # target: sekolah+salatiga, kosong
    _seed_lead(db, "SMP B", "sekolah", "semarang")            # kota beda → bukan target
    _seed_lead(db, "PT C", "corporate", "salatiga")       # kategori beda → bukan target
    _seed_lead(db, "SMP D", "sekolah", "salatiga",
               npsn="20328460", nama_kepsek="Budi", email="info@smp.sch.id", link_source="https://kemdikbud.go.id")  # field lengkap → bukan target

    found = enrich.find_incomplete_leads(db, source="dapodik", category="sekolah", city="salatiga")
    names = {l.nama_instansi for l in found}
    assert names == {"SMP A"}, f"expected hanya SMP A, got {names}"


def test_match_and_merge_hanya_isi_kosong_tidak_replace(db: Session):
    """Matching mengisi field kosong; field terisi tidak di-replace."""
    _seed_lead(db, "SMP N 1 Salatiga", "sekolah", "salatiga",
               email="old@smp.sch.id", nama_kepsek="")

    stats = enrich.match_and_merge(
        db,
        source="dapodik",
        raw_items=[{
            "nama_instansi": "SMP N 1 Salatiga",
            "kota": "salatiga",
            "npsn": "20328460",
            "nama_kepsek": "Drs. Afit",
            "email": "new@smp.sch.id",
        }],
        category="sekolah", city="salatiga",
    )
    lead = db.query(Lead).filter(Lead.nama_instansi == "SMP N 1 Salatiga").one()
    assert lead.npsn == "20328460"        # field kosong → terisi
    assert lead.nama_kepsek == "Drs. Afit" # field kosong → terisi
    assert lead.email == "old@smp.sch.id"  # field terisi → TIDAK replace
    assert stats["matched"] == 1
    # Tidak ada lead baru yang dibuat (hanya 1 baris seed).
    assert db.query(Lead).count() == 1


def test_match_and_merge_tidak_buat_lead_baru(db: Session):
    """Hasil enrichment yang tidak cocok hanya dilaporkan, tidak jadi lead baru."""
    _seed_lead(db, "Sekolah Maju Jaya", "sekolah", "salatiga")

    stats = enrich.match_and_merge(
        db,
        source="dapodik",
        raw_items=[{"nama_instansi": "Sekolah Tidak Ada", "kota": "salatiga",
                    "npsn": "12345678"}],
        category="sekolah", city="salatiga",
    )
    assert stats["matched"] == 0
    assert len(stats["unmatched"]) == 1
    assert db.query(Lead).count() == 1  # tetap 1, tidak ada lead "Sekolah Tidak Ada"


def test_list_categories_with_cities_distink_dan_filter_seed(db: Session):
    """Opsi dropdown Enrichment = nilai DISTINCT (Kategori→Kota) dari data seed gmaps."""
    _seed_lead(db, "Sekolah A", "sekolah", "salatiga")
    _seed_lead(db, "Sekolah B", "sekolah", "semarang")
    _seed_lead(db, "Sekolah Duplikat", "sekolah", "salatiga")   # kota duplikat → di-remove
    _seed_lead(db, "PT X", "corporate", "jakarta")
    # Lead non-seed (enrichment) TIDAK boleh menjadi opsi seed
    cat = db.query(Category).filter(Category.name == "corporate").first()
    ct = db.query(City).filter(City.name == "jakarta").first()
    db.add(Lead(source="dapodik", nama_instansi="PT X (job)", category_id=cat.id, city_id=ct.id))
    db.commit()

    by_cat = store.list_categories_with_cities(db, source="gmaps")
    assert by_cat == {
        "sekolah": ["salatiga", "semarang"],
        "corporate": ["jakarta"],
    }, f"mapping salah: {by_cat}"


# ---- Statistik "berapa yang terambil" (items_created/items_updated) ----

class _StubScraper:
    """Scraper palsu untuk unit test _run_seed/_run_enrichment."""

    def __init__(self, source="gmaps", category="umkm", city="salatiga", cancelled=False):
        self.source = source
        self.category = category
        self.city = city
        self.max_results = 100
        self._cancelled = cancelled

    def is_cancelled(self):
        return self._cancelled

    def is_alive(self):
        return True


@pytest.fixture()
def job_db() -> Session:
    """DB SQLite in-memory + 1 baris job 'perusahaan @ salatiga' + 1 lead seed."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        import uuid

        job = ScrapeJob(
            id=str(uuid.uuid4()), source="gmaps", category="perusahaan",
            city="salatiga", max_results=100, status="running",
        )
        session.add(job)
        session.flush()
        cat = Category(name="perusahaan")
        ct = City(name="salatiga")
        session.add_all([cat, ct])
        session.flush()
        session.add(Lead(
            source="gmaps", nama_instansi="PT Cari Data", category_id=cat.id,
            city_id=ct.id,
        ))
        session.commit()
        yield session
    finally:
        session.close()


def test_run_seed_mencatat_items_created_updated(job_db: Session):
    """Seed: items_created/items_updated = jumlah lead yang benar-benar tersimpan."""
    from backend.services.job_manager import JobManager

    job = job_db.query(ScrapeJob).first()
    jm = JobManager()

    raw = [
        {"nama_instansi": "PT Cari Data", "kota": "salatiga", "kategori": "perusahaan",
         "telp": "081234567890", "website": "https://caridata.id"},
        {"nama_instansi": "PT Baru Masuk", "kota": "salatiga", "kategori": "perusahaan"},
    ]
    jm._run_seed(job_db, job.id, _StubScraper(), raw)

    job_db.expire_all()
    job = job_db.query(ScrapeJob).first()
    # 1 update (PT Cari Data sudah ada) + 1 create (PT Baru Masuk)
    assert job.items_created == 1, f"created salah: {job.items_created}"
    assert job.items_updated == 1, f"updated salah: {job.items_updated}"
    assert job.status == "completed"
    # Lead tetap 2 (tidak ada duplikat)
    assert job_db.query(Lead).count() == 2


def test_run_enrichment_mencatat_items_matched(job_db: Session):
    """Enrichment: items_created = jumlah lead yang field-nya terisi (matched)."""
    from backend.services.job_manager import JobManager

    job = job_db.query(ScrapeJob).first()
    jm = JobManager()

    raw = [{
        "nama_instansi": "PT Cari Data", "kota": "salatiga",
        "npsn": "20328460",
    }]
    jm._run_enrichment(job_db, job.id, _StubScraper(source="dapodik", category="perusahaan"), raw)

    job_db.expire_all()
    job = job_db.query(ScrapeJob).first()
    lead = job_db.query(Lead).filter(Lead.nama_instansi == "PT Cari Data").one()
    assert lead.npsn == "20328460"
    assert job.items_created == 1  # 1 lead terisi
    assert job.items_updated == 0
    assert job.status == "completed"


def test_get_job_incomplete_leads(job_db: Session):
    """Endpoint /jobs/{job_id}/incomplete mengembalikan lead seed yang belum lengkap."""
    from backend.controllers.scrape_routes import get_job_incomplete_leads

    # Buat job enrichment dapodik
    job = store.create_job(job_db, "dapodik", "sekolah", "salatiga", 100)
    # Seed 1 sekolah belum ada npsn & kepsek
    _seed_lead(job_db, "SMP N 1 Salatiga", "sekolah", "salatiga")

    res = get_job_incomplete_leads(job.id, _={}, db=job_db)
    assert res["job_id"] == job.id
    assert res["total"] >= 1
    found = [x for x in res["items"] if x["nama_instansi"] == "SMP N 1 Salatiga"]
    assert len(found) == 1
    assert "npsn" in found[0]["missing_fields"]
    assert "nama_kepsek" in found[0]["missing_fields"]


def test_generate_job_id_format():
    """Format ID job harus SCRP_{kategori[:14]}_{YYYYMMDD_HHMMSS} dan panjang <= 35."""
    from backend.services.storage_service import generate_job_id

    jid1 = generate_job_id("sekolah")
    assert jid1.startswith("SCRP_sekolah_")
    assert len(jid1) <= 35

    jid2 = generate_job_id("vendor pengadaan barang & jasa")
    assert jid2.startswith("SCRP_vendor_pengada_")
    assert len(jid2) <= 35


def test_find_or_create_job_creates_new_when_no_job_id(job_db: Session):
    """Mulai scrape baru tanpa job_id harus selalu membuat baris baru, bukan menimpa yang lama."""
    job1 = store.find_or_create_job(job_db, "gmaps", "sekolah", "salatiga", 50)
    job1.status = "completed"
    job_db.commit()

    # Mulai scrape kedua dengan kategori & kota yang sama
    job2 = store.find_or_create_job(job_db, "gmaps", "sekolah", "salatiga", 50)
    assert job2.id != job1.id
    assert job2.id.startswith("SCRP_sekolah_")

    # Pastikan kedua job ada di database
    all_jobs = job_db.query(ScrapeJob).filter(ScrapeJob.category == "sekolah").all()
    assert len(all_jobs) == 2


def test_find_or_create_job_updates_when_job_id_provided(job_db: Session):
    """Aksi Ulangi / Lengkapi yang mengirimkan job_id harus meng-update job yang bersangkutan."""
    job = store.create_job(job_db, "gmaps", "umkm", "salatiga", 10)
    job.status = "cancelled"
    job.progress = 5
    job_db.commit()

    # Rerun/update dengan job_id
    updated = store.find_or_create_job(job_db, "gmaps", "umkm", "salatiga", 25, job_id=job.id)
    assert updated.id == job.id
    assert updated.status == "pending"
    assert updated.max_results == 25
    assert updated.progress == 0


def test_delete_job_removes_from_db(job_db: Session):
    """Hapus job harus menghapus row dari tabel scrape_jobs."""
    job = store.create_job(job_db, "gmaps", "retail", "salatiga", 10)
    jid = job.id
    assert store.get_job(job_db, jid) is not None

    deleted_count = store.delete_job(job_db, jid)
    assert deleted_count == 1
    assert store.get_job(job_db, jid) is None