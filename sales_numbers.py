"""Amazon Brand Sales Aggregator App

This Streamlit app lets you upload an Amazon business report CSV and returns
the total 'Ordered Product Sales'
grouped by brand, based on SKU prefixes.

How to run:
------------
$ pip install streamlit pandas
$ streamlit run sales_numbers.py
"""

import io
import re
from typing import Iterable, Sequence

import pandas as pd
import streamlit as st

DEFAULT_BRAND_RULES = [
    {"pattern": r'^TH_', "brand": 'Theonia EU'},
    {"pattern": r'^EU-PG-', "brand": 'PupGrade EU'},
    {"pattern": r'^EU-PC-B-', "brand": 'Cosy House EU'},
]
DEFAULT_CURRENCY_SYMBOL = ""



CURRENCY_CODE_TO_SYMBOL = {
    'USD': '$',
    'US$': '$',
    'EUR': '€',
    'GBP': '£',
    'JPY': '¥',
    'JPY¥': '¥',
    'CAD': 'C$',
    'CAD$': 'C$',
    'CA$': 'C$',
    'AUD': 'A$',
    'AUD$': 'A$',
    'A$': 'A$',
    'NZD': 'NZ$',
    'NZ$': 'NZ$',
    'CHF': 'CHF',
    'MXN': 'MX$',
    'MX$': 'MX$',
}

CURRENCY_PREFIX_ALIASES = {
    '$': '$',
    '€': '€',
    '£': '£',
    '¥': '¥',
    '￥': '¥',
    'C$': 'C$',
    'A$': 'A$',
    'CA$': 'C$',
    'US$': '$',
    'AU$': 'A$',
    'NZ$': 'NZ$',
    'MX$': 'MX$',
    'CHF': 'CHF',
}


def normalize_currency_token(token: str) -> str | None:
    cleaned = (token or '').strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace(' ', '').strip()
    alias = CURRENCY_PREFIX_ALIASES.get(cleaned)
    if alias:
        return alias
    normalized = cleaned.upper().replace(' ', '')
    if normalized in CURRENCY_CODE_TO_SYMBOL:
        return CURRENCY_CODE_TO_SYMBOL[normalized]
    if normalized.endswith('$') and len(normalized) <= 4:
        return normalized
    return None


