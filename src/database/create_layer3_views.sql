-- Live View for BI Tools & Visualizations
DROP VIEW IF EXISTS layer3_dim.v_fact_transactions CASCADE;
CREATE OR REPLACE VIEW layer3_dim.v_fact_transactions AS
SELECT 
    ft.id AS transaction_id,
    ft.external_id AS order_id,
    ft.platform AS platform_name,
    -- Platform Info
    CASE 
        WHEN UPPER(ft.platform) LIKE '%GRAB%' THEN '#00B14F'
        WHEN UPPER(ft.platform) LIKE '%SHOPEE%' THEN '#EE4D2D'
        WHEN UPPER(ft.platform) LIKE '%GO%' THEN '#00AA13'
        ELSE '#888888'
    END AS platform_color,
    ft.transaction_date,
    CAST(TO_CHAR(ft.transaction_date, 'YYYYMMDD') AS INTEGER) AS date_key,
    EXTRACT(YEAR FROM ft.transaction_date)::INTEGER AS year,
    ft.month,
    ft.week,
    
    -- Merchant & Mapping Dimensions
    ft.merchant_id AS store_id,
    m.owner_name,
    COALESCE(m.outlet_name, ft.outlet_name) AS outlet_name,
    m.brand,
    COALESCE(m.nama_resto_final, ft.branch_name, 'PENDING_REVIEW') AS nama_resto_final,
    COALESCE(m.group_code, ft.group_code) AS group_code,
    m.bd_pic,
    COALESCE(m.status, 'Live') AS merchant_status,

    -- Transaction Metrics
    ft.status AS order_status,
    ft.is_success,
    ft.is_cancelled,
    ft.gross_amount,
    ft.discounts,
    ft.delivery_discount,
    ft.net_sales,
    ft.marketing_fee,
    ft.commission,
    ft.ofd_fees,
    ft.revenue AS net_payout,

    ft.context,
    ft.created_on,
    ft.updated_at
FROM layer3_dim.fact_transactions ft
LEFT JOIN layer3_dim.dim_merchant_mapping m ON ft.merchant_id = m.store_id;

-- ============================================================================
-- 2. MATERIALIZED VIEW PAYMENT HARIAN PER OWNER & OUTLET
-- ============================================================================
DROP MATERIALIZED VIEW IF EXISTS layer3_dim.mv_payment_daily CASCADE;

CREATE MATERIALIZED VIEW layer3_dim.mv_payment_daily AS
SELECT 
    COALESCE(c.owner_name, m.owner_name, 'UNKNOWN') AS owner_name,
    COALESCE(m.outlet_name, c.merchant_name, ft.outlet_name, 'UNKNOWN') AS outlet_name,
    COALESCE(m.brand, 'UNKNOWN') AS brand,
    COALESCE(m.nama_resto_final, ft.branch_name, 'UNKNOWN') AS nama_resto_final,
    ft.merchant_id AS store_id,
    COALESCE(NULLIF(REGEXP_REPLACE(m.fee, '[^0-9]', '', 'g'), '')::NUMERIC, 1000.00) AS nominal_bagi_hasil_per_order,
    ft.transaction_date,
    SUM(CASE WHEN ft.is_success = 1 THEN ft.net_sales ELSE 0.00 END) AS pendapatan_kotor,
    SUM(CASE WHEN ft.is_success = 1 THEN ft.ofd_fees ELSE 0.00 END) AS potongan_ojol,
    SUM(CASE WHEN ft.is_success = 1 THEN ft.revenue ELSE 0.00 END) AS pendapatan_bersih,
    COUNT(CASE WHEN ft.is_success = 1 AND COALESCE(ft.context, '') <> 'Advertisement' THEN 1 END) AS total_order_sukses,
    COUNT(CASE WHEN ft.is_success = 1 AND COALESCE(ft.context, '') <> 'Advertisement' THEN 1 END) * COALESCE(NULLIF(REGEXP_REPLACE(m.fee, '[^0-9]', '', 'g'), '')::NUMERIC, 1000.00) AS total_bagi_hasil
FROM layer3_dim.fact_transactions ft
LEFT JOIN layer3_dim.dim_merchant_credentials c ON ft.merchant_id = c.store_id
LEFT JOIN layer3_dim.dim_merchant_mapping m ON ft.merchant_id = m.store_id
WHERE UPPER(COALESCE(m.status, 'LIVE')) = 'LIVE'
GROUP BY 
    COALESCE(c.owner_name, m.owner_name, 'UNKNOWN'),
    COALESCE(m.outlet_name, c.merchant_name, ft.outlet_name, 'UNKNOWN'),
    COALESCE(m.brand, 'UNKNOWN'),
    COALESCE(m.nama_resto_final, ft.branch_name, 'UNKNOWN'),
    ft.merchant_id,
    COALESCE(NULLIF(REGEXP_REPLACE(m.fee, '[^0-9]', '', 'g'), '')::NUMERIC, 1000.00),
    ft.transaction_date;

DROP INDEX IF EXISTS layer3_dim.idx_mv_payment_daily;
DROP INDEX IF EXISTS layer3_dim.idx_mv_payment_daily_owner;
DROP INDEX IF EXISTS layer3_dim.idx_mv_payment_daily_date;

-- Indeks Unik Pendukung Refresh Concurrent & Query Cepat
CREATE UNIQUE INDEX idx_mv_payment_daily ON layer3_dim.mv_payment_daily (owner_name, store_id, transaction_date);
CREATE INDEX idx_mv_payment_daily_owner ON layer3_dim.mv_payment_daily (owner_name);
CREATE INDEX idx_mv_payment_daily_date ON layer3_dim.mv_payment_daily (transaction_date);

-- ============================================================================
-- 3. SQL STORED FUNCTION DYNAMIC REKAP TAGIHAN PER OWNER
-- ============================================================================
DROP FUNCTION IF EXISTS layer3_dim.get_rekap_tagihan(text,date,date,numeric) CASCADE;

CREATE OR REPLACE FUNCTION layer3_dim.get_rekap_tagihan(
    p_owner TEXT DEFAULT NULL,
    p_start_date DATE DEFAULT '2026-01-01',
    p_end_date DATE DEFAULT CURRENT_DATE,
    p_override_nominal_bagi_hasil NUMERIC DEFAULT NULL
)
RETURNS TABLE (
    tanggal TEXT,
    pendapatan_kotor NUMERIC(15,2),
    potongan_ojol NUMERIC(15,2),
    pendapatan_bersih NUMERIC(15,2),
    total_order_sukses BIGINT,
    total_bagi_hasil NUMERIC(15,2)
) AS $$
BEGIN
    RETURN QUERY
    WITH daily_agg AS (
        SELECT 
            TO_CHAR(mv.transaction_date, 'YYYY-MM-DD') AS tgl_str,
            mv.transaction_date AS tgl_date,
            SUM(mv.pendapatan_kotor) AS pk,
            SUM(mv.potongan_ojol) AS po,
            SUM(mv.pendapatan_bersih) AS pb,
            SUM(mv.total_order_sukses)::BIGINT AS os,
            SUM(
                CASE 
                    WHEN p_override_nominal_bagi_hasil IS NOT NULL THEN mv.total_order_sukses * p_override_nominal_bagi_hasil
                    ELSE mv.total_bagi_hasil
                END
            ) AS bh
        FROM layer3_dim.mv_payment_daily mv
        WHERE (p_owner IS NULL OR p_owner = '' OR LOWER(mv.owner_name) = LOWER(p_owner))
          AND mv.transaction_date >= p_start_date
          AND mv.transaction_date <= p_end_date
        GROUP BY mv.transaction_date
    ),
    combined AS (
        SELECT 
            d.tgl_str AS t_date,
            d.tgl_date AS sort_date,
            d.pk AS pk_val,
            d.po AS po_val,
            d.pb AS pb_val,
            d.os AS os_val,
            d.bh AS bh_val,
            1 AS sort_grp
        FROM daily_agg d
        
        UNION ALL
        
        SELECT 
            'Grand Total' AS t_date,
            '2099-12-31'::DATE AS sort_date,
            COALESCE(SUM(d.pk), 0.00) AS pk_val,
            COALESCE(SUM(d.po), 0.00) AS po_val,
            COALESCE(SUM(d.pb), 0.00) AS pb_val,
            COALESCE(SUM(d.os), 0)::BIGINT AS os_val,
            COALESCE(SUM(d.bh), 0.00) AS bh_val,
            2 AS sort_grp
        FROM daily_agg d
    )
    SELECT 
        c.t_date AS tanggal,
        c.pk_val AS pendapatan_kotor,
        c.po_val AS potongan_ojol,
        c.pb_val AS pendapatan_bersih,
        c.os_val AS total_order_sukses,
        c.bh_val AS total_bagi_hasil
    FROM combined c
    ORDER BY c.sort_grp ASC, c.sort_date ASC;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 4. TABEL ADMINISTRATIVE REKONSILIASI PEMBAYARAN TAGIHAN BULANAN
-- ============================================================================
CREATE TABLE IF NOT EXISTS layer3_dim.billing_payments (
    id SERIAL PRIMARY KEY,
    store_id TEXT NOT NULL,
    periode TEXT NOT NULL,
    penyesuaian NUMERIC(15,2) DEFAULT 0.00,
    tanggal_tagihan DATE,
    transfer_id TEXT,
    tanggal_pembayaran DATE,
    link_bukti TEXT,
    status_pembayaran TEXT DEFAULT 'BELUM DIBAYAR',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_billing_payments UNIQUE (store_id, periode)
);

-- ============================================================================
-- 5. MATERIALIZED VIEW UNIFIED REKAP TAGIHAN (MONTHLY & WEEKLY LIVE OUTLETS)
-- ============================================================================
DROP MATERIALIZED VIEW IF EXISTS layer3_dim.mv_rekap_tagihan_monthly CASCADE;
DROP MATERIALIZED VIEW IF EXISTS layer3_dim.mv_rekap_tagihan CASCADE;

