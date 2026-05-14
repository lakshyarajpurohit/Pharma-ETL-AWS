import streamlit as st
import pandas as pd
import os

st.set_page_config(
    page_title="Pharma Portfolio Monitor",
    layout="wide",
    page_icon="💊"
)

# ── LOAD CSV FILES WITH ERROR HANDLING ───────────────────
@st.cache_data
def load_csv(filename):
    try:
        df = pd.read_csv(filename)
        # Normalize column names to lowercase and strip spaces
        df.columns = df.columns.str.lower().str.strip()
        return df
    except FileNotFoundError:
        st.error(f"File not found: {filename} — check your query_data folder")
        return pd.DataFrame()

# Load datasets
yoy       = load_csv("query_data/YOY_growth.csv")
pareto    = load_csv("query_data/Revenue.csv")
declining = load_csv("query_data/Declining_months.csv")
weekend   = load_csv("query_data/Weekend_pattern.csv")
quarterly = load_csv("query_data/Quarterly_rank.csv")
underperf = load_csv("query_data/Underperformance.csv")
quality   = load_csv("query_data/Quality_report.csv")

# ── SIDEBAR FILTER ────────────────────────────────────────
st.sidebar.header("Filters")
if not yoy.empty:
    available_years = sorted(yoy['year'].unique().tolist())
    selected_years = st.sidebar.multiselect(
        "Select Year(s)",
        options=available_years,
        default=available_years
    )
else:
    selected_years = []

# ── FILTERING LOGIC ───────────────────────────────────────
def apply_year_filter(df, years):
    if not df.empty and 'year' in df.columns:
        return df[df['year'].isin(years)]
    return df

# Apply filters to all dataframes
yoy = apply_year_filter(yoy, selected_years)
pareto = apply_year_filter(pareto, selected_years)
declining = apply_year_filter(declining, selected_years)
weekend = apply_year_filter(weekend, selected_years)
quarterly = apply_year_filter(quarterly, selected_years)
underperf = apply_year_filter(underperf, selected_years)

# ── HEADER ────────────────────────────────────────────────
st.title("💊 Pharma Portfolio Performance Monitor")
st.caption("Pipeline: AWS S3 → Lambda → Glue ETL → Athena → Dashboard | Data: 2014–2019")
st.divider()

# ── KPI ROW ───────────────────────────────────────────────
if not yoy.empty and not pareto.empty and not underperf.empty:
    # KPI Calculations (Filter-aware)
    best_year_row = yoy.loc[yoy['annual_sales'].idxmax()]
    best_year = best_year_row['year']
    best_growth = yoy['yoy_growth_pct'].dropna().max() if 'yoy_growth_pct' in yoy.columns else 0
    
    # Aggregated top therapy for KPI
    pareto_kpi = pareto.groupby("therapy")["total_revenue"].sum().reset_index()
    top_therapy = pareto_kpi.loc[pareto_kpi['total_revenue'].idxmax(), 'therapy']
    
    worst_row = underperf.sort_values('pct_underperforming', ascending=False).iloc[0]
    worst_q = f"{int(worst_row['year'])} {worst_row['quarter']}"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📅 Peak Revenue Year", str(int(best_year)), delta="Declined after 2016", delta_color="inverse")
    c2.metric("📈 Best YoY Growth", f"{best_growth}%", delta="2018 recovery after 2017 crisis")
    c3.metric("💊 Top Therapy Area", top_therapy, delta="55.8% of total revenue")
    c4.metric("⚠️ Highest Risk Quarter", worst_q, delta=f"{worst_row['pct_underperforming']}% risk", delta_color="inverse")

    st.divider()
    st.info(
        "📋 **Executive Summary:** Analgesics dominate 55.8% of portfolio revenue — "
        "creating concentration risk if this category declines. 2017 and 2019 were crisis years "
        "with -23.1% and -25.3% YoY decline respectively. Q4 is consistently the strongest quarter "
        "across all 6 years. October 2019 saw the worst single-month collapse at -70.5%."
    )
    st.divider()

# ── ROW 1: Revenue Charts ─────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("📈 Annual Revenue Trend (2014–2019)")
    if not yoy.empty:
        st.bar_chart(yoy.set_index("year")["annual_sales"])

with col2:
    st.subheader("🏆 Revenue Share by Therapy Area")
    if not pareto.empty:
        pareto_display = pareto.groupby("therapy")["total_revenue"].sum().reset_index()
        st.bar_chart(pareto_display.set_index("therapy")["total_revenue"])

st.divider()

# ── ROW 2: Performance Charts ─────────────────────────────
col3, col4 = st.columns(2)

with col3:
    st.subheader("📊 Quarterly Sales by Year")
    if not quarterly.empty:
        try:
            pivot = quarterly.pivot_table(index="quarter", columns="year", values="quarterly_sales", aggfunc="sum")
            st.line_chart(pivot)
        except Exception as e:
            st.error(f"Pivot error: {e}")

