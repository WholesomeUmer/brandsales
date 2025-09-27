# Amazon Brand Sales Aggregator App

This Streamlit app lets you upload an Amazon business report CSV and returns
the total 'Ordered Product Sales'
grouped by brand, based on SKU prefixes.

How to run:
------------
- $ pip install streamlit pandas
- $ streamlit run sales_numbers.py

Features
--------
- Totals the 'Ordered Product Sales' column by detected brand.
- Edit brand-to-regex mappings in the sidebar; each browser session keeps its own list via `st.session_state`.
- Sidebar opens wide enough for readable inputs but stays resizable.
- Detects the report currency automatically and applies it to the dashboard.