CREATE MATERIALIZED VIEW layer3_dim.mv_rekap_tagihan AS
SELECT 
    COALESCE(c.owner_name, m.owner_name, 'UNKNOWN') AS owner_name,
    COALESCE(m.outlet_name, c.merchant_name, ft.outlet_name, 'UNKNOWN') AS outlet_name,
    COALESCE(m.brand, 'UNKNOWN') AS brand,
    COALESCE(m.nama_resto_final, ft.branch_name, 'UNKNOWN') AS nama_resto_final,
    ft.merchant_id AS store_id,
    UPPER(COALESCE(m.billing_cycle, 'MONTHLY')) AS billing_cycle,
    (CASE 
        WHEN UPPER(COALESCE(m.billing_cycle, 'MONTHLY')) = 'WEEKLY' 
            THEN TO_CHAR(ft.transaction_date, 'YYYY-MM') || '-W' || TO_CHAR(ft.transaction_date, 'W')
        ELSE TO_CHAR(ft.transaction_date, 'YYYY-MM')
    END) AS periode,
    COUNT(CASE WHEN ft.is_success = 1 AND COALESCE(ft.context, '') <> 'Advertisement' THEN 1 END)::BIGINT AS jumlah_order_sukses,
    COALESCE(NULLIF(REGEXP_REPLACE(m.fee, '[^0-9]', '', 'g'), '')::NUMERIC, 1000.00) AS biaya,
    COUNT(CASE WHEN ft.is_success = 1 AND COALESCE(ft.context, '') <> 'Advertisement' THEN 1 END) * COALESCE(NULLIF(REGEXP_REPLACE(m.fee, '[^0-9]', '', 'g'), '')::NUMERIC, 1000.00) AS subtotal_tagihan,
    COALESCE(p.penyesuaian, 0.00) AS penyesuaian,
    (COUNT(CASE WHEN ft.is_success = 1 AND COALESCE(ft.context, '') <> 'Advertisement' THEN 1 END) * COALESCE(NULLIF(REGEXP_REPLACE(m.fee, '[^0-9]', '', 'g'), '')::NUMERIC, 1000.00)) + COALESCE(p.penyesuaian, 0.00) AS total_tagihan,
    COALESCE(p.tanggal_tagihan, 
        CASE 
            WHEN (CASE WHEN UPPER(COALESCE(m.billing_cycle, 'MONTHLY')) = 'WEEKLY' THEN TO_CHAR(ft.transaction_date, 'YYYY-MM') || '-W' || TO_CHAR(ft.transaction_date, 'W') ELSE TO_CHAR(ft.transaction_date, 'YYYY-MM') END) LIKE '%-W1' THEN (SUBSTRING(TO_CHAR(ft.transaction_date, 'YYYY-MM') FROM 1 FOR 7) || '-08')::DATE
            WHEN (CASE WHEN UPPER(COALESCE(m.billing_cycle, 'MONTHLY')) = 'WEEKLY' THEN TO_CHAR(ft.transaction_date, 'YYYY-MM') || '-W' || TO_CHAR(ft.transaction_date, 'W') ELSE TO_CHAR(ft.transaction_date, 'YYYY-MM') END) LIKE '%-W2' THEN (SUBSTRING(TO_CHAR(ft.transaction_date, 'YYYY-MM') FROM 1 FOR 7) || '-15')::DATE
            WHEN (CASE WHEN UPPER(COALESCE(m.billing_cycle, 'MONTHLY')) = 'WEEKLY' THEN TO_CHAR(ft.transaction_date, 'YYYY-MM') || '-W' || TO_CHAR(ft.transaction_date, 'W') ELSE TO_CHAR(ft.transaction_date, 'YYYY-MM') END) LIKE '%-W3' THEN (SUBSTRING(TO_CHAR(ft.transaction_date, 'YYYY-MM') FROM 1 FOR 7) || '-22')::DATE
            WHEN (CASE WHEN UPPER(COALESCE(m.billing_cycle, 'MONTHLY')) = 'WEEKLY' THEN TO_CHAR(ft.transaction_date, 'YYYY-MM') || '-W' || TO_CHAR(ft.transaction_date, 'W') ELSE TO_CHAR(ft.transaction_date, 'YYYY-MM') END) LIKE '%-W4' THEN (SUBSTRING(TO_CHAR(ft.transaction_date, 'YYYY-MM') FROM 1 FOR 7) || '-29')::DATE
            WHEN (CASE WHEN UPPER(COALESCE(m.billing_cycle, 'MONTHLY')) = 'WEEKLY' THEN TO_CHAR(ft.transaction_date, 'YYYY-MM') || '-W' || TO_CHAR(ft.transaction_date, 'W') ELSE TO_CHAR(ft.transaction_date, 'YYYY-MM') END) LIKE '%-W5' THEN ((SUBSTRING(TO_CHAR(ft.transaction_date, 'YYYY-MM') FROM 1 FOR 7) || '-01')::DATE + INTERVAL '1 month' + INTERVAL '5 days')::DATE
            ELSE ((SUBSTRING(TO_CHAR(ft.transaction_date, 'YYYY-MM') FROM 1 FOR 7) || '-01')::DATE + INTERVAL '1 month')::DATE
        END
    ) AS tanggal_tagihan,
    p.transfer_id,
    p.tanggal_pembayaran,
    p.link_bukti,
    CASE 
        WHEN UPPER(COALESCE(p.status_pembayaran, 'BELUM DIBAYAR')) IN ('PAID', 'LUNAS', 'SUDAH DIBAYAR') THEN 'LUNAS'
        WHEN UPPER(COALESCE(p.status_pembayaran, 'BELUM DIBAYAR')) = 'PENDING' THEN 'PENDING'
        ELSE 'BELUM DIBAYAR'
    END AS status_pembayaran
FROM layer3_dim.fact_transactions ft
LEFT JOIN layer3_dim.dim_merchant_credentials c ON ft.merchant_id = c.store_id
LEFT JOIN layer3_dim.dim_merchant_mapping m ON ft.merchant_id = m.store_id
LEFT JOIN layer3_dim.billing_payments p ON ft.merchant_id = p.store_id AND (
    CASE 
        WHEN UPPER(COALESCE(m.billing_cycle, 'MONTHLY')) = 'WEEKLY' 
            THEN TO_CHAR(ft.transaction_date, 'YYYY-MM') || '-W' || TO_CHAR(ft.transaction_date, 'W')
        ELSE TO_CHAR(ft.transaction_date, 'YYYY-MM')
    END = p.periode OR REPLACE(p.periode, ' ', '-') = (
        CASE 
            WHEN UPPER(COALESCE(m.billing_cycle, 'MONTHLY')) = 'WEEKLY' 
                THEN TO_CHAR(ft.transaction_date, 'YYYY-MM') || '-W' || TO_CHAR(ft.transaction_date, 'W')
            ELSE TO_CHAR(ft.transaction_date, 'YYYY-MM')
        END
    )
)
WHERE UPPER(COALESCE(m.status, 'LIVE')) = 'LIVE'
GROUP BY 
    COALESCE(c.owner_name, m.owner_name, 'UNKNOWN'),
    COALESCE(m.outlet_name, c.merchant_name, ft.outlet_name, 'UNKNOWN'),
    COALESCE(m.brand, 'UNKNOWN'),
    COALESCE(m.nama_resto_final, ft.branch_name, 'UNKNOWN'),
    ft.merchant_id,
    UPPER(COALESCE(m.billing_cycle, 'MONTHLY')),
    (CASE 
        WHEN UPPER(COALESCE(m.billing_cycle, 'MONTHLY')) = 'WEEKLY' 
            THEN TO_CHAR(ft.transaction_date, 'YYYY-MM') || '-W' || TO_CHAR(ft.transaction_date, 'W')
        ELSE TO_CHAR(ft.transaction_date, 'YYYY-MM')
    END),
    TO_CHAR(ft.transaction_date, 'YYYY-MM'),
    COALESCE(NULLIF(REGEXP_REPLACE(m.fee, '[^0-9]', '', 'g'), '')::NUMERIC, 1000.00),
    p.penyesuaian,
    p.tanggal_tagihan,
    p.transfer_id,
    p.tanggal_pembayaran,
    p.link_bukti,
    p.status_pembayaran;

DROP INDEX IF EXISTS layer3_dim.idx_mv_rekap_tagihan;
DROP INDEX IF EXISTS layer3_dim.idx_mv_rekap_tagihan_owner;
DROP INDEX IF EXISTS layer3_dim.idx_mv_rekap_tagihan_periode;

CREATE UNIQUE INDEX idx_mv_rekap_tagihan ON layer3_dim.mv_rekap_tagihan (store_id, periode);
CREATE INDEX idx_mv_rekap_tagihan_owner ON layer3_dim.mv_rekap_tagihan (owner_name);
CREATE INDEX idx_mv_rekap_tagihan_periode ON layer3_dim.mv_rekap_tagihan (periode);

-- ============================================================================
-- 5B. MATERIALIZED VIEW BILLING HISTORY (PAYMENT HISTORY RECORDS)
-- ============================================================================
DROP MATERIALIZED VIEW IF EXISTS layer3_dim.mv_billing_history CASCADE;

CREATE MATERIALIZED VIEW layer3_dim.mv_billing_history AS
SELECT 
    COALESCE(c.owner_name, m.owner_name, 'UNKNOWN') AS owner_name,
    COALESCE(m.outlet_name, c.merchant_name, 'UNKNOWN') AS outlet_name,
    COALESCE(m.brand, 'UNKNOWN') AS brand,
    COALESCE(m.nama_resto_final, 'UNKNOWN') AS nama_resto_final,
    p.store_id,
    p.periode,
    COALESCE(p.penyesuaian, 0.00) AS penyesuaian,
    p.tanggal_tagihan,
    p.transfer_id,
    p.tanggal_pembayaran,
    p.link_bukti,
    CASE 
        WHEN UPPER(COALESCE(p.status_pembayaran, 'BELUM DIBAYAR')) IN ('PAID', 'LUNAS', 'SUDAH DIBAYAR') THEN 'LUNAS'
        WHEN UPPER(COALESCE(p.status_pembayaran, 'BELUM DIBAYAR')) = 'PENDING' THEN 'PENDING'
        ELSE 'BELUM DIBAYAR'
    END AS status_pembayaran,
    p.notes,
    p.updated_at
FROM layer3_dim.billing_payments p
LEFT JOIN layer3_dim.dim_merchant_mapping m ON p.store_id = m.store_id
LEFT JOIN layer3_dim.dim_merchant_credentials c ON p.store_id = c.store_id;

DROP INDEX IF EXISTS layer3_dim.idx_mv_billing_history;
DROP INDEX IF EXISTS layer3_dim.idx_mv_billing_history_owner;
DROP INDEX IF EXISTS layer3_dim.idx_mv_billing_history_periode;

CREATE UNIQUE INDEX idx_mv_billing_history ON layer3_dim.mv_billing_history (store_id, periode);
CREATE INDEX idx_mv_billing_history_owner ON layer3_dim.mv_billing_history (owner_name);
CREATE INDEX idx_mv_billing_history_periode ON layer3_dim.mv_billing_history (periode);

