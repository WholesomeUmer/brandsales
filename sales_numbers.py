"""Amazon Brand Sales Aggregator App

This Streamlit app lets you upload an Amazon business report CSV and returns
the total 'Ordered Product Sales' (consumer) + 'Ordered product sales – B2B'
grouped by brand, based on SKU prefixes.

How to run:
------------
$ pip install streamlit pandas
$ streamlit run sales_numbers.py
"""

import re
import io
import pandas as pd
import streamlit as st

# ----------------------- Configuration ----------------------- #
# Map SKU prefixes (regex) to brand names
BRAND_MAP = {
    r'^TH_': 'Theonia EU',
    r'^EU-PG-': 'PupGrade EU',
    r'^EU-PC-B-': 'Cosy House EU',
}

# ----------------------- Helper Functions -------------------- #
@st.cache_data(show_spinner=False)
def load_report(file: io.BytesIO) -> pd.DataFrame:
    """Read the CSV uploaded by the user."""
    return pd.read_csv(file)

def find_sales_columns(df: pd.DataFrame) -> tuple[str, str | None]:
    """Return column names for consumer and B2B sales."""
    total_col = None
    b2b_col = None
    for col in df.columns:
        name = col.strip().lower()
        if name == 'ordered product sales':
            total_col = col
        # match both 'ordered product sales – b2b' and 'ordered product sales - b2b'
        if re.match(r'ordered product sales\s*[–-]\s*b2b', name, re.I):
            b2b_col = col
    if total_col is None:
        raise ValueError("Couldn't find 'Ordered Product Sales' column.")
    return total_col, b2b_col

def parse_money(value: str | float | int) -> float:
    """Convert strings like '€1,234.56' or '$1,234.56' to float."""
    if pd.isna(value):
        return 0.0
    if not isinstance(value, str):
        return float(value)
    # remove everything except digits and dots
    clean = re.sub(r'[^0-9.]', '', value)
    return float(clean) if clean else 0.0

def detect_brand(sku: str) -> str:
    for pattern, brand in BRAND_MAP.items():
        if re.match(pattern, str(sku)):
            return brand
    return 'Other'

def aggregate_sales(df: pd.DataFrame) -> pd.DataFrame:
    total_col, b2b_col = find_sales_columns(df)

    df['__sales_consumer'] = df[total_col].apply(parse_money)
    if b2b_col:
        df['__sales_b2b'] = df[b2b_col].apply(parse_money)
    else:
        df['__sales_b2b'] = 0.0

    df['__sales_total'] = df['__sales_consumer'] + df['__sales_b2b']
    df['Brand'] = df['SKU'].apply(detect_brand)

    summary = (
        df.groupby('Brand')[['__sales_consumer', '__sales_b2b', '__sales_total']]
          .sum()
          .rename(columns={
              '__sales_consumer': 'Consumer Sales',
              '__sales_b2b': 'B2B Sales',
              '__sales_total': 'Total Sales'
          })
          .sort_values('Total Sales', ascending=False)
          .reset_index()
    )
    return summary

# ----------------------- Streamlit UI ------------------------ #
st.set_page_config(page_title="Amazon Brand Sales Aggregator", page_icon="📊")
st.title("📊 Amazon Brand Sales Aggregator")

uploaded_file = st.file_uploader(
    "Upload your Amazon Business Report CSV",
    type=["csv"],
    accept_multiple_files=False,
    help="Download a 'By ASIN' Business Report from Amazon Seller Central, then drop it here.",
)

if uploaded_file is not None:
    try:
        df = load_report(uploaded_file)
        summary_df = aggregate_sales(df)

        st.success("Report processed!")

        st.subheader("Sales by Brand")
        st.dataframe(summary_df, use_container_width=True)

        st.subheader("Key Metrics")
        for _, row in summary_df.iterrows():
            st.metric(label=row['Brand'], value=f"€{row['Total Sales']:,.2f}")

    except Exception as e:
        st.error(f"Error processing file: {e}")
else:
    st.info("⬆️ Upload a CSV to begin.")
