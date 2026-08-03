import os
import re
import urllib.parse
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import sys

# Add parent directory to sys.path to allow importing config
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Load env variables
load_dotenv(os.path.join(current_dir, ".env"))
load_dotenv(os.path.join(parent_dir, ".env"), override=True)
load_dotenv()

from config import get_db_url
DB_URL = get_db_url()

def raw_string_format(val):
    if pd.isna(val) or val is None or val == "":
        return None
    return str(val).strip()

class DatabaseManager:
    def __init__(self):
        self.engine = create_engine(
            DB_URL,
            pool_size=10,
            max_overflow=20,
            pool_recycle=1800,
            pool_pre_ping=True
        )

    def ingest_shopee(self, df: pd.DataFrame):
        """Ingests Shopee raw data into layer1_raw.raw_shopee with delete-before-insert idempotency."""
        print("[DB] Ingesting Shopee data to layer1_raw.raw_shopee...")
        
        # Support both Indonesian and English headers
        header_mapping = {
            "Store ID": "Store ID",
            "Store name": "Store name",
            "Nama Toko": "Store name",
            "Transaction type": "Transaction type",
            "Tipe Transaksi": "Transaction type",
            "Transaction ID (Order ID)": "Transaction ID (Order ID)",
            "No. Pesanan": "Transaction ID (Order ID)",
            "Order ID": "Transaction ID (Order ID)",
            "Complete Time": "Complete Time",
            "Waktu Penyelesaian": "Complete Time",
            "Status": "Status",
            "Food original price": "Food original price",
            "Harga Makanan": "Food original price",
            "Item discounts": "Item discounts",
            "Diskon": "Item discounts",
            "Flash sale discount": "Flash sale discount",
            "Diskon Flash Sale": "Flash sale discount",
            "Surcharge fee": "Surcharge fee",
            "Biaya Tambahan": "Surcharge fee",
            "Merchant Voucher Deals Subsidy": "Merchant Voucher Deals Subsidy",
            "Subsidi Merchant untuk Voucher Deals": "Merchant Voucher Deals Subsidy",
            "Platform Flash Sale Subsidy": "Platform Flash Sale Subsidy",
            "Subsidi Platform untuk Flash Sale": "Platform Flash Sale Subsidy",
            "Food Voucher Subsidy": "Food Voucher Subsidy",
            "Subsidi Voucher Makanan": "Food Voucher Subsidy",
            "Food Direct Discount": "Food Direct Discount",
            "Diskon Langsung": "Food Direct Discount",
            "Transaction amount": "Transaction amount",
            "Nilai Transaksi": "Transaction amount",
            "Checkout Murah Price": "Checkout Murah Price",
            "Harga Checkout Murah": "Checkout Murah Price",
            "Notes": "Notes"
        }
        
        # Build mapping dynamically based on columns in the dataframe
        resolved_mapping = {}
        for df_col in df.columns:
            if df_col in header_mapping:
                resolved_mapping[df_col] = header_mapping[df_col]
                
        # Fill missing standard targets with defaults
        target_cols = [
            "Store ID", "Store name", "Transaction type", "Transaction ID (Order ID)", 
            "Complete Time", "Status", "Food original price", "Item discounts", 
            "Flash sale discount", "Surcharge fee", "Merchant Voucher Deals Subsidy", 
            "Platform Flash Sale Subsidy", "Food Voucher Subsidy", 
            "Food Direct Discount", "Transaction amount", "Checkout Murah Price", "Notes"
        ]
        
        # Rename and select available columns
        df_mapped = df[list(resolved_mapping.keys())].rename(columns=resolved_mapping).copy()
        df_mapped = df_mapped.loc[:, ~df_mapped.columns.duplicated()]
        
        # Add missing target columns as defaults
        for col in target_cols:
            if col not in df_mapped.columns:
                df_mapped[col] = None

        # Enforce exact column selection and order
        df_stg = df_mapped[target_cols].copy()
        
        # Convert all to raw strings (preserving the exact values, keeping NaN as None/NULL)
        for col in target_cols:
            df_stg[col] = df_stg[col].apply(raw_string_format)
        
        # QA-5: Delete-before-Insert Idempotency Logic
        order_ids = df_stg["Transaction ID (Order ID)"].dropna().unique().tolist()
        
        with self.engine.begin() as conn:
            if order_ids:
                print(f"[DB] Cleaning {len(order_ids)} existing Shopee raw records to ensure idempotency...")
                conn.execute(
                    text("DELETE FROM layer1_raw.raw_shopee WHERE \"Transaction ID (Order ID)\" = ANY(:ids)"),
                    {"ids": order_ids}
                )
            df_stg.to_sql('raw_shopee', conn, schema='layer1_raw', if_exists='append', index=False)
        
        print("[DB] Shopee raw ingestion completed.")

    def ingest_grab(self, df: pd.DataFrame):
        """Ingests Grab raw data into layer1_raw.raw_grab with delete-before-insert idempotency."""
        print("[DB] Ingesting Grab data to layer1_raw.raw_grab...")
        
        cols = [
            "Merchant Name", "Merchant ID", "Store Name", "Store ID", 
            "Updated On", "Created On", "Type", "Category", "Subcategory", 
            "Status", "Transaction ID", "Linked Transaction ID", 
            "Partner transaction ID 1", "Partner transaction ID 2", 
            "Long Order ID", "Short Order ID", "Booking ID", "Order Channel", 
            "Order Type", "Payment Method", "Receiving account / Source of fund", 
            "Terminal ID", "Channel", "Offer Type", "Grab Fee (%)", 
            "Points Multiplier", "Points Issued", "Settlement ID", 
            "Transfer Date", "Amount", "Tax on Order Value", 
            "Restaurant Packaging Charge", "Non-Member Fee", 
            "Restaurant Service Charge", "Offer", "Discount (Merchant-Funded)", 
            "Delivery Fee Discount (Merchant-Funded)", 
            "Delivery Charge (Grab Online Store)", 
            "Delivery Charge (Merchant Delivery)", 
            "GrabExpress Delivery Service Fee", "Net Sales", "Net MDR", 
            "Tax on MDR", "Grab Fee", "Marketing success fee", 
            "Delivery Commission", "Channel Commission", "Order commission", 
            "Step-up commission", "GrabKitchen Commission", 
            "GrabKitchen Other Commission", "Withholding Tax", "Total", 
            "Tax on MDR (%)", "Delivery Commission (%)", "Channel Commission (%)", 
            "Order Commission (%)", 
            "Tax on GrabFood/GrabMart commission, adjustments, ads", 
            "Tax on Total GrabKitchen Commission", "Cancellation Reason", 
            "Cancelled by", "Reason for Refund", "Description", 
            "Incident group", "Incident alias", "Customer refund Item", 
            "Appeal link", "Appeal status"
        ]
        
        # Resolve column naming flexibility
        resolved_mapping = {}
        for df_col in df.columns:
            # Match columns ignoring case and spaces
            cleaned_df_col = re.sub(r'[^a-zA-Z0-9]', '', df_col).lower()
            for target_col in cols:
                cleaned_target = re.sub(r'[^a-zA-Z0-9]', '', target_col).lower()
                if cleaned_df_col == cleaned_target:
                    resolved_mapping[df_col] = target_col
                    break
        
        df_mapped = df[list(resolved_mapping.keys())].rename(columns=resolved_mapping).copy()
        df_mapped = df_mapped.loc[:, ~df_mapped.columns.duplicated()]
        
        # Ensure all columns exist in DF
        for col in cols:
            if col not in df_mapped.columns:
                df_mapped[col] = None
        
        # Select and copy
        df_stg = df_mapped[cols].copy()
        
        # Convert all to raw strings
        for col in cols:
            df_stg[col] = df_stg[col].apply(raw_string_format)

        # QA-5: Delete-before-Insert Idempotency Logic
        order_ids = df_stg["Long Order ID"].dropna().unique().tolist()

        with self.engine.begin() as conn:
            if order_ids:
                print(f"[DB] Cleaning {len(order_ids)} existing Grab raw records to ensure idempotency...")
                conn.execute(
                    text("DELETE FROM layer1_raw.raw_grab WHERE \"Long Order ID\" = ANY(:ids)"),
                    {"ids": order_ids}
                )
            df_stg.to_sql('raw_grab', conn, schema='layer1_raw', if_exists='append', index=False)
            
        print("[DB] Grab raw ingestion completed.")

    def ingest_gofood(self, df: pd.DataFrame):
        """Ingests GoFood raw data into layer1_raw.raw_go with delete-before-insert idempotency."""
        print("[DB] Ingesting GoFood data to layer1_raw.raw_go...")
        
        header_mapping = {
            "Order Status": "Order Status",
            "Outlet Name": "Outlet Name",
            "Store Name": "Outlet Name",
            "Nama Outlet": "Outlet Name",
            "Merchant ID": "Merchant ID",
            "Store ID": "Merchant ID",
            "Feature": "Feature",
            "Layanan": "Feature",
            "Order ID": "Order ID",
            "No. Pesanan": "Order ID",
            "Transaction ID": "Transaction ID",
            "ID Transaksi": "Transaction ID",
            "Amount": "Amount",
            "Penjualan Kotor": "Amount",
            "Net Amount": "Net Amount",
            "Penjualan Bersih": "Net Amount",
            "Transaction Time": "Transaction Time",
            "Waktu Transaksi": "Transaction Time",
            "Tanggal": "Transaction Time",
            "Payment Type": "Payment Type",
            "Tipe Pembayaran": "Payment Type",
            "GoPay Promo": "GoPay Promo",
            "Promo Type": "Promo Type",
            "Promo Name": "Promo Name",
            "Merchant Promo Contribution": "Merchant Promo Contribution",
            "Voucher Description": "Voucher Description",
            "GoFood Discount": "GoFood Discount",
            "Voucher Commission": "Voucher Commission",
            "Total Fee": "Total Fee",
            "Biaya Komisi": "Total Fee",
            "Value Added Tax": "Value Added Tax",
            "Restaurant Tax": "Restaurant Tax",
            "Service": "Service",
            "Withholding Tax": "Withholding Tax",
        }
        
        resolved_mapping = {}
        for df_col in df.columns:
            if df_col in header_mapping:
                resolved_mapping[df_col] = header_mapping[df_col]
                
        target_cols = [
            "Order Status", "Outlet Name", "Merchant ID", "Feature", "Order ID",
            "Transaction ID", "Amount", "Net Amount", "Transaction Time", "Payment Type",
            "GoPay Promo", "Promo Type", "Promo Name", "Merchant Promo Contribution",
            "Voucher Description", "GoFood Discount", "Voucher Commission", "Total Fee",
            "Value Added Tax", "Restaurant Tax", "Service", "Withholding Tax"
        ]
        
        df_mapped = df[list(resolved_mapping.keys())].rename(columns=resolved_mapping).copy()
        df_mapped = df_mapped.loc[:, ~df_mapped.columns.duplicated()]
        
        for col in target_cols:
            if col not in df_mapped.columns:
                df_mapped[col] = None
                
        df_stg = df_mapped[target_cols].copy()
        
        # Convert all to raw strings
        for col in target_cols:
            df_stg[col] = df_stg[col].apply(raw_string_format)

        # QA-5: Delete-before-Insert Idempotency Logic
        keys = df_stg[["Tanggal", "Store ID"]].dropna().drop_duplicates().values.tolist()

        with self.engine.begin() as conn:
            if keys:
                print(f"[DB] Cleaning existing GoFood raw records matching {len(keys)} period-merchant combinations...")
                for tanggal, store_id in keys:
                    conn.execute(
                        text("DELETE FROM layer1_raw.raw_go WHERE \"Tanggal\" = :tanggal AND \"Store ID\" = :store_id"),
                        {"tanggal": tanggal, "store_id": store_id}
                    )
            df_stg.to_sql('raw_go', conn, schema='layer1_raw', if_exists='append', index=False)
            
        print("[DB] GoFood raw ingestion completed.")

if __name__ == "__main__":
    db = DatabaseManager()
    print("[DB] DatabaseManager initialized successfully.")