-- ============================================================================
-- 6. SQL STORED FUNCTION UNIFIED DYNAMIC REKAP TAGIHAN (MONTHLY & WEEKLY)
-- ============================================================================
DROP FUNCTION IF EXISTS layer3_dim.get_rekap_tagihan_monthly(text,text,text) CASCADE;
DROP FUNCTION IF EXISTS layer3_dim.get_rekap_tagihan_billing(text,text,text,text) CASCADE;

CREATE OR REPLACE FUNCTION layer3_dim.get_rekap_tagihan_billing(
    p_billing_cycle TEXT DEFAULT 'Monthly', -- 'Monthly' or 'Weekly'
    p_owner TEXT DEFAULT NULL,
    p_periode TEXT DEFAULT NULL,           -- 'YYYY-MM' for Monthly, or 'YYYY-MM-W1'..'W5' / 'YYYY-MM W1' for Weekly
    p_status_pembayaran TEXT DEFAULT NULL
)
RETURNS TABLE (
    owner_name TEXT,
    outlet_name TEXT,
    brand TEXT,
    nama_resto_final TEXT,
    store_id TEXT,
    periode TEXT,
    jumlah_order_sukses BIGINT,
    biaya NUMERIC(15,2),
    subtotal_tagihan NUMERIC(15,2),
    penyesuaian NUMERIC(15,2),
    total_tagihan NUMERIC(15,2),
    tanggal_tagihan DATE,
    transfer_id TEXT,
    tanggal_pembayaran DATE,
    link_bukti TEXT,
    status_pembayaran TEXT
) AS $$
BEGIN
    RETURN QUERY
    WITH target_cycle AS (
        SELECT CASE 
            WHEN LOWER(COALESCE(p_billing_cycle, 'monthly')) LIKE 'week%' THEN 'WEEKLY'
            ELSE 'MONTHLY'
        END AS cycle_code
    ),
    clean_params AS (
        SELECT REPLACE(REPLACE(p_periode, ' ', '-'), 'W', 'W') AS norm_periode
    ),
    live_outlets AS (
        SELECT 
            COALESCE(c.owner_name, m.owner_name, 'UNKNOWN') AS o_name,
            COALESCE(m.outlet_name, c.merchant_name, 'UNKNOWN') AS ot_name,
            COALESCE(m.brand, 'UNKNOWN') AS b_name,
            COALESCE(m.nama_resto_final, 'UNKNOWN') AS r_name,
            m.store_id AS s_id,
            COALESCE(NULLIF(REGEXP_REPLACE(m.fee, '[^0-9]', '', 'g'), '')::NUMERIC, 1000.00) AS fee_val
        FROM layer3_dim.dim_merchant_mapping m
        LEFT JOIN layer3_dim.dim_merchant_credentials c ON m.store_id = c.store_id
        CROSS JOIN target_cycle tc
        WHERE UPPER(COALESCE(m.status, 'LIVE')) = 'LIVE'
          AND UPPER(COALESCE(m.billing_cycle, '')) = tc.cycle_code
    ),
    target_periodes AS (
        SELECT DISTINCT p.p_code
        FROM (
            SELECT 
                CASE 
                    WHEN (SELECT cycle_code FROM target_cycle) = 'WEEKLY' 
                        THEN TO_CHAR(transaction_date, 'YYYY-MM') || '-W' || TO_CHAR(transaction_date, 'W')
                    ELSE TO_CHAR(transaction_date, 'YYYY-MM')
                END AS p_code 
            FROM layer3_dim.fact_transactions 
            WHERE transaction_date IS NOT NULL
            
            UNION
            
            SELECT COALESCE(NULLIF((SELECT norm_periode FROM clean_params), ''), 
                CASE 
                    WHEN (SELECT cycle_code FROM target_cycle) = 'WEEKLY' 
                        THEN TO_CHAR(CURRENT_DATE, 'YYYY-MM') || '-W1'
                    ELSE TO_CHAR(CURRENT_DATE, 'YYYY-MM')
                END
            ) AS p_code
        ) p
        CROSS JOIN clean_params cp
        WHERE (cp.norm_periode IS NULL OR cp.norm_periode = '' 
               OR REPLACE(p.p_code, ' ', '-') = cp.norm_periode
               OR p.p_code LIKE cp.norm_periode || '%')
    ),
    grid AS (
        SELECT o.*, p.p_code
        FROM live_outlets o
        CROSS JOIN target_periodes p
    ),
    raw_agg AS (
        SELECT 
            g.o_name,
            g.ot_name,
            g.b_name,
            g.r_name,
            g.s_id,
            g.p_code,
            COUNT(CASE WHEN ft.is_success = 1 AND COALESCE(ft.context, '') <> 'Advertisement' THEN 1 END)::BIGINT AS os_cnt,
            g.fee_val,
            COUNT(CASE WHEN ft.is_success = 1 AND COALESCE(ft.context, '') <> 'Advertisement' THEN 1 END) * g.fee_val AS sub_val,
            COALESCE(pm.penyesuaian, 0.00) AS adj_val,
            (COUNT(CASE WHEN ft.is_success = 1 AND COALESCE(ft.context, '') <> 'Advertisement' THEN 1 END) * g.fee_val) + COALESCE(pm.penyesuaian, 0.00) AS tot_val,
            COALESCE(pm.tanggal_tagihan, 
                CASE 
                    WHEN g.p_code LIKE '%-W1' OR g.p_code LIKE '% W1' THEN (SUBSTRING(g.p_code FROM 1 FOR 7) || '-08')::DATE
                    WHEN g.p_code LIKE '%-W2' OR g.p_code LIKE '% W2' THEN (SUBSTRING(g.p_code FROM 1 FOR 7) || '-15')::DATE
                    WHEN g.p_code LIKE '%-W3' OR g.p_code LIKE '% W3' THEN (SUBSTRING(g.p_code FROM 1 FOR 7) || '-22')::DATE
                    WHEN g.p_code LIKE '%-W4' OR g.p_code LIKE '% W4' THEN ((SUBSTRING(g.p_code FROM 1 FOR 7) || '-01')::DATE + INTERVAL '27 days')::DATE
                    WHEN g.p_code LIKE '%-W5' OR g.p_code LIKE '% W5' THEN ((SUBSTRING(g.p_code FROM 1 FOR 7) || '-01')::DATE + INTERVAL '1 month' + INTERVAL '5 days')::DATE
                    ELSE ((SUBSTRING(g.p_code FROM 1 FOR 7) || '-01')::DATE + INTERVAL '1 month')::DATE
                END
            ) AS tgl_tagihan,
            pm.transfer_id AS trf_id,
            pm.tanggal_pembayaran AS tgl_bayar,
            pm.link_bukti AS link_bkt,
            CASE 
                WHEN UPPER(COALESCE(pm.status_pembayaran, 'BELUM DIBAYAR')) IN ('PAID', 'LUNAS', 'SUDAH DIBAYAR') THEN 'LUNAS'
                WHEN UPPER(COALESCE(pm.status_pembayaran, 'BELUM DIBAYAR')) = 'PENDING' THEN 'PENDING'
                ELSE 'BELUM DIBAYAR'
            END AS st_bayar
        FROM grid g
        CROSS JOIN target_cycle tc
        LEFT JOIN layer3_dim.fact_transactions ft 
            ON g.s_id = ft.merchant_id 
           AND (
               CASE 
                   WHEN tc.cycle_code = 'WEEKLY' 
                       THEN (TO_CHAR(ft.transaction_date, 'YYYY-MM') || '-W' || TO_CHAR(ft.transaction_date, 'W'))
                   ELSE TO_CHAR(ft.transaction_date, 'YYYY-MM')
               END
           ) = g.p_code
        LEFT JOIN layer3_dim.billing_payments pm 
            ON g.s_id = pm.store_id 
           AND (pm.periode = g.p_code OR REPLACE(pm.periode, ' ', '-') = g.p_code)
        WHERE (p_owner IS NULL OR p_owner = '' OR LOWER(g.o_name) = LOWER(p_owner))
          AND (
              p_status_pembayaran IS NULL OR p_status_pembayaran = '' OR 
              LOWER(COALESCE(pm.status_pembayaran, 'BELUM DIBAYAR')) = LOWER(p_status_pembayaran) OR
              (LOWER(p_status_pembayaran) IN ('lunas', 'paid', 'sudah dibayar') AND UPPER(COALESCE(pm.status_pembayaran, 'BELUM DIBAYAR')) IN ('PAID', 'LUNAS', 'SUDAH DIBAYAR')) OR
              (LOWER(p_status_pembayaran) IN ('belum dibayar', 'unpaid') AND UPPER(COALESCE(pm.status_pembayaran, 'BELUM DIBAYAR')) IN ('UNPAID', 'BELUM DIBAYAR'))
          )
        GROUP BY 
            g.o_name, g.ot_name, g.b_name, g.r_name, g.s_id, g.p_code, g.fee_val,
            pm.penyesuaian, pm.tanggal_tagihan, pm.transfer_id, pm.tanggal_pembayaran, pm.link_bukti, pm.status_pembayaran
    ),
    combined AS (
        SELECT 
            r.o_name, r.ot_name, r.b_name, r.r_name, r.s_id, r.p_code,
            r.os_cnt, r.fee_val, r.sub_val, r.adj_val, r.tot_val,
            r.tgl_tagihan, r.trf_id, r.tgl_bayar, r.link_bkt, r.st_bayar,
            1 AS s_grp
        FROM raw_agg r

        UNION ALL

        SELECT 
            'Grand Total' AS o_name, '-' AS ot_name, '-' AS b_name, '-' AS r_name, '-' AS s_id, '-' AS p_code,
            COALESCE(SUM(r.os_cnt), 0)::BIGINT AS os_cnt, 0.00 AS fee_val,
            COALESCE(SUM(r.sub_val), 0.00) AS sub_val, COALESCE(SUM(r.adj_val), 0.00) AS adj_val, COALESCE(SUM(r.tot_val), 0.00) AS tot_val,
            NULL::DATE AS tgl_tagihan, '-' AS trf_id, NULL::DATE AS tgl_bayar, '-' AS link_bkt, '-' AS st_bayar,
            2 AS s_grp
        FROM raw_agg r
    )
    SELECT 
        c.o_name AS owner_name, c.ot_name AS outlet_name, c.b_name AS brand, c.r_name AS nama_resto_final,
        c.s_id AS store_id, c.p_code AS periode, c.os_cnt AS jumlah_order_sukses, c.fee_val AS biaya,
        c.sub_val AS subtotal_tagihan, c.adj_val AS penyesuaian, c.tot_val AS total_tagihan,
        c.tgl_tagihan AS tanggal_tagihan, c.trf_id AS transfer_id, c.tgl_bayar AS tanggal_pembayaran,
        c.link_bkt AS link_bukti, c.st_bayar AS status_pembayaran
    FROM combined c
    ORDER BY c.s_grp ASC, c.o_name ASC, c.r_name ASC;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 7. MATERIALIZED VIEW LAPORAN APLIKASI OJOL (GOFOOD, GRABFOOD, SHOPEEFOOD)
