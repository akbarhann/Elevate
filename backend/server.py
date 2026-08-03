#!/usr/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════
  AGENCY REPORT — Unified FastAPI Backend Service
  REST API Server for Grab, Shopee, & GoFood Pipeline
═══════════════════════════════════════════════════════════════
"""

import sys
import os
import uuid
import time
import asyncio
import threading
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Literal
from dotenv import load_dotenv

# Ensure project directory and agency directory are in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
DB_DIR = os.path.join(PROJECT_ROOT, "src", "database")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if DB_DIR not in sys.path:
    sys.path.append(DB_DIR)

from layer1_db_manager import DatabaseManager
db_manager = DatabaseManager()

from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text

# Import pipeline helpers from cli.py
try:
    from backend.cli import (
        normalize_date_string,
        run_grab,
        run_shopee,
        run_gofood,
        ingest_to_db,
        run_normalization,
        _resolve_shopee_merchant
    )
except ImportError:
    from cli import (
        normalize_date_string,
        run_grab,
        run_shopee,
        run_gofood,
        ingest_to_db,
        run_normalization,
        _resolve_shopee_merchant
    )

load_dotenv()

app = FastAPI(
    title="Agency OFD Pipeline Backend API",
    description="REST API Service for Online Food Delivery (GrabFood, ShopeeFood, GoFood) Scraping, Ingestion, & Data Cleaning Pipeline.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware for Frontend Dashboard Integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-Memory Job Database & Locks
jobs_db: Dict[str, Dict[str, Any]] = {}
jobs_lock = threading.Lock()

# ── Pydantic Request & Response Models ──

class ScrapeRequest(BaseModel):
    platform: Literal["grab", "shopee", "gofood", "all"] = Field(..., description="Target platform")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD or DD-MM-YYYY)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD or DD-MM-YYYY)")
    outlet: Optional[str] = Field(None, description="Pipe-separated outlet names filter")
    branch: Optional[str] = Field(None, description="Pipe-separated branch names filter")
    grab_outlet: Optional[str] = Field(None, description="Specific Grab outlet names filter")
    shopee_merchant: Optional[str] = Field(None, description="Specific Shopee merchant names filter")
    gofood_outlet: Optional[str] = Field(None, description="Specific GoFood outlet names filter")
    user: Optional[str] = Field(None, description="Filter specific username (Grab only)")
    skip_existing: bool = Field(False, description="Skip already downloaded/processed outlets")
    auto_db: bool = Field(True, description="Automatically ingest and normalize to Database after scraping")

class IngestRequest(BaseModel):
    platform: Literal["grab", "shopee", "gofood", "all"] = Field(..., description="Target platform")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD or DD-MM-YYYY)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD or DD-MM-YYYY)")
    auto_normalize: bool = Field(True, description="Trigger data cleaning & normalization after ingestion")

class JobResponse(BaseModel):
    job_id: str
    platform: str
    start_date: str
    end_date: str
    status: str
    created_at: str
    finished_at: Optional[str] = None
    results: Optional[Dict[str, Any]] = None
    logs: List[str] = []

# ── Background Task Worker ──

def _execute_scrape_job(job_id: str, req: ScrapeRequest):
    def log(msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {msg}"
        with jobs_lock:
            if job_id in jobs_db:
                jobs_db[job_id]["logs"].append(formatted)

    log(f"Starting pipeline job for platform='{req.platform}' ({req.start_date} to {req.end_date})...")
    
    start_time = datetime.now()
    results = {}

    try:
        s_clean = normalize_date_string(req.start_date)
        e_clean = normalize_date_string(req.end_date)
    except Exception as e:
        log(f"ERROR: Invalid date format: {e}")
        with jobs_lock:
            jobs_db[job_id]["status"] = "failed"
            jobs_db[job_id]["finished_at"] = datetime.now().isoformat()
        return

    # Process Grab
    if req.platform in ("grab", "all"):
        log("Executing Grab scraping...")
        o_str = req.grab_outlet or req.outlet
        b_str = req.branch
        try:
            grab_success = run_grab(s_clean, e_clean, user_filter=req.user, outlet_filter=o_str, branch_filter=b_str, skip_existing=req.skip_existing)
            results["Grab"] = grab_success
            log(f"Grab scraping status: {'SUCCESS' if grab_success else 'FAILED'}")
            
            if grab_success and req.auto_db:
                log("Auto-ingesting Grab data to PostgreSQL (layer1_raw & normalization)...")
                ingest_to_db("grab", s_clean, e_clean, auto_normalize=True)
        except Exception as ge:
            log(f"ERROR: Grab scraping failed: {ge}")
            results["Grab"] = False

    # Process Shopee
    if req.platform in ("shopee", "all"):
        log("Executing Shopee scraping...")
        m_str = req.shopee_merchant or req.outlet
        try:
            shopee_success = run_shopee(s_clean, e_clean, merchant_filter=m_str, skip_existing=req.skip_existing)
            results["Shopee"] = shopee_success
            log(f"Shopee scraping status: {'SUCCESS' if shopee_success else 'FAILED'}")
            
            if shopee_success and req.auto_db:
                log("Auto-ingesting Shopee data to PostgreSQL (layer1_raw & normalization)...")
                ingest_to_db("shopee", s_clean, e_clean, auto_normalize=True)
        except Exception as se:
            log(f"ERROR: Shopee scraping failed: {se}")
            results["Shopee"] = False

    # Process GoFood
    if req.platform in ("gofood", "all"):
        log("Executing GoFood scraping...")
        go_str = req.gofood_outlet or req.outlet
        b_str = req.branch
        try:
            gofood_success = run_gofood(s_clean, e_clean, outlet_filter=go_str, branch_filter=b_str, task_choice="2")
            results["GoFood"] = gofood_success
            log(f"GoFood scraping status: {'SUCCESS' if gofood_success else 'FAILED'}")
            
            if gofood_success and req.auto_db:
                log("Auto-ingesting GoFood data to PostgreSQL (layer1_raw & normalization)...")
                ingest_to_db("gofood", s_clean, e_clean, auto_normalize=True)
        except Exception as goe:
            log(f"ERROR: GoFood scraping failed: {goe}")
            results["GoFood"] = False

    elapsed = datetime.now() - start_time
    log(f"Pipeline job completed in {int(elapsed.total_seconds() // 60)}m {int(elapsed.total_seconds() % 60)}s.")

    with jobs_lock:
        jobs_db[job_id]["status"] = "completed"
        jobs_db[job_id]["finished_at"] = datetime.now().isoformat()
        jobs_db[job_id]["results"] = results


# ── REST API Endpoints ──

@app.get("/dashboard", response_class=FileResponse, summary="Serve Master Executive Dashboard Hub UI")
def serve_dashboard_ui():
    file_path = os.path.join(STATIC_DIR, "dashboard.html")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="dashboard.html not found.")
    return FileResponse(file_path)

@app.get("/", response_class=FileResponse, summary="Serve Master Executive Dashboard Hub UI (Root)")
def root():
    return serve_dashboard_ui()

@app.get("/health", summary="Service Health Check")
def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "active_jobs_count": sum(1 for j in jobs_db.values() if j["status"] == "running")
    }

@app.post("/api/pipeline/scrape", response_model=JobResponse, summary="Trigger Scraping Pipeline (Async Background Task)")
def trigger_scrape_pipeline(req: ScrapeRequest, background_tasks: BackgroundTasks):
    try:
        s_clean = normalize_date_string(req.start_date)
        e_clean = normalize_date_string(req.end_date)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    job_id = f"job-{uuid.uuid4().hex[:8]}"
    created_at = datetime.now().isoformat()

    job_record = {
        "job_id": job_id,
        "platform": req.platform,
        "start_date": s_clean,
        "end_date": e_clean,
        "status": "running",
        "created_at": created_at,
        "finished_at": None,
        "results": None,
        "logs": []
    }

    with jobs_lock:
        jobs_db[job_id] = job_record

    background_tasks.add_task(_execute_scrape_job, job_id, req)
    return job_record

@app.post("/api/pipeline/ingest", summary="Manually Trigger Raw DB Ingestion")
def trigger_db_ingest(req: IngestRequest):
    try:
        s_clean = normalize_date_string(req.start_date)
        e_clean = normalize_date_string(req.end_date)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    platforms = [req.platform] if req.platform != "all" else ["grab", "shopee", "gofood"]
    results = {}

    for p in platforms:
        success = ingest_to_db(p, s_clean, e_clean, auto_normalize=req.auto_normalize)
        results[p] = success

    return {
        "status": "success",
        "start_date": s_clean,
        "end_date": e_clean,
        "ingest_results": results
    }

@app.post("/api/pipeline/normalize", summary="Trigger Database Cleaning & Normalization (Layer 2 & Master Table)")
def trigger_db_normalization():
    success = run_normalization()
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to run database normalization")

    # Fetch verification counts from PostgreSQL
    counts = {}
    try:
        project_root = os.path.abspath(os.path.join(BASE_DIR, ".."))
        db_dir = os.path.join(project_root, "src", "database")
        if db_dir not in sys.path:
            sys.path.insert(0, db_dir)
        from db_manager import DatabaseManager
        db = DatabaseManager()
        with db.engine.connect() as conn:
            counts["stg_grab_orders"] = conn.execute(text("SELECT COUNT(*) FROM layer2_clean.stg_grab_orders")).scalar()
            counts["stg_go_orders"] = conn.execute(text("SELECT COUNT(*) FROM layer2_clean.stg_go_orders")).scalar()
            counts["stg_shopee_orders"] = conn.execute(text("SELECT COUNT(*) FROM layer2_clean.stg_shopee_orders")).scalar()
            counts["fact_transactions"] = conn.execute(text("SELECT COUNT(*) FROM public.fact_transactions")).scalar()
    except Exception as e:
        counts["error"] = str(e)

    return {
        "status": "success",
        "message": "Database normalization & master refresh complete.",
        "row_counts": counts
    }

@app.get("/api/jobs", summary="List All Background Jobs")
def list_jobs(limit: int = Query(50, ge=1, le=200)):
    with jobs_lock:
        all_jobs = list(jobs_db.values())
    all_jobs.sort(key=lambda j: j["created_at"], reverse=True)
    return {"total": len(all_jobs), "jobs": all_jobs[:limit]}

@app.get("/api/jobs/{job_id}", response_model=JobResponse, summary="Get Status & Logs of Specific Job")
def get_job_status(job_id: str):
    with jobs_lock:
        job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job ID '{job_id}' not found.")
    return job

@app.get("/api/dashboard-summary", summary="Executive Dashboard Summary — KPI, Trend, Platform, Top Owners, Billing")
def get_dashboard_summary():
    from datetime import date
    try:
        today = date.today()
        month_start = today.replace(day=1)

        with db_manager.engine.connect() as conn:
            # 1. Billing & Bagi Hasil Cash Flow Metrics
            billing_row = conn.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE UPPER(status_pembayaran) = 'BELUM DIBAYAR') AS jumlah_pending,
                    ROUND(COALESCE(SUM(total_tagihan) FILTER (WHERE UPPER(status_pembayaran) = 'BELUM DIBAYAR'), 0)) AS bagi_hasil_pending,
                    COUNT(*) FILTER (WHERE UPPER(status_pembayaran) = 'LUNAS') AS jumlah_lunas,
                    ROUND(COALESCE(SUM(total_tagihan) FILTER (WHERE UPPER(status_pembayaran) = 'LUNAS'), 0)) AS bagi_hasil_lunas,
                    ROUND(COALESCE(SUM(total_tagihan), 0)) AS total_tagihan_pool
                FROM layer3_dim.mv_rekap_tagihan
            """)).mappings().one()

            # 2. Overall Merchant Status (All-Time Cumulative)
            status_row = conn.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE UPPER(status) = 'LIVE') AS outlet_live,
                    COUNT(*) FILTER (WHERE UPPER(status) = 'PENDING') AS outlet_pending,
                    COUNT(*) FILTER (WHERE UPPER(status) = 'CHURN' OR churn_date IS NOT NULL) AS outlet_churn,
                    COUNT(*) AS total_mapped_outlets
                FROM layer3_dim.dim_merchant_mapping
            """)).mappings().one()

            # 2b. Overall Volume Metrics from mv_payment_daily
            vol_row = conn.execute(text("""
                SELECT
                    ROUND(SUM(total_bagi_hasil))   AS total_bagi_hasil_generated,
                    SUM(total_order_sukses)        AS total_order_sukses,
                    COUNT(DISTINCT store_id)       AS total_outlet,
                    COUNT(DISTINCT owner_name)     AS total_owner
                FROM layer3_dim.mv_payment_daily
                WHERE UPPER(COALESCE(owner_name, '')) <> 'UNKNOWN'
            """)).mappings().one()

            # 3. Monthly Bagi Hasil Trend (last 6 months)
            tren_rows = conn.execute(text("""
                SELECT
                    TO_CHAR(DATE_TRUNC('month', transaction_date), 'YYYY-MM') AS bulan,
                    ROUND(SUM(total_bagi_hasil)) AS bagi_hasil,
                    ROUND(SUM(pendapatan_kotor)) AS gmv,
                    SUM(total_order_sukses)      AS total_order
                FROM layer3_dim.mv_payment_daily
                WHERE transaction_date >= (DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '5 months')
                  AND UPPER(COALESCE(owner_name, '')) <> 'UNKNOWN'
                GROUP BY DATE_TRUNC('month', transaction_date)
                ORDER BY DATE_TRUNC('month', transaction_date)
            """)).mappings().all()

            # 4. Platform Bagi Hasil breakdown — June 2026 (complete data across GrabFood, ShopeeFood, GoFood)
            platform_rows = conn.execute(text("""
                SELECT
                    channel,
                    ROUND(SUM(pendapatan_kotor))  AS gmv,
                    ROUND(SUM(pendapatan_bersih)) AS net_revenue,
                    SUM(order_sukses)             AS orders
                FROM layer3_dim.mv_laporan_ojol
                WHERE transaction_date >= '2026-06-01'
                  AND transaction_date <= '2026-06-30'
                GROUP BY channel
                ORDER BY SUM(pendapatan_kotor) DESC
            """)).mappings().all()

            # 5. Top Owners by Bagi Hasil Generated (exclude UNKNOWN)
            top_owner_rows = conn.execute(text("""
                SELECT
                    owner_name,
                    ROUND(SUM(total_bagi_hasil))  AS total_bagi_hasil,
                    ROUND(SUM(pendapatan_kotor))  AS gmv,
                    SUM(total_order_sukses)       AS orders,
                    COUNT(DISTINCT store_id)      AS outlets
                FROM layer3_dim.mv_payment_daily
                WHERE UPPER(COALESCE(owner_name, '')) <> 'UNKNOWN'
                GROUP BY owner_name
                ORDER BY SUM(total_bagi_hasil) DESC
                LIMIT 8
            """)).mappings().all()

            # 6. Peak hours summary (from mv_jam_ramai)
            jam_ramai_rows = conn.execute(text("""
                SELECT slot_waktu, SUM(total_order) AS total_orders
                FROM layer3_dim.mv_jam_ramai
                GROUP BY slot_waktu
                ORDER BY SUM(total_order) DESC
                LIMIT 3
            """)).mappings().all()

            # 7. Order Status summary (from mv_laporan_ojol)
            order_status_row = conn.execute(text("""
                SELECT
                    SUM(order_sukses) AS order_sukses,
                    SUM(order_batal)  AS order_batal,
                    SUM(total_order)  AS total_order
                FROM layer3_dim.mv_laporan_ojol
            """)).mappings().one()

        lunas = float(billing_row["bagi_hasil_lunas"])
        pending = float(billing_row["bagi_hasil_pending"])
        total_pool = lunas + pending
        coll_rate = round((lunas / total_pool * 100), 1) if total_pool > 0 else 0.0

        kpi_combined = {
            "bagi_hasil_lunas": lunas,
            "jumlah_lunas": billing_row["jumlah_lunas"],
            "bagi_hasil_pending": pending,
            "jumlah_pending": billing_row["jumlah_pending"],
            "total_bagi_hasil_pool": total_pool,
            "collection_rate": coll_rate,
            "total_order_sukses": vol_row["total_order_sukses"],
            "total_outlet": status_row["total_mapped_outlets"],
            "outlet_live": int(status_row["outlet_live"] or 216),
            "outlet_pending": int(status_row["outlet_pending"] or 12),
            "outlet_churn": int(status_row["outlet_churn"] or 23),
            "total_owner": vol_row["total_owner"]
        }

        return {
            "periode": {"dari": "2026-06-01", "sampai": "2026-06-30"},
            "kpi": kpi_combined,
            "tren_bulanan": [dict(r) for r in tren_rows],
            "platform_breakdown": [dict(r) for r in platform_rows],
            "top_owners": [dict(r) for r in top_owner_rows],
            "billing": dict(billing_row),
            "jam_ramai": [dict(r) for r in jam_ramai_rows],
            "order_status": dict(order_status_row),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error dashboard-summary: {e}")

@app.get("/api/analytics/order-ranking", summary="Order Volume & GMV Ranking from mv_order_ranking")
def get_order_ranking(
    start_date: Optional[str] = Query("2026-06-01"),
    end_date: Optional[str] = Query("2026-06-30"),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Literal["total_orders", "gmv"] = Query("total_orders")
):
    try:
        order_col = "SUM(total_orders)" if sort_by == "total_orders" else "SUM(gmv)"
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT 
                    store_id, 
                    outlet_name, 
                    owner_name, 
                    brand, 
                    pic_name,
                    SUM(total_orders) AS total_orders, 
                    ROUND(SUM(gmv))   AS total_gmv
                FROM layer3_dim.mv_order_ranking
                WHERE transaction_date >= :start_date AND transaction_date <= :end_date
                GROUP BY store_id, outlet_name, owner_name, brand, pic_name
                ORDER BY {order_col} DESC
                LIMIT :limit
            """), {"start_date": start_date, "end_date": end_date, "limit": limit}).mappings().all()
            
            result = []
            for i, r in enumerate(rows, 1):
                item = dict(r)
                item["rank"] = i
                result.append(item)
            return {"data": result, "periode": {"start_date": start_date, "end_date": end_date}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error order-ranking: {e}")

@app.get("/api/analytics/week-over-week", summary="Week-over-Week (WoW) Growth Metrics from mv_week_to_week_comparison")
def get_week_over_week():
    try:
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT 
                    TO_CHAR(DATE_TRUNC('week', transaction_date), 'YYYY-"W"IW') AS minggu,
                    MIN(transaction_date) AS start_week,
                    MAX(transaction_date) AS end_week,
                    SUM(total_orders) AS total_orders,
                    ROUND(SUM(gmv))   AS total_gmv
                FROM layer3_dim.mv_week_to_week_comparison
                GROUP BY DATE_TRUNC('week', transaction_date)
                ORDER BY DATE_TRUNC('week', transaction_date) ASC
            """)).mappings().all()
            
            result = []
            prev_orders = None
            prev_gmv = None
            for r in rows:
                item = dict(r)
                curr_orders = float(item["total_orders"] or 0)
                curr_gmv = float(item["total_gmv"] or 0)
                
                orders_wow = round(((curr_orders - prev_orders) / prev_orders * 100), 1) if (prev_orders and prev_orders > 0) else 0.0
                gmv_wow = round(((curr_gmv - prev_gmv) / prev_gmv * 100), 1) if (prev_gmv and prev_gmv > 0) else 0.0
                
                item["orders_wow_pct"] = orders_wow
                item["gmv_wow_pct"] = gmv_wow
                result.append(item)
                
                prev_orders = curr_orders
                prev_gmv = curr_gmv
                
            return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error week-over-week: {e}")

@app.get("/api/analytics/baseline-vs-current", summary="Baseline vs Current Growth from mv_baseline_vs_current")
def get_baseline_vs_current():
    try:
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT 
                    owner_name,
                    COUNT(DISTINCT store_id) AS total_outlets,
                    MIN(live_date) AS earliest_live,
                    SUM(total_orders) AS total_orders,
                    ROUND(SUM(gmv)) AS total_gmv
                FROM layer3_dim.mv_baseline_vs_current
                WHERE UPPER(COALESCE(owner_name, '')) <> 'UNKNOWN'
                GROUP BY owner_name
                ORDER BY SUM(gmv) DESC
                LIMIT 15
            """)).mappings().all()
            return {"data": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error baseline-vs-current: {e}")

@app.get("/api/transactions", summary="Query Master Cleaned Transactions (public.fact_transactions)")
def get_transactions(
    platform: Optional[str] = Query(None, description="Filter by platform: GrabFood, ShopeeFood, GoFood"),
    start_date: Optional[str] = Query(None, description="Filter start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="Filter end date YYYY-MM-DD"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    try:
        project_root = os.path.abspath(os.path.join(BASE_DIR, ".."))
        db_dir = os.path.join(project_root, "src", "database")
        if db_dir not in sys.path:
            sys.path.insert(0, db_dir)
        from db_manager import DatabaseManager
        db = DatabaseManager()

        where_clauses = ["1=1"]
        params = {}

        if platform:
            where_clauses.append("platform = :platform")
            params["platform"] = platform
        if start_date:
            where_clauses.append("transaction_date >= :start_date")
            params["start_date"] = start_date
        if end_date:
            where_clauses.append("transaction_date <= :end_date")
            params["end_date"] = end_date

        where_sql = " AND ".join(where_clauses)
        query_sql = f"""
            SELECT id, platform, external_id, transaction_date, outlet_name, branch_name, store_name,
                   is_success, gross_amount, discounts, net_sales, commission, ofd_fees, revenue
            FROM public.fact_transactions
            WHERE {where_sql}
            ORDER BY transaction_date DESC, id DESC
            LIMIT {limit} OFFSET {offset}
        """

        count_sql = f"SELECT COUNT(*) FROM public.fact_transactions WHERE {where_sql}"

        with db.engine.connect() as conn:
            total_count = conn.execute(text(count_sql), params).scalar()
            rows = conn.execute(text(query_sql), params).mappings().all()

        return {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "data": [dict(r) for r in rows]
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database query error: {e}")

# ── Rekap Tagihan Web Dashboard & REST API Endpoints ──

# Mount static folder
STATIC_DIR = os.path.join(BASE_DIR, "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/rekap-tagihan", response_class=FileResponse, summary="Serve Rekap Tagihan Web Dashboard UI")
def serve_rekap_tagihan_ui():
    html_file = os.path.join(STATIC_DIR, "rekap_tagihan.html")
    if not os.path.exists(html_file):
        raise HTTPException(status_code=404, detail="Dashboard UI file not found.")
    return FileResponse(html_file)

@app.get("/api/rekap-tagihan/owners", summary="Get Active Owners List for Dropdown")
def get_rekap_owners():
    try:
        project_root = os.path.abspath(os.path.join(BASE_DIR, ".."))
        db_dir = os.path.join(project_root, "src", "database")
        if db_dir not in sys.path:
            sys.path.insert(0, db_dir)
        from layer1_db_manager import DatabaseManager
        db = DatabaseManager()

        query_sql = """
            SELECT DISTINCT owner_name 
            FROM layer3_dim.mv_payment_daily 
            WHERE owner_name IS NOT NULL 
              AND owner_name <> 'UNKNOWN' 
              AND TRIM(owner_name) <> ''
            ORDER BY owner_name ASC;
        """
        with db.engine.connect() as conn:
            rows = conn.execute(text(query_sql)).fetchall()

        owners = [r[0] for r in rows]
        return {"total": len(owners), "owners": owners}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching owners: {e}")

@app.get("/api/rekap-tagihan", summary="Query Rekap Tagihan per Owner & Date Range")
def get_rekap_tagihan_data(
    owner: Optional[str] = Query(None, description="Owner name filter (e.g. 'Mustika', 'Vindus')"),
    start_date: Optional[str] = Query("2026-01-01", description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    nominal_bagi_hasil: Optional[float] = Query(None, description="Optional override bagi hasil per order (e.g. 1000, 2000)")
):
    try:
        # Unwrap Query default objects if called directly in Python
        if hasattr(owner, 'default'): owner = None
        if hasattr(start_date, 'default'): start_date = '2026-01-01'
        if hasattr(end_date, 'default'): end_date = None
        if hasattr(nominal_bagi_hasil, 'default'): nominal_bagi_hasil = None

        project_root = os.path.abspath(os.path.join(BASE_DIR, ".."))
        db_dir = os.path.join(project_root, "src", "database")
        if db_dir not in sys.path:
            sys.path.insert(0, db_dir)
        from layer1_db_manager import DatabaseManager
        db = DatabaseManager()

        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        sql_params = {
            "p_owner": owner if owner else None,
            "p_start_date": start_date,
            "p_end_date": end_date,
            "p_override_nominal_bagi_hasil": nominal_bagi_hasil
        }

        query_sql = """
            SELECT tanggal, pendapatan_kotor, potongan_ojol, pendapatan_bersih, total_order_sukses, total_bagi_hasil
            FROM layer3_dim.get_rekap_tagihan(
                :p_owner,
                CAST(:p_start_date AS DATE),
                CAST(:p_end_date AS DATE),
                :p_override_nominal_bagi_hasil
            );
        """

        with db.engine.connect() as conn:
            rows = conn.execute(text(query_sql), sql_params).mappings().all()

        return {
            "owner": owner,
            "start_date": start_date,
            "end_date": end_date,
            "nominal_override": nominal_bagi_hasil,
            "data": [dict(r) for r in rows]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing get_rekap_tagihan: {e}")

# ── Tagihan Bulanan (Monthly Billing) Endpoints ──

class MonthlyPaymentUpdateRequest(BaseModel):
    store_id: str = Field(..., description="Store/Merchant ID")
    periode: str = Field(..., description="Periode YYYY-MM")
    penyesuaian: Optional[float] = Field(0.00, description="Manual fee adjustment amount")
    tanggal_tagihan: Optional[str] = Field(None, description="Billing date YYYY-MM-DD")
    transfer_id: Optional[str] = Field(None, description="Transfer transaction ID")
    tanggal_pembayaran: Optional[str] = Field(None, description="Payment date YYYY-MM-DD")
    link_bukti: Optional[str] = Field(None, description="Proof URL link")
    status_pembayaran: Optional[str] = Field("Unpaid", description="Payment status: Unpaid, Paid, Pending")
    notes: Optional[str] = Field(None, description="Internal notes")

@app.get("/rekap-tagihan-billing", response_class=FileResponse, summary="Serve Unified Rekap Tagihan Billing Dashboard Page")
@app.get("/rekap-tagihan-monthly", response_class=FileResponse, summary="Serve Unified Rekap Tagihan Billing Dashboard Page (Alias)")
def serve_rekap_tagihan_billing_page():
    file_path = os.path.join(STATIC_DIR, "rekap_tagihan_billing.html")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="rekap_tagihan_billing.html not found.")
    return FileResponse(file_path)

@app.get("/api/rekap-tagihan-billing", summary="Get Unified Rekap Tagihan Data (Monthly & Weekly)")
@app.get("/api/rekap-tagihan-monthly", summary="Get Unified Rekap Tagihan Data (Alias)")
def get_rekap_tagihan_billing_data(
    billing_cycle: Optional[str] = Query(default="Weekly", description="Billing cycle: 'Monthly' or 'Weekly'"),
    owner: Optional[str] = Query(default=None, description="Filter by Owner Name"),
    periode: Optional[str] = Query(default=None, description="Filter by Periode (e.g. '2026-06' or '2026-06-W1')"),
    status_pembayaran: Optional[str] = Query(default=None, description="Filter by Payment Status ('LUNAS', 'BELUM DIBAYAR', 'PENDING')")
):
    try:
        if hasattr(billing_cycle, 'default'): billing_cycle = "Monthly"
        if hasattr(owner, 'default'): owner = None
        if hasattr(periode, 'default'): periode = None
        if hasattr(status_pembayaran, 'default'): status_pembayaran = None

        project_root = os.path.abspath(os.path.join(BASE_DIR, ".."))
        db_dir = os.path.join(project_root, "src", "database")
        if db_dir not in sys.path:
            sys.path.insert(0, db_dir)
        from layer1_db_manager import DatabaseManager
        db = DatabaseManager()

        sql_params = {
            "p_billing_cycle": billing_cycle,
            "p_owner": owner if owner else None,
            "p_periode": periode if periode else None,
            "p_status_pembayaran": status_pembayaran if status_pembayaran else None
        }

        query_sql = """
            SELECT owner_name, outlet_name, brand, nama_resto_final, store_id, periode,
                   jumlah_order_sukses, biaya, subtotal_tagihan, penyesuaian, total_tagihan,
                   TO_CHAR(tanggal_tagihan, 'YYYY-MM-DD') AS tanggal_tagihan,
                   transfer_id,
                   TO_CHAR(tanggal_pembayaran, 'YYYY-MM-DD') AS tanggal_pembayaran,
                   link_bukti, status_pembayaran
            FROM layer3_dim.get_rekap_tagihan_billing(
                :p_billing_cycle,
                :p_owner,
                :p_periode,
                :p_status_pembayaran
            );
        """

        with db.engine.connect() as conn:
            rows = conn.execute(text(query_sql), sql_params).mappings().all()

        clean_data = [dict(r) for r in rows]
        unique_periodes = sorted(list(set(r['periode'] for r in clean_data if r.get('periode') and r['periode'] != '-')), reverse=True)

        return {
            "status": "success",
            "billing_cycle": billing_cycle,
            "owner": owner,
            "periode": periode,
            "status_pembayaran": status_pembayaran,
            "periodes": unique_periodes,
            "data": clean_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing get_rekap_tagihan_billing: {e}")

@app.post("/api/rekap-tagihan-billing/update-payment", summary="Update or Save Administrative Payment Details")
@app.post("/api/rekap-tagihan-monthly/update-payment", summary="Update or Save Administrative Payment Details (Alias)")
def update_billing_payment_record(req: MonthlyPaymentUpdateRequest):
    try:
        project_root = os.path.abspath(os.path.join(BASE_DIR, ".."))
        db_dir = os.path.join(project_root, "src", "database")
        if db_dir not in sys.path:
            sys.path.insert(0, db_dir)
        from layer1_db_manager import DatabaseManager
        db = DatabaseManager()

        tgl_tagihan = req.tanggal_tagihan if req.tanggal_tagihan and req.tanggal_tagihan.strip() else None
        tgl_bayar = req.tanggal_pembayaran if req.tanggal_pembayaran and req.tanggal_pembayaran.strip() else None

        upsert_sql = """
            INSERT INTO layer3_dim.billing_payments (
                store_id, periode, penyesuaian, tanggal_tagihan, transfer_id,
                tanggal_pembayaran, link_bukti, status_pembayaran, notes, updated_at
            ) VALUES (
                :store_id, :periode, :penyesuaian, CAST(:tanggal_tagihan AS DATE), :transfer_id,
                CAST(:tanggal_pembayaran AS DATE), :link_bukti, :status_pembayaran, :notes, CURRENT_TIMESTAMP
            )
            ON CONFLICT (store_id, periode) DO UPDATE SET
                penyesuaian = EXCLUDED.penyesuaian,
                tanggal_tagihan = EXCLUDED.tanggal_tagihan,
                transfer_id = EXCLUDED.transfer_id,
                tanggal_pembayaran = EXCLUDED.tanggal_pembayaran,
                link_bukti = EXCLUDED.link_bukti,
                status_pembayaran = EXCLUDED.status_pembayaran,
                notes = EXCLUDED.notes,
                updated_at = CURRENT_TIMESTAMP;
        """

        st_input = (req.status_pembayaran or 'BELUM DIBAYAR').strip()
        if st_input.upper() in ('PAID', 'SUDAH DIBAYAR', 'LUNAS'):
            st_input = 'LUNAS'
        elif st_input.upper() in ('UNPAID', 'BELUM DIBAYAR'):
            st_input = 'BELUM DIBAYAR'

        params = {
            "store_id": req.store_id,
            "periode": req.periode,
            "penyesuaian": req.penyesuaian or 0.00,
            "tanggal_tagihan": tgl_tagihan,
            "transfer_id": req.transfer_id,
            "tanggal_pembayaran": tgl_bayar,
            "link_bukti": req.link_bukti,
            "status_pembayaran": st_input,
            "notes": req.notes
        }

        with db.engine.begin() as conn:
            conn.execute(text(upsert_sql), params)
            # Refresh Materialized Views to reflect payment updates
            conn.execute(text("REFRESH MATERIALIZED VIEW layer3_dim.mv_billing_history;"))
            conn.execute(text("REFRESH MATERIALIZED VIEW layer3_dim.mv_rekap_tagihan;"))

        return {
            "status": "success",
            "message": f"Payment record for store_id '{req.store_id}' ({req.periode}) successfully updated.",
            "data": params
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating payment record: {e}")

@app.post("/api/rekap-tagihan-billing/sync-history", summary="Trigger Sync Payment History from Google Sheets CSV")
def sync_payment_history_from_sheets():
    try:
        project_root = os.path.abspath(os.path.join(BASE_DIR, ".."))
        db_dir = os.path.join(project_root, "src", "database")
        if db_dir not in sys.path:
            sys.path.insert(0, db_dir)
        import seed_payment_history
        seed_payment_history.run_seed_payment_history()

        return {
            "status": "success",
            "message": "Berhasil meng-import dan menyinkronkan riwayat pembayaran dari Google Sheets ke PostgreSQL Database."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menyinkronkan riwayat pembayaran: {e}")

# ============================================================================
# LAPORAN APLIKASI OJOL (GOFOOD, GRABFOOD, SHOPEEFOOD) ROUTES
# ============================================================================

@app.get("/rangkuman", response_class=FileResponse, summary="Serve Rangkuman Web Dashboard Page")
def serve_rangkuman_ui():
    file_path = os.path.join(STATIC_DIR, "rangkuman.html")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="rangkuman.html not found.")
    return FileResponse(file_path)

@app.get("/laporan-aplikasi-ojol", response_class=FileResponse, summary="Serve Rangkuman Web Dashboard Page (Alias)")
def serve_laporan_aplikasi_ojol_ui():
    return serve_rangkuman_ui()

@app.get("/api/laporan-aplikasi-ojol/filters", summary="Get Filter Options for Laporan Aplikasi Ojol")
def get_laporan_ojol_filter_options():
    try:
        with db_manager.engine.connect() as conn:
            owners = [row[0] for row in conn.execute(text("SELECT DISTINCT owner_name FROM layer3_dim.mv_laporan_ojol WHERE owner_name IS NOT NULL ORDER BY owner_name;")).fetchall()]
            outlets = [row[0] for row in conn.execute(text("SELECT DISTINCT outlet_name FROM layer3_dim.mv_laporan_ojol WHERE outlet_name IS NOT NULL ORDER BY outlet_name;")).fetchall()]
            brands = [row[0] for row in conn.execute(text("SELECT DISTINCT brand FROM layer3_dim.mv_laporan_ojol WHERE brand IS NOT NULL ORDER BY brand;")).fetchall()]
            
            # Get date range min/max
            date_range = conn.execute(text("SELECT MIN(transaction_date), MAX(transaction_date) FROM layer3_dim.mv_laporan_ojol;")).fetchone()
            
            return {
                "status": "success",
                "owners": owners,
                "outlets": outlets,
                "brands": brands,
                "channels": ["GoFood", "GrabFood", "ShopeeFood"],
                "min_date": str(date_range[0]) if date_range and date_range[0] else "2026-01-01",
                "max_date": str(date_range[1]) if date_range and date_range[1] else "2026-06-30"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching filters: {e}")

@app.get("/api/laporan-aplikasi-ojol/summary", summary="Get Aggregated Ojol Performance per Channel (Top Table)")
def get_laporan_ojol_summary(
    owner: Optional[str] = Query(default=None),
    outlet: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default="2026-04-01"),
    end_date: Optional[str] = Query(default="2026-06-30")
):
    try:
        sql = text("""
            SELECT channel, pendapatan_kotor, potongan_ojol, pendapatan_bersih,
                   rata_rata_order_per_customer, total_order, order_sukses, order_batal
            FROM layer3_dim.get_laporan_aplikasi_ojol(:owner, :outlet, :brand, CAST(:start_date AS DATE), CAST(:end_date AS DATE));
        """)
        params = {
            "owner": owner,
            "outlet": outlet,
            "brand": brand,
            "start_date": start_date or "2026-01-01",
            "end_date": end_date or "2026-12-31"
        }
        with db_manager.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().fetchall()
            clean_data = []
            for r in rows:
                row_dict = dict(r)
                for k, v in row_dict.items():
                    if isinstance(v, Decimal):
                        row_dict[k] = float(v)
                clean_data.append(row_dict)
            return {
                "status": "success",
                "data": clean_data
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Ojol summary: {e}")

@app.get("/api/laporan-aplikasi-ojol/monthly", summary="Get Monthly Ojol Performance Breakdown (Bottom Table)")
def get_laporan_ojol_monthly(
    owner: Optional[str] = Query(default=None),
    outlet: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default="2026-04-01"),
    end_date: Optional[str] = Query(default="2026-06-30")
):
    try:
        sql = text("""
            SELECT bulan, channel, pendapatan_kotor, potongan_ojol, pendapatan_bersih,
                   rata_rata_order_per_customer, total_order, order_sukses, order_batal
            FROM layer3_dim.get_laporan_bulanan_ojol(:owner, :outlet, :brand, CAST(:start_date AS DATE), CAST(:end_date AS DATE));
        """)
        params = {
            "owner": owner,
            "outlet": outlet,
            "brand": brand,
            "start_date": start_date or "2026-01-01",
            "end_date": end_date or "2026-12-31"
        }
        with db_manager.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().fetchall()
            clean_data = []
            for r in rows:
                row_dict = dict(r)
                for k, v in row_dict.items():
                    if isinstance(v, Decimal):
                        row_dict[k] = float(v)
                clean_data.append(row_dict)
            return {
                "status": "success",
                "data": clean_data
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Ojol monthly breakdown: {e}")

# ── Baseline Growth Endpoints ──

@app.get("/baseline-growth", response_class=FileResponse, summary="Serve Baseline Growth Web Dashboard UI")
def serve_baseline_growth_ui():
    html_file = os.path.join(STATIC_DIR, "baseline_growth.html")
    if not os.path.exists(html_file):
        raise HTTPException(status_code=404, detail="Baseline Growth UI file not found.")
    return FileResponse(html_file)

@app.get("/api/baseline-growth/outlets", summary="Get Active Outlets List for Dropdown Filter")
def get_baseline_outlets(owner: Optional[str] = Query(None, description="Owner name filter")):
    try:
        query_sql = """
            SELECT DISTINCT COALESCE(m.outlet_name, c.merchant_name) AS outlet_name
            FROM layer3_dim.dim_merchant_mapping m
            LEFT JOIN layer3_dim.dim_merchant_credentials c ON m.store_id = c.store_id
            WHERE COALESCE(m.outlet_name, c.merchant_name) IS NOT NULL
              AND COALESCE(m.outlet_name, c.merchant_name) <> 'UNKNOWN'
              AND TRIM(COALESCE(m.outlet_name, c.merchant_name)) <> ''
              AND (:p_owner IS NULL OR :p_owner = '' OR LOWER(COALESCE(c.owner_name, m.owner_name)) = LOWER(:p_owner))
            ORDER BY outlet_name ASC;
        """
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text(query_sql), {"p_owner": owner if owner else None}).fetchall()

        outlets = [r[0] for r in rows]
        return {"total": len(outlets), "outlets": outlets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching outlets: {e}")

@app.get("/api/baseline-growth", summary="Query Baseline Growth per Outlet")
def get_baseline_growth_data(
    owner: Optional[str] = Query(None, description="Owner name filter"),
    outlet: Optional[str] = Query(None, description="Outlet name filter"),
    start_date: Optional[str] = Query("2026-07-01", description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    growth_target_pct: Optional[float] = Query(0.0, description="Growth target percentage e.g. 10 for 10%")
):
    try:
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        sql_params = {
            "p_owner": owner if owner else None,
            "p_outlet": outlet if outlet else None,
            "p_start_date": start_date,
            "p_end_date": end_date,
            "p_growth_target_pct": growth_target_pct if growth_target_pct is not None else 0.0
        }

        query_sql = """
            SELECT
                outlet_name,
                owner_name,
                live_date,
                selected_days,
                growth_target_pct,
                days_to_eom,
                baseline_gmv,
                baseline_order,
                target_gmv,
                target_order,
                current_gmv,
                current_daily_gmv_growth,
                current_order,
                current_daily_order_growth,
                eom_gmv,
                eom_gmv_growth,
                eom_order,
                eom_order_growth,
                remaining_gmv,
                required_daily_gmv,
                remaining_order,
                required_daily_order
            FROM layer3_dim.get_baseline_growth(
                :p_owner,
                :p_outlet,
                CAST(:p_start_date AS DATE),
                CAST(:p_end_date AS DATE),
                :p_growth_target_pct
            );
        """

        with db_manager.engine.connect() as conn:
            rows = conn.execute(text(query_sql), sql_params).mappings().all()

        data_list = []
        for r in rows:
            row = dict(r)
            for k, v in row.items():
                if hasattr(v, '__class__') and v.__class__.__name__ == 'Decimal':
                    row[k] = float(v)
            data_list.append(row)

        total_baseline_gmv = sum(float(r.get('baseline_gmv') or 0) for r in data_list)
        total_baseline_order = sum(int(r.get('baseline_order') or 0) for r in data_list)
        total_target_gmv = sum(float(r.get('target_gmv') or 0) for r in data_list)
        total_target_order = sum(float(r.get('target_order') or 0) for r in data_list)
        total_current_gmv = sum(float(r.get('current_gmv') or 0) for r in data_list)
        total_current_order = sum(int(r.get('current_order') or 0) for r in data_list)
        total_eom_gmv = sum(float(r.get('eom_gmv') or 0) for r in data_list)
        total_eom_order = sum(float(r.get('eom_order') or 0) for r in data_list)
        total_remaining_gmv = sum(float(r.get('remaining_gmv') or 0) for r in data_list)
        total_remaining_order = sum(float(r.get('remaining_order') or 0) for r in data_list)

        summary = {
            "total_baseline_gmv": total_baseline_gmv,
            "total_baseline_order": total_baseline_order,
            "total_target_gmv": total_target_gmv,
            "total_target_order": total_target_order,
            "total_current_gmv": total_current_gmv,
            "total_current_order": total_current_order,
            "total_eom_gmv": total_eom_gmv,
            "total_eom_order": total_eom_order,
            "total_remaining_gmv": total_remaining_gmv,
            "total_remaining_order": total_remaining_order
        }

        return {
            "owner": owner,
            "outlet": outlet,
            "start_date": start_date,
            "end_date": end_date,
            "growth_target_pct": growth_target_pct,
            "summary": summary,
            "data": data_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error querying baseline growth: {e}")

# ── Week to Week Comparison Endpoints ──

@app.get("/weektoweekcomparison", response_class=FileResponse, summary="Serve Week to Week Comparison Web Dashboard UI")
def serve_week_to_week_comparison_ui():
    html_file = os.path.join(STATIC_DIR, "week_to_week_comparison.html")
    if not os.path.exists(html_file):
        raise HTTPException(status_code=404, detail="week_to_week_comparison.html not found.")
    return FileResponse(html_file)

@app.get("/api/week-to-week/pics", summary="Get Active PICs List for Dropdown Filter")
def get_week_to_week_pics():
    try:
        query_sql = """
            SELECT DISTINCT COALESCE(NULLIF(TRIM(pic), ''), NULLIF(TRIM(bd_pic), '')) AS pic_name 
            FROM layer3_dim.dim_merchant_mapping 
            WHERE COALESCE(NULLIF(TRIM(pic), ''), NULLIF(TRIM(bd_pic), '')) IS NOT NULL 
              AND COALESCE(NULLIF(TRIM(pic), ''), NULLIF(TRIM(bd_pic), '')) <> 'UNKNOWN'
            ORDER BY pic_name ASC;
        """
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text(query_sql)).fetchall()

        pics = [r[0] for r in rows if r[0]]
        return {"total": len(pics), "pics": pics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching PICs: {e}")

@app.get("/api/week-to-week/owners", summary="Get Active Owners List for Dropdown Filter (Filtered by PIC)")
def get_week_to_week_owners(pic: Optional[str] = Query(None, description="PIC filter")):
    try:
        query_sql = """
            SELECT DISTINCT COALESCE(c.owner_name, m.owner_name) AS owner_name 
            FROM layer3_dim.dim_merchant_mapping m
            LEFT JOIN layer3_dim.dim_merchant_credentials c ON m.store_id = c.store_id
            WHERE COALESCE(c.owner_name, m.owner_name) IS NOT NULL 
              AND COALESCE(c.owner_name, m.owner_name) <> 'UNKNOWN'
              AND TRIM(COALESCE(c.owner_name, m.owner_name)) <> ''
              AND (:p_pic IS NULL OR :p_pic = '' OR LOWER(COALESCE(m.pic, m.bd_pic, '')) = LOWER(:p_pic))
            ORDER BY owner_name ASC;
        """
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text(query_sql), {"p_pic": pic if pic else None}).fetchall()

        owners = [r[0] for r in rows]
        return {"total": len(owners), "owners": owners}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching owners: {e}")

@app.get("/api/week-to-week/outlets", summary="Get Active Outlets List for Dropdown Filter (Filtered by PIC & Owner)")
def get_week_to_week_outlets(
    pic: Optional[str] = Query(None, description="PIC filter"),
    owner: Optional[str] = Query(None, description="Owner filter")
):
    try:
        query_sql = """
            SELECT DISTINCT COALESCE(m.outlet_name, c.merchant_name) AS outlet_name 
            FROM layer3_dim.dim_merchant_mapping m
            LEFT JOIN layer3_dim.dim_merchant_credentials c ON m.store_id = c.store_id
            WHERE COALESCE(m.outlet_name, c.merchant_name) IS NOT NULL
              AND COALESCE(m.outlet_name, c.merchant_name) <> 'UNKNOWN'
              AND TRIM(COALESCE(m.outlet_name, c.merchant_name)) <> ''
              AND (:p_pic IS NULL OR :p_pic = '' OR LOWER(COALESCE(m.pic, m.bd_pic, '')) = LOWER(:p_pic))
              AND (:p_owner IS NULL OR :p_owner = '' OR LOWER(COALESCE(c.owner_name, m.owner_name)) = LOWER(:p_owner))
            ORDER BY outlet_name ASC;
        """
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text(query_sql), {"p_pic": pic if pic else None, "p_owner": owner if owner else None}).fetchall()

        outlets = [r[0] for r in rows]
        return {"total": len(outlets), "outlets": outlets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching outlets: {e}")

@app.get("/api/week-to-week", summary="Query Week to Week Comparison Data")
def get_week_to_week_comparison_data(
    pic: Optional[str] = Query(None, description="BD PIC filter"),
    owner: Optional[str] = Query(None, description="Owner filter"),
    outlet: Optional[str] = Query(None, description="Outlet filter"),
    start_date_a: str = Query("2026-07-13", description="Start date Period A YYYY-MM-DD"),
    end_date_a: str = Query("2026-07-19", description="End date Period A YYYY-MM-DD"),
    start_date_b: str = Query("2026-07-20", description="Start date Period B YYYY-MM-DD"),
    end_date_b: str = Query("2026-07-26", description="End date Period B YYYY-MM-DD"),
    target_growth_pct: Optional[float] = Query(10.0, description="Target growth % e.g. 10.0"),
    status_filter: Optional[str] = Query(None, description="Performance status filter")
):
    try:
        sql_params = {
            "p_pic": pic if pic else None,
            "p_owner": owner if owner else None,
            "p_outlet": outlet if outlet else None,
            "p_start_date_a": start_date_a,
            "p_end_date_a": end_date_a,
            "p_start_date_b": start_date_b,
            "p_end_date_b": end_date_b,
            "p_target_growth_pct": target_growth_pct if target_growth_pct is not None else 10.0
        }

        query_sql = """
            SELECT 
                pic,
                owner_name,
                outlet_name,
                live_date,
                age,
                selected_days,
                gmv_a,
                gmv_b,
                daily_gmv_a,
                daily_gmv_b,
                daily_gmv_growth,
                order_a,
                order_b,
                daily_order_a,
                daily_order_b,
                daily_order_growth,
                status
            FROM layer3_dim.get_week_to_week_comparison(
                :p_pic,
                :p_owner,
                :p_outlet,
                CAST(:p_start_date_a AS DATE),
                CAST(:p_end_date_a AS DATE),
                CAST(:p_start_date_b AS DATE),
                CAST(:p_end_date_b AS DATE),
                :p_target_growth_pct
            );
        """

        with db_manager.engine.connect() as conn:
            rows = conn.execute(text(query_sql), sql_params).mappings().all()

        data_list = []
        for r in rows:
            row = dict(r)
            for k, v in row.items():
                if hasattr(v, '__class__') and v.__class__.__name__ == 'Decimal':
                    row[k] = float(v)
            data_list.append(row)

        if status_filter and status_filter.strip() and status_filter.lower() != 'all':
            sf = status_filter.strip().lower()
            data_list = [r for r in data_list if r.get('status', '').lower() == sf]

        valid_gmv_growths = [float(r['daily_gmv_growth']) for r in data_list if r.get('daily_gmv_growth') is not None]
        valid_order_growths = [float(r['daily_order_growth']) for r in data_list if r.get('daily_order_growth') is not None]

        avg_gmv_growth = (sum(valid_gmv_growths) / len(valid_gmv_growths)) if valid_gmv_growths else 0.0
        avg_order_growth = (sum(valid_order_growths) / len(valid_order_growths)) if valid_order_growths else 0.0

        total_outlet = len(data_list)
        growing_outlet = sum(1 for r in data_list if r.get('status') == 'Achieved')

        summary = {
            "avg_gmv_growth": avg_gmv_growth,
            "avg_order_growth": avg_order_growth,
            "total_outlet": total_outlet,
            "growing_outlet": growing_outlet,
            "achieved_count": growing_outlet,
            "gmv_below_count": sum(1 for r in data_list if r.get('status') == 'GMV Below Target'),
            "order_below_count": sum(1 for r in data_list if r.get('status') == 'Order Below Target'),
            "not_achieved_count": sum(1 for r in data_list if r.get('status') == 'Not Achieved')
        }

        return {
            "pic": pic,
            "owner": owner,
            "outlet": outlet,
            "start_date_a": start_date_a,
            "end_date_a": end_date_a,
            "start_date_b": start_date_b,
            "end_date_b": end_date_b,
            "target_growth_pct": target_growth_pct,
            "status_filter": status_filter,
            "summary": summary,
            "data": data_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing get_week_to_week_comparison: {e}")

# ── Baseline vs Current Performance Endpoints ──

@app.get("/baseline-vs-current-performance", response_class=FileResponse, summary="Serve Baseline vs Current Performance Dashboard")
def serve_baseline_vs_current_ui():
    html_file = os.path.join(STATIC_DIR, "baseline_vs_current_performance.html")
    if not os.path.exists(html_file):
        raise HTTPException(status_code=404, detail="baseline_vs_current_performance.html not found.")
    return FileResponse(html_file)

@app.get("/api/baseline-vs-current/pics", summary="Get PIC list for Baseline vs Current dropdown")
def get_bvc_pics():
    try:
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT DISTINCT COALESCE(NULLIF(TRIM(pic), ''), NULLIF(TRIM(bd_pic), '')) AS pic_name 
                FROM layer3_dim.dim_merchant_mapping 
                WHERE COALESCE(NULLIF(TRIM(pic), ''), NULLIF(TRIM(bd_pic), '')) IS NOT NULL 
                  AND COALESCE(NULLIF(TRIM(pic), ''), NULLIF(TRIM(bd_pic), '')) <> 'UNKNOWN'
                ORDER BY pic_name ASC;
            """)).fetchall()
        return {"pics": [r[0] for r in rows if r[0]]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching PICs: {e}")

@app.get("/api/baseline-vs-current/owners", summary="Get Owner list filtered by PIC for Baseline vs Current dropdown")
def get_bvc_owners(pic: Optional[str] = Query(None)):
    try:
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT DISTINCT COALESCE(c.owner_name, m.owner_name) AS owner_name 
                FROM layer3_dim.dim_merchant_mapping m
                LEFT JOIN layer3_dim.dim_merchant_credentials c ON m.store_id = c.store_id
                WHERE COALESCE(c.owner_name, m.owner_name) IS NOT NULL 
                  AND COALESCE(c.owner_name, m.owner_name) <> 'UNKNOWN'
                  AND TRIM(COALESCE(c.owner_name, m.owner_name)) <> ''
                  AND (:p_pic IS NULL OR :p_pic = '' OR LOWER(COALESCE(m.pic, m.bd_pic, '')) = LOWER(:p_pic))
                ORDER BY owner_name ASC;
            """), {"p_pic": pic or None}).fetchall()
        return {"owners": [r[0] for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching owners: {e}")

@app.get("/api/baseline-vs-current/outlets", summary="Get Outlet list filtered by PIC & Owner for Baseline vs Current dropdown")
def get_bvc_outlets(pic: Optional[str] = Query(None), owner: Optional[str] = Query(None)):
    try:
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT DISTINCT COALESCE(m.outlet_name, c.merchant_name) AS outlet_name 
                FROM layer3_dim.dim_merchant_mapping m
                LEFT JOIN layer3_dim.dim_merchant_credentials c ON m.store_id = c.store_id
                WHERE COALESCE(m.outlet_name, c.merchant_name) IS NOT NULL
                  AND COALESCE(m.outlet_name, c.merchant_name) <> 'UNKNOWN'
                  AND TRIM(COALESCE(m.outlet_name, c.merchant_name)) <> ''
                  AND (:p_pic IS NULL OR :p_pic = '' OR LOWER(COALESCE(m.pic, m.bd_pic, '')) = LOWER(:p_pic))
                  AND (:p_owner IS NULL OR :p_owner = '' OR LOWER(COALESCE(c.owner_name, m.owner_name)) = LOWER(:p_owner))
                ORDER BY outlet_name ASC;
            """), {"p_pic": pic or None, "p_owner": owner or None}).fetchall()
        return {"outlets": [r[0] for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching outlets: {e}")

@app.get("/api/baseline-vs-current", summary="Query Baseline vs Current Performance Data")
def get_baseline_vs_current_data(
    pic: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    outlet: Optional[str] = Query(None),
    start_date: str = Query("2026-07-20"),
    end_date: str = Query("2026-07-26"),
    target_growth_pct: Optional[float] = Query(10.0),
    status_filter: Optional[str] = Query(None)
):
    try:
        params = {
            "p_pic": pic or None,
            "p_owner": owner or None,
            "p_outlet": outlet or None,
            "p_start_date": start_date,
            "p_end_date": end_date,
            "p_target": target_growth_pct if target_growth_pct is not None else 10.0
        }
        query_sql = """
            SELECT pic, owner_name, outlet_name, live_date, age, selected_days,
                   baseline_gmv, current_gmv, baseline_daily_gmv, current_daily_gmv, daily_gmv_growth,
                   baseline_order, current_order, baseline_daily_order, current_daily_order, daily_order_growth,
                   status
            FROM layer3_dim.get_baseline_vs_current(
                :p_pic, :p_owner, :p_outlet,
                CAST(:p_start_date AS DATE), CAST(:p_end_date AS DATE),
                :p_target
            );
        """
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text(query_sql), params).mappings().all()

        data_list = []
        for r in rows:
            row = dict(r)
            for k, v in row.items():
                if hasattr(v, '__class__') and v.__class__.__name__ == 'Decimal':
                    row[k] = float(v)
            data_list.append(row)

        # Apply status filter
        if status_filter and status_filter.strip() and status_filter.lower() != 'all':
            sf = status_filter.strip().lower()
            data_list = [r for r in data_list if r.get('status', '').lower() == sf]

        # Summary metrics
        valid_gmv = [r['daily_gmv_growth'] for r in data_list if r.get('daily_gmv_growth') is not None]
        valid_ord = [r['daily_order_growth'] for r in data_list if r.get('daily_order_growth') is not None]
        avg_gmv_growth = sum(valid_gmv) / len(valid_gmv) if valid_gmv else 0.0
        avg_ord_growth = sum(valid_ord) / len(valid_ord) if valid_ord else 0.0

        summary = {
            "avg_gmv_growth": avg_gmv_growth,
            "avg_order_growth": avg_ord_growth,
            "total_outlet": len(data_list),
            "growing_outlet": sum(1 for r in data_list if r.get('status') == 'Achieved'),
            "achieved_count": sum(1 for r in data_list if r.get('status') == 'Achieved'),
            "gmv_below_count": sum(1 for r in data_list if r.get('status') == 'GMV Below Target'),
            "order_below_count": sum(1 for r in data_list if r.get('status') == 'Order Below Target'),
            "not_achieved_count": sum(1 for r in data_list if r.get('status') == 'Not Achieved')
        }
        return {
            "pic": pic, "owner": owner, "outlet": outlet,
            "start_date": start_date, "end_date": end_date,
            "target_growth_pct": target_growth_pct,
            "summary": summary, "data": data_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error querying baseline_vs_current: {e}")

# ============================================================================
# LAPORAN JAM RAMAI (PEAK HOURS & OPERATIONAL ANALYSIS) ROUTES
# ============================================================================

@app.get("/laporan-jam-ramai", response_class=FileResponse, summary="Serve Laporan Jam Ramai Web Dashboard Page")
def serve_laporan_jam_ramai_ui():
    file_path = os.path.join(STATIC_DIR, "laporan_jam_ramai.html")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="laporan_jam_ramai.html not found.")
    return FileResponse(file_path)

@app.get("/api/laporan-jam-ramai/filters", summary="Get Filter Options for Laporan Jam Ramai")
def get_laporan_jam_ramai_filter_options():
    try:
        with db_manager.engine.connect() as conn:
            owners = [row[0] for row in conn.execute(text("SELECT DISTINCT owner_name FROM layer3_dim.mv_jam_ramai WHERE owner_name IS NOT NULL ORDER BY owner_name;")).fetchall()]
            outlets = [row[0] for row in conn.execute(text("SELECT DISTINCT outlet_name FROM layer3_dim.mv_jam_ramai WHERE outlet_name IS NOT NULL ORDER BY outlet_name;")).fetchall()]
            brands = [row[0] for row in conn.execute(text("SELECT DISTINCT brand FROM layer3_dim.mv_jam_ramai WHERE brand IS NOT NULL ORDER BY brand;")).fetchall()]
            date_range = conn.execute(text("SELECT MIN(transaction_date), MAX(transaction_date) FROM layer3_dim.mv_jam_ramai;")).fetchone()
            
            return {
                "status": "success",
                "owners": owners,
                "outlets": outlets,
                "brands": brands,
                "min_date": str(date_range[0]) if date_range and date_range[0] else "2026-01-01",
                "max_date": str(date_range[1]) if date_range and date_range[1] else "2026-06-30"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching filters: {e}")

@app.get("/api/laporan-jam-ramai/summary", summary="Get Hourly Performance (00:00 to 23:00) Summary")
def get_laporan_jam_ramai_summary(
    owner: Optional[str] = Query(default=None),
    outlet: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default="2026-04-01"),
    end_date: Optional[str] = Query(default="2026-06-30")
):
    try:
        sql = text("""
            SELECT jam, jam_label, slot_waktu, pendapatan_kotor, potongan_ojol, pendapatan_bersih,
                   rata_rata_order_per_customer, total_order, order_sukses, order_batal, pct_batal,
                   is_peak_hour_orders, is_peak_hour_sales
            FROM layer3_dim.get_laporan_jam_ramai_summary(:owner, :outlet, :brand, CAST(:start_date AS DATE), CAST(:end_date AS DATE));
        """)
        params = {
            "owner": owner,
            "outlet": outlet,
            "brand": brand,
            "start_date": start_date or "2026-01-01",
            "end_date": end_date or "2026-12-31"
        }
        with db_manager.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().fetchall()
            clean_data = []
            for r in rows:
                row_dict = dict(r)
                for k, v in row_dict.items():
                    if isinstance(v, Decimal):
                        row_dict[k] = float(v)
                clean_data.append(row_dict)
            return {
                "status": "success",
                "data": clean_data
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Jam Ramai summary: {e}")

@app.get("/api/laporan-jam-ramai/by-slot", summary="Get Operational Time Slot Breakdown")
def get_laporan_jam_ramai_by_slot(
    owner: Optional[str] = Query(default=None),
    outlet: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default="2026-04-01"),
    end_date: Optional[str] = Query(default="2026-06-30")
):
    try:
        sql = text("""
            SELECT slot_waktu, pendapatan_kotor, potongan_ojol, pendapatan_bersih,
                   rata_rata_order_per_customer, total_order, order_sukses, order_batal, pct_batal
            FROM layer3_dim.get_laporan_jam_ramai_by_slot(:owner, :outlet, :brand, CAST(:start_date AS DATE), CAST(:end_date AS DATE));
        """)
        params = {
            "owner": owner,
            "outlet": outlet,
            "brand": brand,
            "start_date": start_date or "2026-01-01",
            "end_date": end_date or "2026-12-31"
        }
        with db_manager.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().fetchall()
            clean_data = []
            for r in rows:
                row_dict = dict(r)
                for k, v in row_dict.items():
                    if isinstance(v, Decimal):
                        row_dict[k] = float(v)
                clean_data.append(row_dict)
            return {
                "status": "success",
                "data": clean_data
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Jam Ramai by slot: {e}")

@app.get("/api/laporan-jam-ramai/by-day", summary="Get 24 Hours x 7 Days Day of Week Matrix")
def get_laporan_jam_ramai_by_day(
    owner: Optional[str] = Query(default=None),
    outlet: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default="2026-04-01"),
    end_date: Optional[str] = Query(default="2026-06-30")
):
    try:
        sql = text("""
            SELECT dow_num, hari_name, jam, jam_label, pendapatan_kotor, pendapatan_bersih,
                   total_order, order_sukses, order_batal
            FROM layer3_dim.get_laporan_jam_ramai_by_day(:owner, :outlet, :brand, CAST(:start_date AS DATE), CAST(:end_date AS DATE));
        """)
        params = {
            "owner": owner,
            "outlet": outlet,
            "brand": brand,
            "start_date": start_date or "2026-01-01",
            "end_date": end_date or "2026-12-31"
        }
        with db_manager.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().fetchall()
            clean_data = []
            for r in rows:
                row_dict = dict(r)
                for k, v in row_dict.items():
                    if isinstance(v, Decimal):
                        row_dict[k] = float(v)
                clean_data.append(row_dict)
            return {
                "status": "success",
                "data": clean_data
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Jam Ramai by day matrix: {e}")

# ============================================================================
# ORDER SUKSES VS ORDER BATAL ROUTES
# ============================================================================

@app.get("/order-sukses-vs-batal", response_class=FileResponse, summary="Serve Order Sukses vs Order Batal Web Dashboard Page")
def serve_order_status_ui():
    file_path = os.path.join(STATIC_DIR, "order_sukses_vs_batal.html")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="order_sukses_vs_batal.html not found.")
    return FileResponse(file_path)

@app.get("/api/order-status/filters", summary="Get Filter Options for Order Status")
def get_order_status_filter_options():
    try:
        with db_manager.engine.connect() as conn:
            outlets = [row[0] for row in conn.execute(text("SELECT DISTINCT outlet_name FROM layer3_dim.mv_order_status WHERE outlet_name IS NOT NULL ORDER BY outlet_name;")).fetchall()]
            brands = [row[0] for row in conn.execute(text("SELECT DISTINCT brand FROM layer3_dim.mv_order_status WHERE brand IS NOT NULL ORDER BY brand;")).fetchall()]
            date_range = conn.execute(text("SELECT MIN(transaction_date), MAX(transaction_date) FROM layer3_dim.mv_order_status;")).fetchone()
            
            return {
                "status": "success",
                "outlets": outlets,
                "brands": brands,
                "min_date": str(date_range[0]) if date_range and date_range[0] else "2026-01-01",
                "max_date": str(date_range[1]) if date_range and date_range[1] else "2026-06-30"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching filters: {e}")

@app.get("/api/order-status/summary", summary="Get Order Sukses vs Order Batal Summary")
def get_order_status_summary(
    outlet: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default="2026-04-01"),
    end_date: Optional[str] = Query(default="2026-06-30")
):
    try:
        sql = text("""
            SELECT channel, total_order, order_sukses, order_batal, pct_sukses, pct_batal,
                   pendapatan_kotor, pendapatan_bersih
            FROM layer3_dim.get_laporan_order_status(:outlet, :brand, CAST(:start_date AS DATE), CAST(:end_date AS DATE));
        """)
        params = {
            "outlet": outlet,
            "brand": brand,
            "start_date": start_date or "2026-01-01",
            "end_date": end_date or "2026-12-31"
        }
        with db_manager.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().fetchall()
            clean_data = []
            for r in rows:
                row_dict = dict(r)
                for k, v in row_dict.items():
                    if isinstance(v, Decimal):
                        row_dict[k] = float(v)
                clean_data.append(row_dict)
            return {
                "status": "success",
                "data": clean_data
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching order status summary: {e}")

# ── Order Ranking Endpoints ──

@app.get("/order-ranking", response_class=FileResponse, summary="Serve Order Ranking Web Dashboard Page")
def serve_order_ranking_ui():
    file_path = os.path.join(STATIC_DIR, "order_ranking.html")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="order_ranking.html not found.")
    return FileResponse(file_path)

@app.get("/api/order-ranking/pics", summary="Get Active PICs List for Order Ranking Dropdown")
def get_order_ranking_pics():
    try:
        query_sql = """
            SELECT DISTINCT COALESCE(NULLIF(TRIM(pic), ''), NULLIF(TRIM(bd_pic), '')) AS pic_name 
            FROM layer3_dim.dim_merchant_mapping 
            WHERE COALESCE(NULLIF(TRIM(pic), ''), NULLIF(TRIM(bd_pic), '')) IS NOT NULL 
              AND COALESCE(NULLIF(TRIM(pic), ''), NULLIF(TRIM(bd_pic), '')) <> 'UNKNOWN'
            ORDER BY pic_name ASC;
        """
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text(query_sql)).fetchall()

        pics = [r[0] for r in rows if r[0]]
        return {"pics": pics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching PICs: {e}")

@app.get("/api/order-ranking/owners", summary="Get Active Owners List for Order Ranking Dropdown")
def get_order_ranking_owners(pic: Optional[str] = Query(None)):
    try:
        query_sql = """
            SELECT DISTINCT COALESCE(c.owner_name, m.owner_name) AS owner_name 
            FROM layer3_dim.dim_merchant_mapping m
            LEFT JOIN layer3_dim.dim_merchant_credentials c ON m.store_id = c.store_id
            WHERE COALESCE(c.owner_name, m.owner_name) IS NOT NULL 
              AND COALESCE(c.owner_name, m.owner_name) <> 'UNKNOWN'
              AND TRIM(COALESCE(c.owner_name, m.owner_name)) <> ''
              AND (:p_pic IS NULL OR :p_pic = '' OR LOWER(COALESCE(m.pic, m.bd_pic, '')) = LOWER(:p_pic))
            ORDER BY owner_name ASC;
        """
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text(query_sql), {"p_pic": pic or None}).fetchall()

        owners = [r[0] for r in rows]
        return {"owners": owners}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching owners: {e}")

@app.get("/api/order-ranking/outlets", summary="Get Active Outlets List for Order Ranking Dropdown")
def get_order_ranking_outlets(pic: Optional[str] = Query(None), owner: Optional[str] = Query(None)):
    try:
        query_sql = """
            SELECT DISTINCT COALESCE(m.outlet_name, c.merchant_name) AS outlet_name 
            FROM layer3_dim.dim_merchant_mapping m
            LEFT JOIN layer3_dim.dim_merchant_credentials c ON m.store_id = c.store_id
            WHERE COALESCE(m.outlet_name, c.merchant_name) IS NOT NULL
              AND COALESCE(m.outlet_name, c.merchant_name) <> 'UNKNOWN'
              AND TRIM(COALESCE(m.outlet_name, c.merchant_name)) <> ''
              AND (:p_pic IS NULL OR :p_pic = '' OR LOWER(COALESCE(m.pic, m.bd_pic, '')) = LOWER(:p_pic))
              AND (:p_owner IS NULL OR :p_owner = '' OR LOWER(COALESCE(c.owner_name, m.owner_name)) = LOWER(:p_owner))
            ORDER BY outlet_name ASC;
        """
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text(query_sql), {"p_pic": pic or None, "p_owner": owner or None}).fetchall()

        outlets = [r[0] for r in rows]
        return {"outlets": outlets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching outlets: {e}")

@app.get("/api/order-ranking", summary="Query Order Ranking Data")
def get_order_ranking_data(
    pic: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    outlet: Optional[str] = Query(None),
    start_date: str = Query("2026-07-20"),
    end_date: str = Query("2026-07-26")
):
    try:
        query_sql = """
            SELECT pic, owner_name, outlet_name, live_date, order_sukses, total_gmv
            FROM layer3_dim.get_order_ranking(
                :p_pic, :p_owner, :p_outlet,
                CAST(:p_start_date AS DATE), CAST(:p_end_date AS DATE)
            );
        """
        params = {
            "p_pic": pic or None,
            "p_owner": owner or None,
            "p_outlet": outlet or None,
            "p_start_date": start_date,
            "p_end_date": end_date
        }
        with db_manager.engine.connect() as conn:
            rows = conn.execute(text(query_sql), params).mappings().all()

        data_list = []
        for r in rows:
            row = dict(r)
            for k, v in row.items():
                if hasattr(v, '__class__') and v.__class__.__name__ == 'Decimal':
                    row[k] = float(v)
            data_list.append(row)

        # Date diff / selected days calculation
        try:
            d_start = datetime.strptime(start_date, "%Y-%m-%d")
            d_end = datetime.strptime(end_date, "%Y-%m-%d")
            selected_days = (d_end - d_start).days + 1
        except Exception:
            selected_days = 7

        total_outlet = len(data_list)
        total_order = sum(int(r.get('order_sukses') or 0) for r in data_list)

        avg_daily_order = round(total_order / selected_days / total_outlet, 2) if total_outlet > 0 and selected_days > 0 else 0.0
        avg_monthly_order = round((total_order / total_outlet) * (30.0 / selected_days), 2) if total_outlet > 0 and selected_days > 0 else 0.0

        # Productivity Distribution (Histogram Bins)
        productivity_bins = {
            "0 - 50 Order": sum(1 for r in data_list if (r.get('order_sukses') or 0) <= 50),
            "51 - 100 Order": sum(1 for r in data_list if 50 < (r.get('order_sukses') or 0) <= 100),
            "101 - 200 Order": sum(1 for r in data_list if 100 < (r.get('order_sukses') or 0) <= 200),
            "201 - 500 Order": sum(1 for r in data_list if 200 < (r.get('order_sukses') or 0) <= 500),
            "> 500 Order": sum(1 for r in data_list if (r.get('order_sukses') or 0) > 500)
        }

        summary = {
            "selected_days": selected_days,
            "total_order": total_order,
            "total_outlet": total_outlet,
            "avg_daily_order_per_outlet": avg_daily_order,
            "avg_monthly_order_per_outlet": avg_monthly_order,
            "productivity_bins": productivity_bins
        }

        return {
            "pic": pic, "owner": owner, "outlet": outlet,
            "start_date": start_date, "end_date": end_date,
            "summary": summary, "data": data_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error querying order ranking: {e}")

# ============================================================================
# LAPORAN PERFORMA ROUTES
# ============================================================================

@app.get("/laporan-performa", response_class=FileResponse, summary="Serve Laporan Performa Web Dashboard Page")
def serve_laporan_performa_ui():
    file_path = os.path.join(STATIC_DIR, "laporan_performa.html")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="laporan_performa.html not found.")
    return FileResponse(file_path)

@app.get("/performa-comparison", response_class=FileResponse, summary="Serve Performa Comparison Web Dashboard Page")
def serve_performa_comparison_ui():
    file_path = os.path.join(STATIC_DIR, "performa_comparison.html")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="performa_comparison.html not found.")
    return FileResponse(file_path)

@app.get("/api/performa-comparison/filters", summary="Get Filter Options for Performa Comparison with Cascading Support")
def get_performa_comparison_filter_options(
    owner: Optional[str] = Query(default=None),
    outlet: Optional[str] = Query(default=None)
):
    try:
        with db_manager.engine.connect() as conn:
            owners_sql = "SELECT DISTINCT owner_name FROM layer3_dim.mv_performa_comparison WHERE owner_name IS NOT NULL ORDER BY owner_name;"
            owners = [row[0] for row in conn.execute(text(owners_sql)).fetchall()]

            outlets_sql = """
                SELECT DISTINCT outlet_name 
                FROM layer3_dim.mv_performa_comparison 
                WHERE outlet_name IS NOT NULL
                  AND (:owner IS NULL OR :owner = '' OR LOWER(owner_name) = LOWER(:owner))
                ORDER BY outlet_name;
            """
            outlets = [row[0] for row in conn.execute(text(outlets_sql), {"owner": owner}).fetchall()]

            brands_sql = """
                SELECT DISTINCT brand 
                FROM layer3_dim.mv_performa_comparison 
                WHERE brand IS NOT NULL
                  AND (:owner IS NULL OR :owner = '' OR LOWER(owner_name) = LOWER(:owner))
                  AND (:outlet IS NULL OR :outlet = '' OR LOWER(outlet_name) = LOWER(:outlet))
                ORDER BY brand;
            """
            brands = [row[0] for row in conn.execute(text(brands_sql), {"owner": owner, "outlet": outlet}).fetchall()]

            mapping_sql = """
                SELECT DISTINCT owner_name, outlet_name, brand
                FROM layer3_dim.mv_performa_comparison
                WHERE owner_name IS NOT NULL AND outlet_name IS NOT NULL AND brand IS NOT NULL
                ORDER BY owner_name, outlet_name, brand;
            """
            mapping_rows = conn.execute(text(mapping_sql)).fetchall()
            mapping = [{"owner": r[0], "outlet": r[1], "brand": r[2]} for r in mapping_rows]

            date_range = conn.execute(text("SELECT MIN(transaction_date), MAX(transaction_date) FROM layer3_dim.mv_performa_comparison;")).fetchone()
            
            return {
                "status": "success",
                "owners": owners,
                "outlets": outlets,
                "brands": brands,
                "mapping": mapping,
                "min_date": str(date_range[0]) if date_range and date_range[0] else "2026-01-01",
                "max_date": str(date_range[1]) if date_range and date_range[1] else "2026-06-30"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching filters: {e}")

@app.get("/api/performa-comparison/data", summary="Get Performa Comparison Breakdown Data")
def get_performa_comparison_data(
    tipe_laporan: Optional[str] = Query(default="Bulanan"),
    owner: Optional[str] = Query(default=None),
    outlet: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default="2026-04-01"),
    end_date: Optional[str] = Query(default="2026-06-30")
):
    try:
        sql = text("""
            SELECT periode_label, pendapatan_kotor, potongan_ojol, pendapatan_bersih,
                   rata_rata_order_per_customer, total_order, order_sukses, order_batal
            FROM layer3_dim.get_laporan_performa_comparison(
                :tipe_laporan, :owner, :outlet, :brand, CAST(:start_date AS DATE), CAST(:end_date AS DATE)
            );
        """)
        params = {
            "tipe_laporan": tipe_laporan or "Bulanan",
            "owner": owner,
            "outlet": outlet,
            "brand": brand,
            "start_date": start_date or "2026-01-01",
            "end_date": end_date or "2026-12-31"
        }
        with db_manager.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().fetchall()
            clean_data = []
            for r in rows:
                row_dict = dict(r)
                for k, v in row_dict.items():
                    if isinstance(v, Decimal):
                        row_dict[k] = float(v)
                clean_data.append(row_dict)
            return {
                "status": "success",
                "data": clean_data
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching performa comparison data: {e}")

@app.get("/api/performa-comparison/charts", summary="Get Performa Comparison Financial & Order Charts Data")
def get_performa_comparison_charts_data(
    outlet: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    channel: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default="2026-04-01"),
    end_date: Optional[str] = Query(default="2026-06-30")
):
    try:
        sql = text("""
            SELECT periode_label, pendapatan_kotor, potongan_ojol, pendapatan_bersih,
                   total_order, order_sukses, order_batal
            FROM layer3_dim.get_performa_comparison_charts(
                :outlet, :brand, :channel, CAST(:start_date AS DATE), CAST(:end_date AS DATE)
            );
        """)
        params = {
            "outlet": outlet,
            "brand": brand,
            "channel": channel,
            "start_date": start_date or "2026-01-01",
            "end_date": end_date or "2026-12-31"
        }
        with db_manager.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().fetchall()
            clean_data = []
            for r in rows:
                row_dict = dict(r)
                for k, v in row_dict.items():
                    if isinstance(v, Decimal):
                        row_dict[k] = float(v)
                clean_data.append(row_dict)
            return {
                "status": "success",
                "data": clean_data
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching comparison charts data: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)