with col4:
    st.subheader("⚠️ Worst Quarters by Underperformance")
    if not underperf.empty:
        worst_quarters = underperf.sort_values("pct_underperforming", ascending=False).head(5).copy()
        worst_quarters["period"] = worst_quarters["year"].astype(str) + " " + worst_quarters["quarter"]
        worst_quarters["pct_underperforming_fmt"] = worst_quarters["pct_underperforming"].apply(lambda x: f"⚠️ {x}%")
        
        display_underperf = worst_quarters[["period", "bad_days", "total_days", "pct_underperforming_fmt"]]
        display_underperf.columns = ["Quarter", "Bad Days", "Total Days", "Underperforming %"]
        st.dataframe(display_underperf, use_container_width=True, hide_index=True)
        st.caption("💡 Q4 never appears in top 10 worst — consistently the strongest quarter across all 6 years.")

st.divider()

# ── ROW 3: Pattern Analysis ───────────────────────────────
col5, col6 = st.columns(2)

with col5:
    st.subheader("🗓️ Weekday vs Weekend Sales Pattern")
    if not weekend.empty:
        # AGGREGATE & ROUND to 2 decimal places
        weekend_display = weekend.groupby("day_type")[["avg_daily_sales", "peak_sales"]].mean().reset_index()
        weekend_display = weekend_display.round(2)
        
        st.bar_chart(weekend_display.set_index("day_type")["avg_daily_sales"])
        
        # Rounded Caption
        avg_wd = weekend_display[weekend_display['day_type']=='Weekday']['avg_daily_sales'].values[0]
        avg_we = weekend_display[weekend_display['day_type']=='Weekend']['avg_daily_sales'].values[0]
        st.caption(f"Peak sales in range: {weekend_display['peak_sales'].max():.2f} | "
                   f"Avg weekday: {avg_wd:.2f} | Avg weekend: {avg_we:.2f}")

with col6:
    if not declining.empty:
        declining_only = declining[declining["trend"].str.lower() == "declining"]
        if not declining_only.empty:
            worst = declining_only.sort_values("mom_growth_pct").head(10).copy()
            month_map = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                         7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
            
            worst_display = pd.DataFrame()
            worst_display["Year"] = worst["year"].astype(str)
            worst_display["Month"] = worst["month"].map(month_map)
            worst_display["Monthly Sales"] = worst["monthly_sales"].apply(lambda x: f"₹{x:,.2f}")
            worst_display["MoM Change"] = worst["mom_growth_pct"].apply(lambda x: f"📉 {x}%")
            
            st.subheader("📉 Top 10 Worst Declining Months")
            st.dataframe(worst_display, use_container_width=True, hide_index=True, height=320)
            st.caption("⚠️ February and November recur in worst months — seasonal pattern.")

st.divider()

# ── YoY GROWTH TABLE (USING YOUR LOGIC) ───────────────────
st.subheader("📋 Year over Year Growth Detail")
if not yoy.empty:
    display_yoy = yoy.copy()
    if 'yoy_growth_pct' in display_yoy.columns:
        display_yoy['yoy_growth_pct'] = display_yoy['yoy_growth_pct'].apply(
            lambda x: f"📈 +{x}%" if x > 0 else (f"📉 {x}%" if pd.notna(x) else "—")
        )
    
    # We rename only existing columns to prevent errors
    # Note: Ensure your CSV has 4 columns for this exact labeling
    try:
        display_yoy.columns = ["Year", "Annual Sales", "Prev Year Sales", "YoY Growth %"]
    except ValueError:
        # Fallback if CSV column count is different
        pass
        
    display_yoy["Year"] = display_yoy["Year"].astype(str)
    st.dataframe(display_yoy, use_container_width=True, hide_index=True)

st.divider()

# ── DATA QUALITY REPORT (USING YOUR LOGIC) ────────────────
st.subheader("🔍 Data Quality Report")

if not quality.empty:
    # Normalize column names
    quality.columns = quality.columns.str.lower().str.strip()
    
    # Find status column dynamically
    status_col = None
    for col in quality.columns:
        if "status" in col:
            status_col = col
            break

    def color_status(val):
        if val == "PASS":
            return "background-color: #d4edda; color: #155724; font-weight: bold"
        elif val == "FAIL":
            return "background-color: #f8d7da; color: #721c24; font-weight: bold"
        elif val == "WARN":
            return "background-color: #fff3cd; color: #856404; font-weight: bold"
        elif val == "INFO":
            return "background-color: #d1ecf1; color: #0c5460"
        return ""

    if status_col:
        st.dataframe(
            quality.style.map(color_status, subset=[status_col]),
            use_container_width=True
        )
        pass_count = (quality[status_col] == "PASS").sum()
        fail_count = (quality[status_col] == "FAIL").sum()
        warn_count = (quality[status_col] == "WARN").sum()

        q1, q2, q3 = st.columns(3)
        q1.metric("✅ Checks Passed", int(pass_count))
        q2.metric("❌ Checks Failed", int(fail_count))
        q3.metric("⚠️ Warnings",      int(warn_count))
    else:
        st.dataframe(quality, use_container_width=True)
        st.caption(f"Columns found: {quality.columns.tolist()}")
else:
    st.info("quality_report.csv not found. Run the Glue job with quality checks first.")

st.divider()
st.caption("Built on AWS | S3 + Lambda + Glue ETL + Athena")