-- ============================================================================
DROP MATERIALIZED VIEW IF EXISTS layer3_dim.mv_laporan_ojol CASCADE;

CREATE MATERIALIZED VIEW layer3_dim.mv_laporan_ojol AS
SELECT 
    COALESCE(c.owner_name, m.owner_name, 'UNKNOWN') AS owner_name,
    COALESCE(m.outlet_name, c.merchant_name, ft.outlet_name, 'UNKNOWN') AS outlet_name,
    COALESCE(m.brand, 'UNKNOWN') AS brand,
    ft.merchant_id AS store_id,
    ft.transaction_date,
    TO_CHAR(ft.transaction_date, 'YYYY-MM') AS bulan,
    ft.platform AS channel,
    SUM(CASE WHEN ft.is_success = 1 THEN ft.net_sales ELSE 0.00 END) AS pendapatan_kotor,
    SUM(CASE WHEN ft.is_success = 1 THEN ft.ofd_fees ELSE 0.00 END) AS potongan_ojol,
    SUM(CASE WHEN ft.is_success = 1 THEN ft.revenue ELSE 0.00 END) AS pendapatan_bersih,
    COUNT(*)::BIGINT AS total_order,
    COUNT(CASE WHEN ft.is_success = 1 THEN 1 END)::BIGINT AS order_sukses,
    COUNT(CASE WHEN ft.is_cancelled = 1 OR ft.is_success = 0 THEN 1 END)::BIGINT AS order_batal
FROM layer3_dim.fact_transactions ft
LEFT JOIN layer3_dim.dim_merchant_credentials c ON ft.merchant_id = c.store_id
LEFT JOIN layer3_dim.dim_merchant_mapping m ON ft.merchant_id = m.store_id
WHERE UPPER(COALESCE(m.status, 'LIVE')) = 'LIVE'
GROUP BY 
    COALESCE(c.owner_name, m.owner_name, 'UNKNOWN'),
    COALESCE(m.outlet_name, c.merchant_name, ft.outlet_name, 'UNKNOWN'),
    COALESCE(m.brand, 'UNKNOWN'),
    ft.merchant_id,
    ft.transaction_date,
    ft.platform;

DROP INDEX IF EXISTS layer3_dim.idx_mv_laporan_ojol;
DROP INDEX IF EXISTS layer3_dim.idx_mv_laporan_ojol_owner;
DROP INDEX IF EXISTS layer3_dim.idx_mv_laporan_ojol_date;

CREATE UNIQUE INDEX idx_mv_laporan_ojol ON layer3_dim.mv_laporan_ojol (store_id, transaction_date, channel);
CREATE INDEX idx_mv_laporan_ojol_owner ON layer3_dim.mv_laporan_ojol (owner_name);
CREATE INDEX idx_mv_laporan_ojol_date ON layer3_dim.mv_laporan_ojol (transaction_date);

-- ============================================================================
-- 8. STORED FUNCTIONS LAPORAN APLIKASI OJOL (AGREGAT CHANNEL & BULANAN)
-- ============================================================================
DROP FUNCTION IF EXISTS layer3_dim.get_laporan_aplikasi_ojol(text,text,text,date,date) CASCADE;
DROP FUNCTION IF EXISTS layer3_dim.get_laporan_bulanan_ojol(text,text,text,date,date) CASCADE;

CREATE OR REPLACE FUNCTION layer3_dim.get_laporan_aplikasi_ojol(
    p_owner TEXT DEFAULT NULL,
    p_outlet TEXT DEFAULT NULL,
    p_brand TEXT DEFAULT NULL,
    p_start_date DATE DEFAULT '2026-01-01',
    p_end_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    channel TEXT,
    pendapatan_kotor NUMERIC(15,2),
    potongan_ojol NUMERIC(15,2),
    pendapatan_bersih NUMERIC(15,2),
    rata_rata_order_per_customer NUMERIC(15,2),
    total_order BIGINT,
    order_sukses BIGINT,
    order_batal BIGINT
) AS $$
BEGIN
    RETURN QUERY
    WITH filtered AS (
        SELECT 
            mv.channel,
            SUM(mv.pendapatan_kotor) AS pk,
            SUM(mv.potongan_ojol) AS po,
            SUM(mv.pendapatan_bersih) AS pb,
            SUM(mv.total_order) AS tot_ord,
            SUM(mv.order_sukses) AS suk_ord,
            SUM(mv.order_batal) AS bat_ord
        FROM layer3_dim.mv_laporan_ojol mv
        WHERE (p_owner IS NULL OR p_owner = '' OR LOWER(mv.owner_name) = LOWER(p_owner))
          AND (p_outlet IS NULL OR p_outlet = '' OR LOWER(mv.outlet_name) = LOWER(p_outlet))
          AND (p_brand IS NULL OR p_brand = '' OR LOWER(mv.brand) = LOWER(p_brand))
          AND mv.transaction_date BETWEEN COALESCE(p_start_date, '2026-01-01') AND COALESCE(p_end_date, CURRENT_DATE)
        GROUP BY mv.channel
    ),
    combined AS (
        SELECT 
            f.channel,
            f.pk,
            f.po,
            f.pb,
            ROUND(CASE WHEN f.suk_ord > 0 THEN f.pk / f.suk_ord ELSE 0.00 END, 2) AS avg_ord,
            f.tot_ord,
            f.suk_ord,
            f.bat_ord,
            1 AS s_grp
        FROM filtered f

        UNION ALL

        SELECT 
            'Grand Total' AS channel,
            COALESCE(SUM(f.pk), 0.00) AS pk,
            COALESCE(SUM(f.po), 0.00) AS po,
            COALESCE(SUM(f.pb), 0.00) AS pb,
            ROUND(CASE WHEN SUM(f.suk_ord) > 0 THEN SUM(f.pk) / SUM(f.suk_ord) ELSE 0.00 END, 2) AS avg_ord,
            COALESCE(SUM(f.tot_ord), 0)::BIGINT AS tot_ord,
            COALESCE(SUM(f.suk_ord), 0)::BIGINT AS suk_ord,
            COALESCE(SUM(f.bat_ord), 0)::BIGINT AS bat_ord,
            2 AS s_grp
        FROM filtered f
    )
    SELECT 
        c.channel::TEXT,
        c.pk AS pendapatan_kotor,
        c.po AS potongan_ojol,
        c.pb AS pendapatan_bersih,
        c.avg_ord AS rata_rata_order_per_customer,
        c.tot_ord::BIGINT AS total_order,
        c.suk_ord::BIGINT AS order_sukses,
        c.bat_ord::BIGINT AS order_batal
    FROM combined c
    ORDER BY c.s_grp ASC, c.channel ASC;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION layer3_dim.get_laporan_bulanan_ojol(
    p_owner TEXT DEFAULT NULL,
    p_outlet TEXT DEFAULT NULL,
    p_brand TEXT DEFAULT NULL,
    p_start_date DATE DEFAULT '2026-01-01',
    p_end_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    bulan TEXT,
    channel TEXT,
    pendapatan_kotor NUMERIC(15,2),
    potongan_ojol NUMERIC(15,2),
    pendapatan_bersih NUMERIC(15,2),
    rata_rata_order_per_customer NUMERIC(15,2),
    total_order BIGINT,
    order_sukses BIGINT,
    order_batal BIGINT
) AS $$
BEGIN
    RETURN QUERY
    WITH filtered AS (
        SELECT 
            mv.bulan,
            mv.channel,
            SUM(mv.pendapatan_kotor) AS pk,
            SUM(mv.potongan_ojol) AS po,
            SUM(mv.pendapatan_bersih) AS pb,
            SUM(mv.total_order) AS tot_ord,
            SUM(mv.order_sukses) AS suk_ord,
            SUM(mv.order_batal) AS bat_ord
        FROM layer3_dim.mv_laporan_ojol mv
        WHERE (p_owner IS NULL OR p_owner = '' OR LOWER(mv.owner_name) = LOWER(p_owner))
          AND (p_outlet IS NULL OR p_outlet = '' OR LOWER(mv.outlet_name) = LOWER(p_outlet))
          AND (p_brand IS NULL OR p_brand = '' OR LOWER(mv.brand) = LOWER(p_brand))
          AND mv.transaction_date BETWEEN COALESCE(p_start_date, '2026-01-01') AND COALESCE(p_end_date, CURRENT_DATE)
        GROUP BY mv.bulan, mv.channel
    ),
    monthly_totals AS (
        SELECT 
            f.bulan,
            'Total' AS channel,
            SUM(f.pk) AS pk,
            SUM(f.po) AS po,
            SUM(f.pb) AS pb,
            SUM(f.tot_ord) AS tot_ord,
            SUM(f.suk_ord) AS suk_ord,
            SUM(f.bat_ord) AS bat_ord
        FROM filtered f
        GROUP BY f.bulan
    ),
    grand_total AS (
        SELECT 
            'Grand Total' AS bulan,
            '' AS channel,
            COALESCE(SUM(f.pk), 0.00) AS pk,
            COALESCE(SUM(f.po), 0.00) AS po,
            COALESCE(SUM(f.pb), 0.00) AS pb,
            COALESCE(SUM(f.tot_ord), 0)::BIGINT AS tot_ord,
            COALESCE(SUM(f.suk_ord), 0)::BIGINT AS suk_ord,
            COALESCE(SUM(f.bat_ord), 0)::BIGINT AS bat_ord
        FROM filtered f
    ),
    combined AS (
        -- Channel rows
        SELECT 
            f.bulan,
            f.channel,
            f.pk,
            f.po,
            f.pb,
            ROUND(CASE WHEN f.suk_ord > 0 THEN f.pk / f.suk_ord ELSE 0.00 END, 2) AS avg_ord,
            f.tot_ord,
            f.suk_ord,
            f.bat_ord,
            f.bulan AS sort_bulan,
            1 AS sort_grp
        FROM filtered f

        UNION ALL

        -- Monthly total rows
        SELECT 
            m.bulan,
            m.channel,
            m.pk,
            m.po,
            m.pb,
            ROUND(CASE WHEN m.suk_ord > 0 THEN m.pk / m.suk_ord ELSE 0.00 END, 2) AS avg_ord,
            m.tot_ord,
            m.suk_ord,
            m.bat_ord,
            m.bulan AS sort_bulan,
            2 AS sort_grp
        FROM monthly_totals m

        UNION ALL

        -- Grand total row
        SELECT 
            g.bulan,
            g.channel,
            g.pk,
            g.po,
            g.pb,
            ROUND(CASE WHEN g.suk_ord > 0 THEN g.pk / g.suk_ord ELSE 0.00 END, 2) AS avg_ord,
            g.tot_ord,
            g.suk_ord,
            g.bat_ord,
            '9999-99' AS sort_bulan,
            3 AS sort_grp
        FROM grand_total g
    )
    SELECT 
        c.bulan::TEXT,
        c.channel::TEXT,
        c.pk AS pendapatan_kotor,
        c.po AS potongan_ojol,
        c.pb AS pendapatan_bersih,
        c.avg_ord AS rata_rata_order_per_customer,
        c.tot_ord::BIGINT AS total_order,
        c.suk_ord::BIGINT AS order_sukses,
        c.bat_ord::BIGINT AS order_batal
    FROM combined c
    ORDER BY c.sort_bulan ASC, c.sort_grp ASC, c.channel ASC;
