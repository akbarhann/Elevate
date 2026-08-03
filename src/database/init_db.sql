-- STORED PROCEDURE REFRESH FACT TRANSACTIONS (STANDARDIZED STATUS & FINANCIAL METRICS)
CREATE OR REPLACE FUNCTION refresh_fact_transactions()
RETURNS void AS $$
BEGIN

    -- 1. PROSES DATA GRABFOOD (Standardized Status: Transferred & Completed -> COMPLETED)
    INSERT INTO layer3_dim.fact_transactions (
        platform, external_id, transaction_date, created_on, year, month, week, hour,
        merchant_id, group_code, outlet_name, branch_name, store_name, status,
        is_success, is_cancelled,
        gross_amount, discounts, delivery_discount, net_sales,
        marketing_fee, commission, ofd_fees, revenue,
        context, raw_record_id
    )
    WITH grab_ranked AS (
        SELECT 
            stg.*,
            ROW_NUMBER() OVER(
                PARTITION BY stg.long_order_id 
                ORDER BY CASE WHEN stg.order_type = 'Auto-Paid' THEN 1 ELSE 2 END, stg.id DESC
            ) as rn
        FROM layer2_clean.stg_grab_orders stg
        WHERE stg.long_order_id IS NOT NULL 
          AND stg.long_order_id <> ''
    )
    SELECT 
        'GrabFood',
        stg.long_order_id,
        TO_DATE(SUBSTRING(stg.created_on FROM 1 FOR 10), 'YYYY-MM-DD'),
        TO_TIMESTAMP(stg.created_on, 'YYYY-MM-DD "at" HH24:MI'),
        EXTRACT(YEAR FROM TO_TIMESTAMP(stg.created_on, 'YYYY-MM-DD "at" HH24:MI'))::INTEGER,
        stg.month,
        TO_CHAR(TO_TIMESTAMP(stg.created_on, 'YYYY-MM-DD "at" HH24:MI'), 'YY-MM-') || 'W' || TO_CHAR(TO_TIMESTAMP(stg.created_on, 'YYYY-MM-DD "at" HH24:MI'), 'W'),
        EXTRACT(HOUR FROM TO_TIMESTAMP(stg.created_on, 'YYYY-MM-DD "at" HH24:MI'))::INTEGER,
        stg.store_id,
        COALESCE(m.group_code, 'UNKNOWN'),
        COALESCE(m.outlet_name, stg.merchant_name),
        COALESCE(m.nama_resto_final, m.nama_tarikan, 'UNKNOWN'),
        stg.store_name,
        stg.status,
        CASE WHEN LOWER(stg.status) IN ('transferred', 'completed', 'ditransfer', 'success', 'sukses') THEN 1 ELSE 0 END,
        CASE WHEN LOWER(stg.status) IN ('cancelled', 'dibatalkan', 'batal') THEN 1 ELSE 0 END,
        stg.amount,
        stg.discount_merchant_funded,
        stg.delivery_fee_discount_merchant_funded,
        stg.net_sales,
        stg.marketing_success_fee,
        stg.order_commission,
        ABS(COALESCE(stg.order_commission, 0) + COALESCE(stg.marketing_success_fee, 0)) as ofd_fees,
        stg.total,
        CASE WHEN stg.total <> stg.amount THEN 'Refund Adjusted' ELSE NULL END,
        stg.id
    FROM grab_ranked stg
    LEFT JOIN layer3_dim.dim_merchant_mapping m ON stg.store_id = m.store_id
    WHERE stg.rn = 1
    ON CONFLICT (platform, external_id) 
    DO UPDATE SET
        status = EXCLUDED.status,
        is_success = EXCLUDED.is_success,
        is_cancelled = EXCLUDED.is_cancelled,
        revenue = EXCLUDED.revenue,
        context = EXCLUDED.context,
        updated_at = CURRENT_TIMESTAMP;

    -- 2. PROSES DATA SHOPEEFOOD (Standardized Status: completed -> COMPLETED)
    INSERT INTO layer3_dim.fact_transactions (
        platform, external_id, transaction_date, created_on, year, month, week, hour,
        merchant_id, group_code, outlet_name, branch_name, store_name, status,
        is_success, is_cancelled,
        gross_amount, discounts, delivery_discount, net_sales,
        commission, ofd_fees, revenue,
        raw_record_id
    )
    SELECT 
        'ShopeeFood',
        stg.order_id,
        TO_DATE(SUBSTRING(stg.complete_time FROM 1 FOR 10), 'YYYY-MM-DD'),
        TO_TIMESTAMP(stg.complete_time, 'YYYY-MM-DD "at" HH24:MI'),
        EXTRACT(YEAR FROM TO_TIMESTAMP(stg.complete_time, 'YYYY-MM-DD "at" HH24:MI'))::INTEGER,
        stg.month,
        TO_CHAR(TO_TIMESTAMP(stg.complete_time, 'YYYY-MM-DD "at" HH24:MI'), 'YY-MM-') || 'W' || TO_CHAR(TO_TIMESTAMP(stg.complete_time, 'YYYY-MM-DD "at" HH24:MI'), 'W'),
        EXTRACT(HOUR FROM TO_TIMESTAMP(stg.complete_time, 'YYYY-MM-DD "at" HH24:MI'))::INTEGER,
        stg.store_id,
        COALESCE(m.group_code, 'UNKNOWN'),
        COALESCE(m.outlet_name, stg.store_name),
        COALESCE(m.nama_resto_final, m.nama_tarikan, 'UNKNOWN'),
        stg.store_name,
        stg.status,
        CASE WHEN LOWER(stg.status) IN ('completed', 'selesai', 'success', 'sukses') THEN 1 ELSE 0 END,
        CASE WHEN LOWER(stg.status) IN ('cancelled', 'batal', 'dibatalkan') THEN 1 ELSE 0 END,
        stg.food_original_price,
        (COALESCE(stg.item_discounts, 0) + COALESCE(stg.flash_sale_discount, 0) + COALESCE(stg.merchant_voucher_deals_subsidy, 0) + COALESCE(stg.food_voucher_subsidy, 0)) as total_discounts,
        0.00,
        stg.net_sales,
        stg.commission,
        stg.commission,
        stg.revenue,
        stg.id
    FROM layer2_clean.stg_shopee_orders stg
    LEFT JOIN layer3_dim.dim_merchant_mapping m ON stg.store_id = m.store_id
    WHERE stg.order_id IS NOT NULL 
      AND stg.order_id <> ''
    ON CONFLICT (platform, external_id) 
    DO UPDATE SET
        status = EXCLUDED.status,
        is_success = EXCLUDED.is_success,
        is_cancelled = EXCLUDED.is_cancelled,
        revenue = EXCLUDED.revenue,
        updated_at = CURRENT_TIMESTAMP;

    -- 3. PROSES DATA GOFOOD (Standardized Status: Sukses -> COMPLETED)
    INSERT INTO layer3_dim.fact_transactions (
        platform, external_id, transaction_date, created_on, year, month, week, hour,
        merchant_id, group_code, outlet_name, branch_name, store_name, status,
        is_success, is_cancelled,
        gross_amount, discounts, delivery_discount, net_sales,
        marketing_fee, commission, ofd_fees, revenue,
        raw_record_id
    )
    SELECT 
        'GoFood',
        stg.order_id,
        stg.date,
        stg.transaction_time,
        EXTRACT(YEAR FROM stg.transaction_time)::INTEGER,
        stg.month,
        TO_CHAR(stg.transaction_time, 'YY-MM-') || 'W' || TO_CHAR(stg.transaction_time, 'W'),
        EXTRACT(HOUR FROM stg.transaction_time)::INTEGER,
        stg.merchant_id,
        COALESCE(m.group_code, 'UNKNOWN'),
        COALESCE(m.outlet_name, stg.outlet_name),
        COALESCE(m.nama_resto_final, m.nama_tarikan, 'UNKNOWN'),
        stg.outlet_name,
        COALESCE(stg.order_status, 'Sukses'),
        1, -- GoFood completed orders
        0,
        stg.amount,
        0.00,
        0.00,
        stg.amount, -- Tab Order Lineage: net_sales = Amount
        (COALESCE(stg.gofood_discount, 0) + COALESCE(stg.voucher_commission, 0)), -- Tab Order Lineage: GoFood Discount + Voucher Commission
        stg.total_fee, -- Tab Order Lineage: Total Fee
        stg.total_platform_deduction, -- Tab Order Lineage: Amount - Net Amount
        stg.net_amount, -- Tab Order Lineage: revenue = Net Amount
        stg.id
    FROM layer2_clean.stg_go_orders stg
    LEFT JOIN layer3_dim.dim_merchant_mapping m ON stg.merchant_id = m.store_id
    WHERE stg.order_id IS NOT NULL 
      AND stg.order_id <> ''
    ON CONFLICT (platform, external_id) 
    DO UPDATE SET
        created_on = EXCLUDED.created_on,
        hour = EXCLUDED.hour,
        status = EXCLUDED.status,
        is_success = EXCLUDED.is_success,
        is_cancelled = EXCLUDED.is_cancelled,
        gross_amount = EXCLUDED.gross_amount,
        net_sales = EXCLUDED.net_sales,
        marketing_fee = EXCLUDED.marketing_fee,
        commission = EXCLUDED.commission,
        ofd_fees = EXCLUDED.ofd_fees,
        revenue = EXCLUDED.revenue,
        updated_at = CURRENT_TIMESTAMP;

    -- 4. HITUNG PERSENTASE GMV
    UPDATE layer3_dim.fact_transactions
    SET 
        gmv_vs_ofd_commission = CASE WHEN net_sales <> 0 THEN ROUND((commission / net_sales * 100), 2) || '%' ELSE '0%' END,
        gmv_vs_ofd_fees = CASE WHEN net_sales <> 0 THEN ROUND((ofd_fees / net_sales * 100), 2) || '%' ELSE '0%' END,
        gmv_vs_revenue = CASE WHEN net_sales <> 0 THEN ROUND((revenue / net_sales * 100), 2) || '%' ELSE '0%' END
    WHERE updated_at >= (CURRENT_TIMESTAMP - INTERVAL '1 hour');

    -- 5. AUTO REFRESH MATERIALIZED VIEW HARIAN
    IF EXISTS (SELECT 1 FROM pg_matviews WHERE schemaname = 'layer3_dim' AND matviewname = 'mv_payment_daily') THEN
        REFRESH MATERIALIZED VIEW CONCURRENTLY layer3_dim.mv_payment_daily;
    END IF;

    IF EXISTS (SELECT 1 FROM pg_matviews WHERE schemaname = 'layer3_dim' AND matviewname = 'mv_rekap_tagihan_monthly') THEN
        REFRESH MATERIALIZED VIEW CONCURRENTLY layer3_dim.mv_rekap_tagihan_monthly;
    END IF;

END;
$$ LANGUAGE plpgsql;