def find_currency_column(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if 'currency' in col.lower():
            return col
    return None


def infer_currency_symbol(df: pd.DataFrame, sales_column: str) -> tuple[str | None, str | None]:
    """Return inferred currency symbol and optional warning message."""
    currency_col = find_currency_column(df)
    if currency_col:
        series = df[currency_col].dropna()
        if not series.empty:
            token = str(series.iloc[0]).strip()
            symbol = normalize_currency_token(token)
            if symbol:
                return symbol, None

    raw_tokens: list[str] = []
    normalized_tokens: set[str] = set()

    for value in df[sales_column].dropna():
        text = str(value).strip()
        if not text:
            continue
        prefix_chars: list[str] = []
        for ch in text:
            if ch.isdigit() or ch in ',.-':
                break
            prefix_chars.append(ch)
        prefix = ''.join(prefix_chars).strip()
        if prefix:
            raw_tokens.append(prefix)
            normalized = normalize_currency_token(prefix)
            if normalized:
                normalized_tokens.add(normalized)
        suffix_chars: list[str] = []
        for ch in reversed(text):
            if ch.isdigit() or ch in ',.-':
                break
            suffix_chars.append(ch)
        suffix = ''.join(reversed(suffix_chars)).strip()
        if suffix and suffix != prefix:
            raw_tokens.append(suffix)
            normalized = normalize_currency_token(suffix)
            if normalized:
                normalized_tokens.add(normalized)
        if len(normalized_tokens) > 1:
            break

    if len(normalized_tokens) == 1:
        return normalized_tokens.pop(), None

    if raw_tokens:
        unique_raw = sorted({token for token in raw_tokens if token})
        if len(unique_raw) > 1:
            return None, f"Detected multiple currency markers {unique_raw}; totals are shown without a symbol."
        token = unique_raw[0]
        symbol = normalize_currency_token(token)
        if symbol:
            return symbol, None

    if df[sales_column].dropna().empty:
        return None, None
    return None, 'Could not determine a currency marker in the report; totals are shown without a symbol.'

# ----------------------- Helper Functions -------------------- #
@st.cache_data(show_spinner=False)
def load_report(file: io.BytesIO) -> pd.DataFrame:
    """Read the CSV uploaded by the user."""
    return pd.read_csv(file)


def find_sales_column(df: pd.DataFrame) -> str:
    """Return column name for consumer sales."""
    for col in df.columns:
        if col.strip().lower() == 'ordered product sales':
            return col
    raise ValueError("Couldn't find 'Ordered Product Sales' column.")


def find_sku_column(df: pd.DataFrame) -> str:
    """Return column name that holds SKU values."""
    for col in df.columns:
        if col.strip().lower() == 'sku':
            return col
    raise ValueError("Couldn't find 'SKU' column in the report.")


def parse_money(value: str | float | int) -> float:
    """Convert strings like '€1,234.56' or '€1.234,56' to float."""
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return 0.0

    negative = '-' in text or '(' in text
    text = text.replace('-', '').replace('(', '').replace(')', '')
    text = text.replace(' ', '').replace(' ', '')
    filtered = re.sub(r"[^0-9,.]", '', text)
    if not filtered:
        return 0.0

    decimal_sep = None
    if '.' in filtered and ',' in filtered:
        decimal_sep = '.' if filtered.rfind('.') > filtered.rfind(',') else ','
    elif ',' in filtered:
        decimal_sep = ',' if len(filtered.split(',')[-1]) <= 2 else None
    elif '.' in filtered:
        decimal_sep = '.' if len(filtered.split('.')[-1]) <= 2 else None

    working = filtered
    if decimal_sep != '.':
        working = working.replace('.', '')
    if decimal_sep != ',':
        working = working.replace(',', '')
    if decimal_sep == ',':
        working = working.replace(',', '.')

    try:
        amount = float(working)
    except ValueError:
        amount = 0.0
    return -amount if negative else amount


def normalize_brand_rules(records: Iterable[dict[str, str]]) -> list[tuple[str, str]]:
    """Drop empty entries and keep order for regex evaluation."""
    normalized: list[tuple[str, str]] = []
    for record in records:
        pattern = (record.get('pattern') or '').strip()
        brand = (record.get('brand') or '').strip()
        if pattern and brand:
            normalized.append((pattern, brand))
    return normalized


def detect_brand(sku: str, rules: Sequence[tuple[str, str]]) -> str:
    text = str(sku)
    for pattern, brand in rules:
        if re.match(pattern, text):
            return brand
    return 'Other'


def aggregate_sales(
    df: pd.DataFrame, *, brand_rules: Sequence[tuple[str, str]],
    sales_column: str | None = None, sku_column: str | None = None
) -> pd.DataFrame:
    """Aggregate consumer sales by detected brand."""
    sales_col = sales_column or find_sales_column(df)
    sku_col = sku_column or find_sku_column(df)

    sales_series = df[sales_col].apply(parse_money)
    brand_series = df[sku_col].apply(lambda sku: detect_brand(sku, brand_rules))

    summary = (
        pd.DataFrame({'Brand': brand_series, 'Ordered Product Sales': sales_series})
        .groupby('Brand', as_index=False)['Ordered Product Sales']
        .sum()
        .sort_values('Ordered Product Sales', ascending=False)
        .reset_index(drop=True)
    )
    return summary


def ensure_session_defaults() -> None:
    if 'brand_rules' not in st.session_state:
        st.session_state.brand_rules = [rule.copy() for rule in DEFAULT_BRAND_RULES]
    if 'currency_symbol' not in st.session_state:
        st.session_state.currency_symbol = DEFAULT_CURRENCY_SYMBOL




def edit_brand_rules_ui(rules: list[dict[str, str]]) -> list[dict[str, str]]:
    """Render the brand rules editor, falling back if data editor is unavailable."""
    st.caption('Edit SKU prefix patterns using Python regular expressions.')
    editor = getattr(st, 'data_editor', None) or getattr(st, 'experimental_data_editor', None)

    if editor:
        current_rules = rules or [{'pattern': '', 'brand': ''}]
        brand_editor_df = editor(
            pd.DataFrame(current_rules, columns=['pattern', 'brand']),
            num_rows='dynamic',
            use_container_width=True,
            hide_index=True,
            key='brand_editor',
            column_config={
                'pattern': 'SKU Pattern (regex)',
                'brand': 'Brand label',
            },
        )
        return brand_editor_df.fillna('').to_dict(orient='records')

    st.warning(
        'Streamlit `data_editor` is unavailable. Upgrade Streamlit to 1.19+ for the table UI. ' 
        'For now, edit rules using the text area below (format: pattern => brand).'
    )
    serialized = "\n".join(f"{item.get('pattern', '').strip()} => {item.get('brand', '').strip()}" for item in rules)
    raw = st.text_area('Brand rules', value=serialized, height=160)

    parsed: list[dict[str, str]] = []
    for line in raw.splitlines():
        if '=>' not in line:
            continue
        pattern, brand = (part.strip() for part in line.split('=>', 1))
        if pattern and brand:
            parsed.append({'pattern': pattern, 'brand': brand})
    return parsed or rules

DEFAULT_BRAND_RULE_SET = normalize_brand_rules(DEFAULT_BRAND_RULES)



SIDEBAR_MIN_WIDTH = 320
SIDEBAR_DEFAULT_WIDTH = 360
SIDEBAR_TOP_PADDING = "1.5rem"


def apply_sidebar_style() -> None:
    """Ensure the sidebar starts wide enough for labels but stays resizable."""
    st.markdown(
        f"""
        <style>
            [data-testid="stSidebar"] {{
                min-width: {SIDEBAR_MIN_WIDTH}px;
                width: {SIDEBAR_DEFAULT_WIDTH}px;
            }}
            [data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
                padding-top: {SIDEBAR_TOP_PADDING};
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )

# ----------------------- Streamlit UI ------------------------ #
ensure_session_defaults()
st.set_page_config(page_title="Amazon Brand Sales Aggregator", page_icon="📊")
st.title("📊 Amazon Brand Sales Aggregator")
apply_sidebar_style()

with st.sidebar:
    st.header('Preferences')
    st.session_state.brand_rules = edit_brand_rules_ui(st.session_state.brand_rules)


uploaded_file = st.file_uploader(
    'Upload your Amazon Business Report CSV',
    type=['csv'],
    accept_multiple_files=False,
    help="Download a 'By ASIN' Business Report from Amazon Seller Central, then drop it here.",
)


if uploaded_file is not None:
    try:
        df = load_report(uploaded_file)
        sales_col = find_sales_column(df)
        detected_symbol, detection_note = infer_currency_symbol(df, sales_col)
        st.session_state.currency_symbol = detected_symbol or DEFAULT_CURRENCY_SYMBOL
        if detection_note:
            st.warning(detection_note)

        active_rules = normalize_brand_rules(st.session_state.brand_rules)
        summary_df = aggregate_sales(
            df,
            brand_rules=active_rules or DEFAULT_BRAND_RULE_SET,
            sales_column=sales_col,
        )

        st.success('Report processed!')

        st.subheader('Sales by Brand')
        st.dataframe(summary_df, use_container_width=True)

        st.subheader('Key Metrics')
        symbol = st.session_state.currency_symbol or ''
        for _, row in summary_df.iterrows():
            st.metric(label=row['Brand'], value=f"{symbol}{row['Ordered Product Sales']:,.2f}")

    except Exception as e:
        st.error(f'Error processing file: {e}')
else:
    st.info('⬆️ Upload a CSV to begin.')