END;
$$ LANGUAGE plpgsql;

-- ─────────────────────────────────────────────────────────────────────────────
-- Baseline vs Current Performance Function
-- Objective: Compare each outlet GMV & Order from 30-day baseline window
-- vs current period (p_start_date..p_end_date from filter Date Range)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION layer3_dim.get_baseline_vs_current(
    p_pic          TEXT    DEFAULT NULL,
    p_owner        TEXT    DEFAULT NULL,
    p_outlet       TEXT    DEFAULT NULL,
    p_start_date   DATE    DEFAULT CURRENT_DATE - INTERVAL '6 days',
    p_end_date     DATE    DEFAULT CURRENT_DATE,
    p_target_growth_pct NUMERIC DEFAULT 10.0
)
RETURNS TABLE (
    pic                  TEXT,
    owner_name           TEXT,
    outlet_name          TEXT,
    live_date            TEXT,
    age                  TEXT,
    selected_days        INT,
    baseline_gmv         NUMERIC(15,2),
    current_gmv          NUMERIC(15,2),
    baseline_daily_gmv   NUMERIC(15,2),
    current_daily_gmv    NUMERIC(15,2),
    daily_gmv_growth     NUMERIC(15,4),
    baseline_order       BIGINT,
    current_order        BIGINT,
    baseline_daily_order NUMERIC(15,2),
    current_daily_order  NUMERIC(15,2),
    daily_order_growth   NUMERIC(15,4),
    status               TEXT
) AS $$
DECLARE
    v_selected_days   INT;
    v_baseline_end    DATE;
    v_baseline_start  DATE;
BEGIN
    v_selected_days  := GREATEST((p_end_date - p_start_date) + 1, 1);
    v_baseline_end   := p_start_date - INTERVAL '1 day';
    v_baseline_start := v_baseline_end - INTERVAL '29 days';

    RETURN QUERY
    WITH target_outlets AS (
        SELECT DISTINCT
            COALESCE(NULLIF(TRIM(m.pic), ''), NULLIF(TRIM(m.bd_pic), ''), 'UNKNOWN') AS pic_val,
            COALESCE(c.owner_name, m.owner_name, 'UNKNOWN')                          AS owner_val,
            COALESCE(m.outlet_name, c.merchant_name, 'UNKNOWN')                     AS outlet_val,
            m.store_id,
            m.live_date AS live_dt
        FROM layer3_dim.dim_merchant_mapping m
        LEFT JOIN layer3_dim.dim_merchant_credentials c ON m.store_id = c.store_id
        WHERE UPPER(COALESCE(m.status, 'LIVE')) = 'LIVE'
          AND (p_pic    IS NULL OR p_pic    = '' OR LOWER(COALESCE(m.pic, m.bd_pic, ''))        = LOWER(p_pic))
          AND (p_owner  IS NULL OR p_owner  = '' OR LOWER(COALESCE(c.owner_name, m.owner_name, '')) = LOWER(p_owner))
          AND (p_outlet IS NULL OR p_outlet = '' OR LOWER(COALESCE(m.outlet_name, c.merchant_name, '')) = LOWER(p_outlet))
    ),
    perf AS (
        SELECT
            t.pic_val,
            t.owner_val,
            t.outlet_val,
            t.live_dt,
            COALESCE(SUM(CASE WHEN p.transaction_date BETWEEN v_baseline_start AND v_baseline_end THEN p.gmv          ELSE 0 END), 0.00)::NUMERIC(15,2) AS b_gmv,
            COALESCE(SUM(CASE WHEN p.transaction_date BETWEEN v_baseline_start AND v_baseline_end THEN p.total_orders ELSE 0 END), 0)::BIGINT          AS b_ord,
            COALESCE(SUM(CASE WHEN p.transaction_date BETWEEN p_start_date      AND p_end_date   THEN p.gmv          ELSE 0 END), 0.00)::NUMERIC(15,2) AS c_gmv,
            COALESCE(SUM(CASE WHEN p.transaction_date BETWEEN p_start_date      AND p_end_date   THEN p.total_orders ELSE 0 END), 0)::BIGINT          AS c_ord
        FROM target_outlets t
        LEFT JOIN layer3_dim.mv_outlet_daily_performance p ON p.store_id = t.store_id
        GROUP BY t.pic_val, t.owner_val, t.outlet_val, t.live_dt
    ),
    calc AS (
        SELECT
            p.pic_val,
            p.owner_val,
            p.outlet_val,
            COALESCE(p.live_dt, '-')   AS live_date_str,
            -- Age: (p_end_date - live_date) in Xmo Yw, live_dt is TEXT
            CASE
                WHEN p.live_dt IS NULL OR p.live_dt = '-' THEN '-'
                ELSE CONCAT(
                    FLOOR((p_end_date - p.live_dt::DATE)::NUMERIC / 30.4375)::INT, 'mo ',
                    FLOOR(((p_end_date - p.live_dt::DATE)::NUMERIC % 30.4375) / 7)::INT, 'w'
                )
            END AS age_str,
            v_selected_days                                          AS sel_days,
            p.b_gmv,
            p.c_gmv,
            -- Baseline Daily GMV = Baseline GMV / 30
            ROUND(p.b_gmv / 30.0, 2)                                AS bdg,
            -- Current Daily GMV  = Current GMV / Selected Days
            ROUND(p.c_gmv / v_selected_days, 2)                     AS cdg,
            -- Daily GMV Growth = (Current Daily / Baseline Daily) - 1
            CASE WHEN p.b_gmv > 0
                 THEN ROUND((ROUND(p.c_gmv / v_selected_days, 2) / ROUND(p.b_gmv / 30.0, 2)) - 1.0, 4)
                 ELSE NULL
            END AS gmv_growth,
            p.b_ord,
            p.c_ord,
            -- Baseline Daily Order = Baseline Order / 30
            ROUND(p.b_ord::NUMERIC / 30.0, 2)                       AS bdo,
            -- Current Daily Order  = Current Order / Selected Days
            ROUND(p.c_ord::NUMERIC / v_selected_days, 2)            AS cdo,
            -- Daily Order Growth = (Current Daily / Baseline Daily) - 1
            CASE WHEN p.b_ord > 0
                 THEN ROUND((ROUND(p.c_ord::NUMERIC / v_selected_days, 2) / ROUND(p.b_ord::NUMERIC / 30.0, 2)) - 1.0, 4)
                 ELSE NULL
            END AS ord_growth
        FROM perf p
    ),
    evaluated AS (
        SELECT
            c.*,
            CASE
                WHEN (c.gmv_growth IS NOT NULL AND c.gmv_growth >= (p_target_growth_pct / 100.0))
                 AND (c.ord_growth IS NOT NULL AND c.ord_growth >= (p_target_growth_pct / 100.0))
                 THEN 'Achieved'
                WHEN (c.gmv_growth IS NULL OR c.gmv_growth < (p_target_growth_pct / 100.0))
                 AND (c.ord_growth IS NOT NULL AND c.ord_growth >= (p_target_growth_pct / 100.0))
                 THEN 'GMV Below Target'
                WHEN (c.gmv_growth IS NOT NULL AND c.gmv_growth >= (p_target_growth_pct / 100.0))
                 AND (c.ord_growth IS NULL OR c.ord_growth < (p_target_growth_pct / 100.0))
                 THEN 'Order Below Target'
                ELSE 'Not Achieved'
            END AS res_status
        FROM calc c
    )
    SELECT
        e.pic_val::TEXT,
        e.owner_val::TEXT,
        e.outlet_val::TEXT,
        e.live_date_str::TEXT,
        e.age_str::TEXT,
        e.sel_days::INT,
        e.b_gmv,
        e.c_gmv,
        e.bdg,
        e.cdg,
        e.gmv_growth,
        e.b_ord,
        e.c_ord,
        e.bdo,
        e.cdo,
        e.ord_growth,
        e.res_status::TEXT
    FROM evaluated e
    ORDER BY e.owner_val ASC, e.outlet_val ASC;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 9. MATERIALIZED VIEW LAPORAN JAM RAMAI (HOURLY TRAFFIC & PEAK HOURS)
-- ============================================================================
DROP MATERIALIZED VIEW IF EXISTS layer3_dim.mv_jam_ramai CASCADE;

CREATE MATERIALIZED VIEW layer3_dim.mv_jam_ramai AS
SELECT 
    COALESCE(c.owner_name, m.owner_name, 'UNKNOWN') AS owner_name,
    COALESCE(m.outlet_name, c.merchant_name, ft.outlet_name, 'UNKNOWN') AS outlet_name,
    COALESCE(m.brand, 'UNKNOWN') AS brand,
    ft.merchant_id AS store_id,
    ft.transaction_date,
    TO_CHAR(ft.transaction_date, 'YYYY-MM') AS bulan,
    CASE EXTRACT(DOW FROM ft.transaction_date)
        WHEN 0 THEN 'Minggu'
        WHEN 1 THEN 'Senin'
        WHEN 2 THEN 'Selasa'
        WHEN 3 THEN 'Rabu'
        WHEN 4 THEN 'Kamis'
        WHEN 5 THEN 'Jumat'
        WHEN 6 THEN 'Sabtu'
    END AS hari_name,
    EXTRACT(DOW FROM ft.transaction_date)::INT AS dow_num,
    COALESCE(ft.hour, 0) AS jam,
    CASE 
        WHEN COALESCE(ft.hour, 0) BETWEEN 6 AND 9 THEN 'Breakfast (06:00-09:59)'
        WHEN COALESCE(ft.hour, 0) BETWEEN 10 AND 13 THEN 'Lunch (10:00-13:59)'
        WHEN COALESCE(ft.hour, 0) BETWEEN 14 AND 16 THEN 'Afternoon (14:00-16:59)'
        WHEN COALESCE(ft.hour, 0) BETWEEN 17 AND 20 THEN 'Dinner (17:00-20:59)'
        ELSE 'Late Night (21:00-05:59)'
    END AS slot_waktu,
    ft.platform AS channel,
    SUM(CASE WHEN ft.is_success = 1 THEN ft.net_sales ELSE 0.00 END) AS pendapatan_kotor,
    SUM(CASE WHEN ft.is_success = 1 THEN ft.ofd_fees ELSE 0.00 END) AS potongan_ojol,
    SUM(CASE WHEN ft.is_success = 1 THEN ft.revenue ELSE 0.00 END) AS pendapatan_bersih,
    COUNT(*)::BIGINT AS total_order,
    COUNT(CASE WHEN ft.is_success = 1 THEN 1 END)::BIGINT AS order_sukses,
    COUNT(CASE WHEN ft.is_cancelled = 1 OR ft.is_success = 0 THEN 1 END)::BIGINT AS order_batal
FROM layer3_dim.fact_transactions ft
LEFT JOIN layer3_dim.dim_merchant_credentials c ON ft.merchant_id = c.store_id
LEFT JOIN layer3_dim.dim_merchant_mapping m ON ft.merchant_id = m.store_id
WHERE UPPER(COALESCE(m.status, 'LIVE')) = 'LIVE'
GROUP BY 
    COALESCE(c.owner_name, m.owner_name, 'UNKNOWN'),
    COALESCE(m.outlet_name, c.merchant_name, ft.outlet_name, 'UNKNOWN'),
    COALESCE(m.brand, 'UNKNOWN'),
    ft.merchant_id,
    ft.transaction_date,
    EXTRACT(DOW FROM ft.transaction_date),
    COALESCE(ft.hour, 0),
    ft.platform;

DROP INDEX IF EXISTS layer3_dim.idx_mv_jam_ramai;
DROP INDEX IF EXISTS layer3_dim.idx_mv_jam_ramai_owner;
DROP INDEX IF EXISTS layer3_dim.idx_mv_jam_ramai_jam;

CREATE UNIQUE INDEX idx_mv_jam_ramai ON layer3_dim.mv_jam_ramai (store_id, transaction_date, jam, channel);
CREATE INDEX idx_mv_jam_ramai_owner ON layer3_dim.mv_jam_ramai (owner_name);
CREATE INDEX idx_mv_jam_ramai_jam ON layer3_dim.mv_jam_ramai (jam);

-- -- ============================================================================
-- 10. STORED FUNCTIONS LAPORAN JAM RAMAI (SUMMARY, SLOT WAKTU, MATRIKS HARI)
-- ============================================================================
DROP FUNCTION IF EXISTS layer3_dim.get_laporan_jam_ramai_summary(text,text,text,date,date) CASCADE;
DROP FUNCTION IF EXISTS layer3_dim.get_laporan_jam_ramai_by_slot(text,text,text,date,date) CASCADE;
DROP FUNCTION IF EXISTS layer3_dim.get_laporan_jam_ramai_by_day(text,text,text,date,date) CASCADE;

CREATE OR REPLACE FUNCTION layer3_dim.get_laporan_jam_ramai_summary(
    p_owner TEXT DEFAULT NULL,
    p_outlet TEXT DEFAULT NULL,
    p_brand TEXT DEFAULT NULL,
    p_start_date DATE DEFAULT '2026-01-01',
    p_end_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    jam INT,
    jam_label TEXT,
    slot_waktu TEXT,
    pendapatan_kotor NUMERIC(15,2),
    potongan_ojol NUMERIC(15,2),
    pendapatan_bersih NUMERIC(15,2),
    rata_rata_order_per_customer NUMERIC(15,2),
    total_order BIGINT,
    order_sukses BIGINT,
    order_batal BIGINT,
    pct_batal NUMERIC(5,2),
    is_peak_hour_orders INT,
    is_peak_hour_sales INT
) AS $$
BEGIN
    RETURN QUERY
    WITH filtered AS (
        SELECT 
            mv.jam,
            MIN(mv.slot_waktu) AS slot_waktu,
            SUM(mv.pendapatan_kotor) AS pk,
            SUM(mv.potongan_ojol) AS po,
            SUM(mv.pendapatan_bersih) AS pb,
            SUM(mv.total_order) AS tot_ord,
            SUM(mv.order_sukses) AS suk_ord,
            SUM(mv.order_batal) AS bat_ord
        FROM layer3_dim.mv_jam_ramai mv
        WHERE (p_owner IS NULL OR p_owner = '' OR LOWER(mv.owner_name) = LOWER(p_owner))
          AND (p_outlet IS NULL OR p_outlet = '' OR LOWER(mv.outlet_name) = LOWER(p_outlet))
          AND (p_brand IS NULL OR p_brand = '' OR LOWER(mv.brand) = LOWER(p_brand))
          AND mv.transaction_date BETWEEN COALESCE(p_start_date, '2026-01-01') AND COALESCE(p_end_date, CURRENT_DATE)
        GROUP BY mv.jam
    ),
    max_stats AS (
        SELECT 
            COALESCE(MAX(f.suk_ord), 0) AS max_suk,
            COALESCE(MAX(f.pk), 0.00) AS max_pk
        FROM filtered f
    ),
    combined AS (
        SELECT 
            f.jam,
            TO_CHAR(f.jam, 'FM00') || ':00 - ' || TO_CHAR(f.jam, 'FM00') || ':59' AS jam_label,
            f.slot_waktu,
            f.pk,
            f.po,
            f.pb,
            ROUND(CASE WHEN f.suk_ord > 0 THEN f.pk / f.suk_ord ELSE 0.00 END, 2) AS avg_ord,
            f.tot_ord,
            f.suk_ord,
            f.bat_ord,
            ROUND(CASE WHEN f.tot_ord > 0 THEN (f.bat_ord::NUMERIC / f.tot_ord::NUMERIC) * 100.0 ELSE 0.00 END, 2) AS pct_batal,
            CASE WHEN f.suk_ord = m.max_suk AND f.suk_ord > 0 THEN 1 ELSE 0 END AS is_peak_ord,
            CASE WHEN f.pk = m.max_pk AND f.pk > 0 THEN 1 ELSE 0 END AS is_peak_sales,
            1 AS s_grp
        FROM filtered f
        CROSS JOIN max_stats m

        UNION ALL

        SELECT 
            99 AS jam,
            'Grand Total' AS jam_label,
            '' AS slot_waktu,
            COALESCE(SUM(f.pk), 0.00) AS pk,
            COALESCE(SUM(f.po), 0.00) AS po,
            COALESCE(SUM(f.pb), 0.00) AS pb,
            ROUND(CASE WHEN SUM(f.suk_ord) > 0 THEN SUM(f.pk) / SUM(f.suk_ord) ELSE 0.00 END, 2) AS avg_ord,
            COALESCE(SUM(f.tot_ord), 0)::BIGINT AS tot_ord,
            COALESCE(SUM(f.suk_ord), 0)::BIGINT AS suk_ord,
            COALESCE(SUM(f.bat_ord), 0)::BIGINT AS bat_ord,
            ROUND(CASE WHEN SUM(f.tot_ord) > 0 THEN (SUM(f.bat_ord)::NUMERIC / SUM(f.tot_ord)::NUMERIC) * 100.0 ELSE 0.00 END, 2) AS pct_batal,
            0 AS is_peak_ord,
            0 AS is_peak_sales,
            2 AS s_grp
        FROM filtered f
    )
    SELECT 
        c.jam::INT,
        c.jam_label::TEXT,
        c.slot_waktu::TEXT,
        c.pk AS pendapatan_kotor,
        c.po AS potongan_ojol,
        c.pb AS pendapatan_bersih,
        c.avg_ord AS rata_rata_order_per_customer,
        c.tot_ord::BIGINT AS total_order,
        c.suk_ord::BIGINT AS order_sukses,
        c.bat_ord::BIGINT AS order_batal,
        c.pct_batal AS pct_batal,
        c.is_peak_ord::INT,
        c.is_peak_sales::INT
    FROM combined c
    ORDER BY c.s_grp ASC, c.jam ASC;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION layer3_dim.get_laporan_jam_ramai_by_slot(
    p_owner TEXT DEFAULT NULL,
    p_outlet TEXT DEFAULT NULL,
    p_brand TEXT DEFAULT NULL,
    p_start_date DATE DEFAULT '2026-01-01',
    p_end_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    slot_waktu TEXT,
    pendapatan_kotor NUMERIC(15,2),
    potongan_ojol NUMERIC(15,2),
    pendapatan_bersih NUMERIC(15,2),
    rata_rata_order_per_customer NUMERIC(15,2),
    total_order BIGINT,
    order_sukses BIGINT,
    order_batal BIGINT,
    pct_batal NUMERIC(5,2)
) AS $$
BEGIN
    RETURN QUERY
    WITH filtered AS (
        SELECT 
            mv.slot_waktu,
            SUM(mv.pendapatan_kotor) AS pk,
            SUM(mv.potongan_ojol) AS po,
            SUM(mv.pendapatan_bersih) AS pb,
            SUM(mv.total_order) AS tot_ord,
            SUM(mv.order_sukses) AS suk_ord,
            SUM(mv.order_batal) AS bat_ord
        FROM layer3_dim.mv_jam_ramai mv
        WHERE (p_owner IS NULL OR p_owner = '' OR LOWER(mv.owner_name) = LOWER(p_owner))
          AND (p_outlet IS NULL OR p_outlet = '' OR LOWER(mv.outlet_name) = LOWER(p_outlet))
          AND (p_brand IS NULL OR p_brand = '' OR LOWER(mv.brand) = LOWER(p_brand))
          AND mv.transaction_date BETWEEN COALESCE(p_start_date, '2026-01-01') AND COALESCE(p_end_date, CURRENT_DATE)
        GROUP BY mv.slot_waktu
    ),
    combined AS (
        SELECT 
            f.slot_waktu,
            f.pk,
            f.po,
            f.pb,
            ROUND(CASE WHEN f.suk_ord > 0 THEN f.pk / f.suk_ord ELSE 0.00 END, 2) AS avg_ord,
            f.tot_ord,
            f.suk_ord,
            f.bat_ord,
            ROUND(CASE WHEN f.tot_ord > 0 THEN (f.bat_ord::NUMERIC / f.tot_ord::NUMERIC) * 100.0 ELSE 0.00 END, 2) AS pct_batal,
            1 AS s_grp
        FROM filtered f

        UNION ALL

        SELECT 
            'Grand Total' AS slot_waktu,
            COALESCE(SUM(f.pk), 0.00) AS pk,
            COALESCE(SUM(f.po), 0.00) AS po,
            COALESCE(SUM(f.pb), 0.00) AS pb,
            ROUND(CASE WHEN SUM(f.suk_ord) > 0 THEN SUM(f.pk) / SUM(f.suk_ord) ELSE 0.00 END, 2) AS avg_ord,
            COALESCE(SUM(f.tot_ord), 0)::BIGINT AS tot_ord,
            COALESCE(SUM(f.suk_ord), 0)::BIGINT AS suk_ord,
            COALESCE(SUM(f.bat_ord), 0)::BIGINT AS bat_ord,
            ROUND(CASE WHEN SUM(f.tot_ord) > 0 THEN (SUM(f.bat_ord)::NUMERIC / SUM(f.tot_ord)::NUMERIC) * 100.0 ELSE 0.00 END, 2) AS pct_batal,
            2 AS s_grp
        FROM filtered f
    )
    SELECT 
        c.slot_waktu::TEXT,
        c.pk AS pendapatan_kotor,
        c.po AS potongan_ojol,
        c.pb AS pendapatan_bersih,
        c.avg_ord AS rata_rata_order_per_customer,
        c.tot_ord::BIGINT AS total_order,
        c.suk_ord::BIGINT AS order_sukses,
        c.bat_ord::BIGINT AS order_batal,
        c.pct_batal AS pct_batal
    FROM combined c
    ORDER BY c.s_grp ASC, c.slot_waktu ASC;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION layer3_dim.get_laporan_jam_ramai_by_day(
    p_owner TEXT DEFAULT NULL,
    p_outlet TEXT DEFAULT NULL,
    p_brand TEXT DEFAULT NULL,
    p_start_date DATE DEFAULT '2026-01-01',
    p_end_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    dow_num INT,
    hari_name TEXT,
    jam INT,
    jam_label TEXT,
    pendapatan_kotor NUMERIC(15,2),
    pendapatan_bersih NUMERIC(15,2),
    total_order BIGINT,
    order_sukses BIGINT,
    order_batal BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        mv.dow_num::INT,
        mv.hari_name::TEXT,
        mv.jam::INT,
        (TO_CHAR(mv.jam, 'FM00') || ':00 - ' || TO_CHAR(mv.jam, 'FM00') || ':59')::TEXT AS jam_label,
        SUM(mv.pendapatan_kotor) AS pendapatan_kotor,
        SUM(mv.pendapatan_bersih) AS pendapatan_bersih,
        SUM(mv.total_order)::BIGINT AS total_order,
        SUM(mv.order_sukses)::BIGINT AS order_sukses,
        SUM(mv.order_batal)::BIGINT AS order_batal
    FROM layer3_dim.mv_jam_ramai mv
    WHERE (p_owner IS NULL OR p_owner = '' OR LOWER(mv.owner_name) = LOWER(p_owner))
      AND (p_outlet IS NULL OR p_outlet = '' OR LOWER(mv.outlet_name) = LOWER(p_outlet))
      AND (p_brand IS NULL OR p_brand = '' OR LOWER(mv.brand) = LOWER(p_brand))
      AND mv.transaction_date BETWEEN COALESCE(p_start_date, '2026-01-01') AND COALESCE(p_end_date, CURRENT_DATE)
    GROUP BY mv.dow_num, mv.hari_name, mv.jam
    ORDER BY 
        CASE WHEN mv.dow_num = 0 THEN 7 ELSE mv.dow_num END ASC,
        mv.jam ASC;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 11. MATERIALIZED VIEW ORDER SUKSES VS ORDER BATAL (ORDER STATUS ANALYSIS)
-- ============================================================================
DROP MATERIALIZED VIEW IF EXISTS layer3_dim.mv_order_status CASCADE;

-- ============================================================================
-- 12. VIEW ORDER STATUS (OPTIMIZED STANDARD VIEW FROM MV_LAPORAN_OJOL)
-- ============================================================================
DROP MATERIALIZED VIEW IF EXISTS layer3_dim.mv_order_status CASCADE;
DROP VIEW IF EXISTS layer3_dim.v_order_status CASCADE;
DROP VIEW IF EXISTS layer3_dim.mv_order_status CASCADE;

CREATE OR REPLACE VIEW layer3_dim.v_order_status AS
SELECT 
    mv.owner_name,
    mv.outlet_name,
    mv.brand,
    mv.store_id,
    mv.transaction_date,
    mv.channel,
    SUM(mv.total_order)::BIGINT AS total_order,
    SUM(mv.order_sukses)::BIGINT AS order_sukses,
    SUM(mv.order_batal)::BIGINT AS order_batal,
    SUM(mv.pendapatan_kotor) AS pendapatan_kotor,
    SUM(mv.pendapatan_bersih) AS pendapatan_bersih
FROM layer3_dim.mv_laporan_ojol mv
GROUP BY 
    mv.owner_name,
    mv.outlet_name,
    mv.brand,
    mv.store_id,
    mv.transaction_date,
    mv.channel;

-- Backward compatibility view alias
CREATE OR REPLACE VIEW layer3_dim.mv_order_status AS 
SELECT * FROM layer3_dim.v_order_status;

-- ============================================================================
-- 12. STORED FUNCTION GET LAPORAN ORDER STATUS
-- ============================================================================
DROP FUNCTION IF EXISTS layer3_dim.get_laporan_order_status(text,text,date,date) CASCADE;

CREATE OR REPLACE FUNCTION layer3_dim.get_laporan_order_status(
    p_outlet TEXT DEFAULT NULL,
    p_brand TEXT DEFAULT NULL,
    p_start_date DATE DEFAULT '2026-01-01',
    p_end_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    channel TEXT,
    total_order BIGINT,
    order_sukses BIGINT,
    order_batal BIGINT,
    pct_sukses NUMERIC(5,2),
    pct_batal NUMERIC(5,2),
    pendapatan_kotor NUMERIC(15,2),
    pendapatan_bersih NUMERIC(15,2)
) AS $$
BEGIN
    RETURN QUERY
    WITH filtered AS (
        SELECT 
            mv.channel::TEXT AS ch,
            COALESCE(SUM(mv.total_order), 0) AS tot_ord,
            COALESCE(SUM(mv.order_sukses), 0) AS suk_ord,
            COALESCE(SUM(mv.order_batal), 0) AS bat_ord,
            COALESCE(SUM(mv.pendapatan_kotor), 0.00) AS pk,
            COALESCE(SUM(mv.pendapatan_bersih), 0.00) AS pb
        FROM layer3_dim.mv_order_status mv
        WHERE (p_outlet IS NULL OR p_outlet = '' OR LOWER(mv.outlet_name) = LOWER(p_outlet))
          AND (p_brand IS NULL OR p_brand = '' OR LOWER(mv.brand) = LOWER(p_brand))
          AND mv.transaction_date BETWEEN COALESCE(p_start_date, '2026-01-01') AND COALESCE(p_end_date, CURRENT_DATE)
        GROUP BY mv.channel
    ),
    all_ofd AS (
        SELECT 
            'All OFD'::TEXT AS ch,
            COALESCE(SUM(f.tot_ord), 0) AS tot_ord,
            COALESCE(SUM(f.suk_ord), 0) AS suk_ord,
            COALESCE(SUM(f.bat_ord), 0) AS bat_ord,
            COALESCE(SUM(f.pk), 0.00) AS pk,
            COALESCE(SUM(f.pb), 0.00) AS pb,
            0 AS s_grp
        FROM filtered f
        
        UNION ALL
        
        SELECT 
            f.ch,
            f.tot_ord,
            f.suk_ord,
            f.bat_ord,
            f.pk,
            f.pb,
            1 AS s_grp
        FROM filtered f
        WHERE LOWER(f.ch) <> 'gofood'
    )
    SELECT 
        a.ch AS channel,
        a.tot_ord::BIGINT AS total_order,
        a.suk_ord::BIGINT AS order_sukses,
        a.bat_ord::BIGINT AS order_batal,
        ROUND(CASE WHEN a.tot_ord > 0 THEN (a.suk_ord::NUMERIC / a.tot_ord::NUMERIC) * 100.0 ELSE 0.00 END, 2) AS pct_sukses,
        ROUND(CASE WHEN a.tot_ord > 0 THEN (a.bat_ord::NUMERIC / a.tot_ord::NUMERIC) * 100.0 ELSE 0.00 END, 2) AS pct_batal,
        a.pk AS pendapatan_kotor,
        a.pb AS pendapatan_bersih
    FROM all_ofd a
    ORDER BY a.s_grp ASC, a.ch ASC;
END;
$$ LANGUAGE plpgsql;

-- ─────────────────────────────────────────────────────────────────────────────
-- Order Ranking Function
-- Objective: Rank active outlets by total success order & GMV for selected date range
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION layer3_dim.get_order_ranking(
    p_pic          TEXT    DEFAULT NULL,
    p_owner        TEXT    DEFAULT NULL,
    p_outlet       TEXT    DEFAULT NULL,
    p_start_date   DATE    DEFAULT CURRENT_DATE - INTERVAL '6 days',
    p_end_date     DATE    DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    pic          TEXT,
    owner_name   TEXT,
    outlet_name  TEXT,
    live_date    TEXT,
    order_sukses BIGINT,
    total_gmv    NUMERIC(15,2)
) AS $$
BEGIN
    RETURN QUERY
    WITH target_outlets AS (
        SELECT DISTINCT
            COALESCE(NULLIF(TRIM(m.pic), ''), NULLIF(TRIM(m.bd_pic), ''), 'UNKNOWN') AS pic_val,
            COALESCE(c.owner_name, m.owner_name, 'UNKNOWN')                          AS owner_val,
            COALESCE(m.outlet_name, c.merchant_name, 'UNKNOWN')                     AS outlet_val,
            m.store_id,
            m.live_date AS live_dt
        FROM layer3_dim.dim_merchant_mapping m
        LEFT JOIN layer3_dim.dim_merchant_credentials c ON m.store_id = c.store_id
        WHERE UPPER(COALESCE(m.status, 'LIVE')) = 'LIVE'
          AND (p_pic    IS NULL OR p_pic    = '' OR LOWER(COALESCE(m.pic, m.bd_pic, ''))        = LOWER(p_pic))
          AND (p_owner  IS NULL OR p_owner  = '' OR LOWER(COALESCE(c.owner_name, m.owner_name, '')) = LOWER(p_owner))
          AND (p_outlet IS NULL OR p_outlet = '' OR LOWER(COALESCE(m.outlet_name, c.merchant_name, '')) = LOWER(p_outlet))
    ),
    perf AS (
        SELECT
            t.pic_val,
            t.owner_val,
            t.outlet_val,
            t.live_dt,
            COALESCE(SUM(p.total_orders), 0)::BIGINT AS tot_ord,
            COALESCE(SUM(p.gmv), 0.00)::NUMERIC(15,2) AS tot_gmv
        FROM target_outlets t
        LEFT JOIN layer3_dim.mv_outlet_daily_performance p 
               ON p.store_id = t.store_id
              AND p.transaction_date BETWEEN p_start_date AND p_end_date
        GROUP BY t.pic_val, t.owner_val, t.outlet_val, t.live_dt
    )
    SELECT
        p.pic_val::TEXT,
        p.owner_val::TEXT,
        p.outlet_val::TEXT,
        COALESCE(p.live_dt, '-')::TEXT AS live_date,
        p.tot_ord::BIGINT              AS order_sukses,
        p.tot_gmv::NUMERIC(15,2)       AS total_gmv
    FROM perf p
    ORDER BY p.tot_ord DESC, p.tot_gmv DESC, p.outlet_val ASC;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 13. MATERIALIZED VIEW PERFORMA COMPARISON
-- ============================================================================
-- 14. VIEW PERFORMA COMPARISON (OPTIMIZED STANDARD VIEW FROM MV_LAPORAN_OJOL)
-- ============================================================================
DROP MATERIALIZED VIEW IF EXISTS layer3_dim.mv_performa_comparison CASCADE;
DROP VIEW IF EXISTS layer3_dim.v_performa_comparison CASCADE;
DROP VIEW IF EXISTS layer3_dim.mv_performa_comparison CASCADE;

CREATE OR REPLACE VIEW layer3_dim.v_performa_comparison AS
SELECT 
    mv.owner_name,
    mv.outlet_name,
    mv.brand,
    mv.store_id,
    mv.transaction_date,
    SUM(mv.pendapatan_kotor) AS pendapatan_kotor,
    SUM(mv.potongan_ojol) AS potongan_ojol,
    SUM(mv.pendapatan_bersih) AS pendapatan_bersih,
    SUM(mv.total_order)::BIGINT AS total_order,
    SUM(mv.order_sukses)::BIGINT AS order_sukses,
    SUM(mv.order_batal)::BIGINT AS order_batal
FROM layer3_dim.mv_laporan_ojol mv
GROUP BY 
    mv.owner_name,
    mv.outlet_name,
    mv.brand,
    mv.store_id,
    mv.transaction_date;

-- Backward compatibility view alias
CREATE OR REPLACE VIEW layer3_dim.mv_performa_comparison AS 
SELECT * FROM layer3_dim.v_performa_comparison;

-- ============================================================================
-- 14. STORED FUNCTION GET LAPORAN PERFORMA COMPARISON
-- ============================================================================
DROP FUNCTION IF EXISTS layer3_dim.get_laporan_performa_comparison(text,text,text,text,date,date) CASCADE;

CREATE OR REPLACE FUNCTION layer3_dim.get_laporan_performa_comparison(
    p_tipe_laporan TEXT DEFAULT 'Bulanan',
    p_owner TEXT DEFAULT NULL,
    p_outlet TEXT DEFAULT NULL,
    p_brand TEXT DEFAULT NULL,
    p_start_date DATE DEFAULT '2026-01-01',
    p_end_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    periode_label TEXT,
    pendapatan_kotor NUMERIC(15,2),
    potongan_ojol NUMERIC(15,2),
    pendapatan_bersih NUMERIC(15,2),
    rata_rata_order_per_customer NUMERIC(15,2),
    total_order BIGINT,
    order_sukses BIGINT,
    order_batal BIGINT
) AS $$
DECLARE
    v_mode TEXT := COALESCE(LOWER(TRIM(p_tipe_laporan)), 'bulanan');
BEGIN
    RETURN QUERY
    WITH raw_filtered AS (
        SELECT 
            mv.transaction_date,
            mv.pendapatan_kotor AS pk,
            mv.potongan_ojol AS po,
            mv.pendapatan_bersih AS pb,
            mv.total_order AS tot_ord,
            mv.order_sukses AS suk_ord,
            mv.order_batal AS bat_ord,
            CASE 
                WHEN v_mode = 'harian' THEN TO_CHAR(mv.transaction_date, 'YYYY-MM-DD')
                WHEN v_mode = 'mingguan' THEN TO_CHAR(mv.transaction_date, 'IYYY-"W"IW')
                ELSE TO_CHAR(mv.transaction_date, 'YYYY-MM')
            END AS p_key,
            CASE 
                WHEN v_mode = 'harian' THEN TO_CHAR(mv.transaction_date, 'DD/MM/YYYY')
                WHEN v_mode = 'mingguan' THEN 'Minggu ' || TO_CHAR(mv.transaction_date, 'IW (IYYY)')
                ELSE TO_CHAR(mv.transaction_date, 'TMMonth YYYY')
            END AS p_label
        FROM layer3_dim.mv_performa_comparison mv
        WHERE (p_owner IS NULL OR p_owner = '' OR LOWER(mv.owner_name) = LOWER(p_owner))
          AND (p_outlet IS NULL OR p_outlet = '' OR LOWER(mv.outlet_name) = LOWER(p_outlet))
          AND (p_brand IS NULL OR p_brand = '' OR LOWER(mv.brand) = LOWER(p_brand))
          AND mv.transaction_date BETWEEN COALESCE(p_start_date, '2026-01-01') AND COALESCE(p_end_date, CURRENT_DATE)
    ),
    grouped AS (
        SELECT 
            rf.p_key,
            rf.p_label,
            SUM(rf.pk) AS pk,
            SUM(rf.po) AS po,
            SUM(rf.pb) AS pb,
            SUM(rf.tot_ord) AS tot_ord,
            SUM(rf.suk_ord) AS suk_ord,
            SUM(rf.bat_ord) AS bat_ord,
            ROUND(CASE WHEN SUM(rf.suk_ord) > 0 THEN SUM(rf.pk) / SUM(rf.suk_ord) ELSE 0.00 END, 2) AS avg_ord,
            1 AS s_grp
        FROM raw_filtered rf
        GROUP BY rf.p_key, rf.p_label
    ),
    combined AS (
        SELECT 
            g.p_key,
            g.p_label,
            g.pk,
            g.po,
            g.pb,
            g.avg_ord,
            g.tot_ord,
            g.suk_ord,
            g.bat_ord,
            g.s_grp
        FROM grouped g

        UNION ALL

        SELECT 
            '9999-99' AS p_key,
            'Grand Total' AS p_label,
            COALESCE(SUM(g.pk), 0.00) AS pk,
            COALESCE(SUM(g.po), 0.00) AS po,
            COALESCE(SUM(g.pb), 0.00) AS pb,
            ROUND(CASE WHEN SUM(g.suk_ord) > 0 THEN SUM(g.pk) / SUM(g.suk_ord) ELSE 0.00 END, 2) AS avg_ord,
            COALESCE(SUM(g.tot_ord), 0)::BIGINT AS tot_ord,
            COALESCE(SUM(g.suk_ord), 0)::BIGINT AS suk_ord,
            COALESCE(SUM(g.bat_ord), 0)::BIGINT AS bat_ord,
            2 AS s_grp
        FROM grouped g
    )
    SELECT 
        c.p_label::TEXT AS periode_label,
        c.pk AS pendapatan_kotor,
        c.po AS potongan_ojol,
        c.pb AS pendapatan_bersih,
        c.avg_ord AS rata_rata_order_per_customer,
        c.tot_ord::BIGINT AS total_order,
        c.suk_ord::BIGINT AS order_sukses,
        c.bat_ord::BIGINT AS order_batal
    FROM combined c
    ORDER BY c.s_grp ASC, c.p_key ASC;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 15. STORED FUNCTION GET PERFORMA COMPARISON CHARTS
-- ============================================================================
DROP FUNCTION IF EXISTS layer3_dim.get_performa_comparison_charts(text,text,text,date,date) CASCADE;

CREATE OR REPLACE FUNCTION layer3_dim.get_performa_comparison_charts(
    p_outlet TEXT DEFAULT NULL,
    p_brand TEXT DEFAULT NULL,
    p_channel TEXT DEFAULT NULL,
    p_start_date DATE DEFAULT '2026-01-01',
    p_end_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    periode_label TEXT,
    pendapatan_kotor NUMERIC(15,2),
    potongan_ojol NUMERIC(15,2),
    pendapatan_bersih NUMERIC(15,2),
    total_order BIGINT,
    order_sukses BIGINT,
    order_batal BIGINT
) AS $$
BEGIN
    RETURN QUERY
    WITH filtered AS (
        SELECT 
            TO_CHAR(mv.transaction_date, 'YYYY-MM') AS p_key,
            TO_CHAR(mv.transaction_date, 'TMMonth YYYY') AS p_label,
            SUM(mv.pendapatan_kotor) AS pk,
            SUM(mv.potongan_ojol) AS po,
            SUM(mv.pendapatan_bersih) AS pb,
            SUM(mv.total_order) AS tot_ord,
            SUM(mv.order_sukses) AS suk_ord,
            SUM(mv.order_batal) AS bat_ord
        FROM layer3_dim.mv_laporan_ojol mv
        WHERE (p_outlet IS NULL OR p_outlet = '' OR LOWER(mv.outlet_name) = LOWER(p_outlet))
          AND (p_brand IS NULL OR p_brand = '' OR LOWER(mv.brand) = LOWER(p_brand))
          AND (p_channel IS NULL OR p_channel = '' OR LOWER(mv.channel) = LOWER(p_channel))
          AND mv.transaction_date BETWEEN COALESCE(p_start_date, '2026-01-01') AND COALESCE(p_end_date, CURRENT_DATE)
        GROUP BY TO_CHAR(mv.transaction_date, 'YYYY-MM'), TO_CHAR(mv.transaction_date, 'TMMonth YYYY')
    )
    SELECT 
        f.p_label::TEXT AS periode_label,
        f.pk AS pendapatan_kotor,
        f.po AS potongan_ojol,
        f.pb AS pendapatan_bersih,
        f.tot_ord::BIGINT AS total_order,
        f.suk_ord::BIGINT AS order_sukses,
        f.bat_ord::BIGINT AS order_batal
    FROM filtered f
    ORDER BY f.p_key ASC;
END;
$$ LANGUAGE plpgsql;
