import streamlit as st
import pandas as pd
import json
import datetime
import pytz
import re

st.set_page_config(page_title="Jumbo Homes Lead Dashboard", layout="wide")

# --- MAPPINGS ---
OWNER_MAPPING = {
    'gchethan11@gmail.com': 'Chethan',
    'harishsofficial0@gmail.com': 'Harish',
    'imrankhandabang350@gmail.com': 'Imran',
    'megharajpattepur65@gmail.com': 'Megharaj',
    'shariffroushan5@gmail.com': 'Roushan',
    'stanhemanth0410@gmail.com': 'Hema',
    'pmer302@gmail.com': 'Prashant',
    'suhasphoto106@gmail.com': 'Suhas'
}

# --- HELPER FUNCTIONS ---
def clean_phone(phone):
    """Extracts the last 10 digits of a phone number to ensure clean matching."""
    phone_str = str(phone).strip()
    digits = re.sub(r'\D', '', phone_str)
    return digits[-10:] if len(digits) >= 10 else digits

def parse_duration_to_seconds(duration_str):
    """Converts Callyzer '0h 1m 31s' to integer seconds."""
    try:
        h, m, s = str(duration_str).split(' ')
        return (int(h[:-1]) * 3600) + (int(m[:-1]) * 60) + int(s[:-1])
    except:
        return 0

# --- SIDEBAR: DATE FILTERS ---
st.sidebar.header("Dashboard Filters")
ist = pytz.timezone('Asia/Kolkata')
today = datetime.datetime.now(ist).date()
yesterday = today - datetime.timedelta(days=1)

start_date = st.sidebar.date_input("Start Date", yesterday)
end_date = st.sidebar.date_input("End Date", yesterday)

# --- FILE UPLOADS ---
st.title("📊 Jumbo Homes Lead Dashboard")
st.markdown("Upload your latest **Glide JSON** and **Callyzer CSV** dumps below to generate the dashboard.")

col1, col2 = st.columns(2)
with col1:
    glide_file = st.file_uploader("Upload Glide Data (data.json)", type=['json'])
with col2:
    callyzer_file = st.file_uploader("Upload Callyzer Report (.csv)", type=['csv'])

if glide_file and callyzer_file:
    with st.spinner("Processing data..."):
        # 1. LOAD & PROCESS GLIDE DATA
        glide_raw = json.load(glide_file)
        # Extract rows from Glide JSON structure
        if isinstance(glide_raw, list) and 'rows' in glide_raw[0]:
            df_glide = pd.DataFrame(glide_raw[0]['rows'])
        else:
            st.error("Invalid Glide JSON format.")
            st.stop()

        # Convert created dates to IST
        df_glide['Created_IST'] = pd.to_datetime(df_glide['z6nvn']).dt.tz_convert('Asia/Kolkata').dt.date
        
        # Apply Lead Owner Mapping
        df_glide['Lead Owner'] = df_glide['qlWht'].map(OWNER_MAPPING).fillna(df_glide['qlWht'])
        
        # Clean Glide Phone Numbers
        df_glide['CleanPhone'] = df_glide['a92mh'].apply(clean_phone)

        # Filter Glide Data by Date Range
        mask_glide = (df_glide['Created_IST'] >= start_date) & (df_glide['Created_IST'] <= end_date)
        df_glide_filtered = df_glide[mask_glide]

        # DEDUPLICATE LEADS (for Status and Source analysis)
        df_leads_unique = df_glide_filtered.drop_duplicates(subset=['CleanPhone'])


        # 2. LOAD & PROCESS CALLYZER DATA
        df_callyzer = pd.read_csv(callyzer_file)
        
        # Parse Call Dates
        df_callyzer['Call Date'] = pd.to_datetime(df_callyzer['Call Date'], format='%d %b %Y').dt.date
        
        # Filter Callyzer Data by Date Range
        mask_callyzer = (df_callyzer['Call Date'] >= start_date) & (df_callyzer['Call Date'] <= end_date)
        df_call_filtered = df_callyzer[mask_callyzer].copy()

        # Isolate Outgoing Calls
        df_outgoing = df_call_filtered[df_call_filtered['Call Type'] == 'Outgoing'].copy()
        
        # Clean Callyzer Phone Numbers (To Number)
        df_outgoing['CleanPhone'] = df_outgoing['To Number'].apply(clean_phone)
        
        # Calculate duration in seconds
        df_outgoing['DurationSec'] = df_outgoing['Duration'].apply(parse_duration_to_seconds)

        # --- DASHBOARD METRICS & VISUALS ---

        st.divider()
        
        # OVERVIEW METRICS
        st.subheader("Overview Metrics")
        m1, m2, m3 = st.columns(3)
        
        total_unique_leads = len(df_leads_unique)
        
        # Database Attempt %: Unique called numbers found in Glide / Total Unique called numbers
        unique_numbers_called = df_outgoing['CleanPhone'].nunique()
        glide_database_numbers = set(df_glide['CleanPhone'].dropna()) # Check against whole DB, not just filtered dates
        numbers_called_in_db = df_outgoing[df_outgoing['CleanPhone'].isin(glide_database_numbers)]['CleanPhone'].nunique()
        
        db_attempt_pct = (numbers_called_in_db / unique_numbers_called * 100) if unique_numbers_called > 0 else 0

        m1.metric("Total Unique Leads Added", total_unique_leads)
        m2.metric("Total Outgoing Attempts", len(df_outgoing))
        m3.metric("Database Call Attempt %", f"{db_attempt_pct:.1f}%", help="Percentage of unique numbers called that exist in the Glide database.")

        st.divider()

        # SECTION 1 & 2: LEAD ANALYSIS (Deduplicated Data)
        col_table1, col_table2 = st.columns(2)

        with col_table1:
            st.subheader("1. Lead Owner vs Lead Status")
            # Pivot Table: Rows = Owner, Cols = Status (WlkAx)
            if not df_leads_unique.empty:
                status_pivot = pd.crosstab(df_leads_unique['Lead Owner'], df_leads_unique['WlkAx'], margins=True, margins_name="Total")
                st.dataframe(status_pivot, use_container_width=True)
            else:
                st.info("No leads found for the selected date range.")

        with col_table2:
            st.subheader("2. Source Wise Leads")
            # Group by Source (fYTgZ)
            if not df_leads_unique.empty:
                source_counts = df_leads_unique['fYTgZ'].value_counts().reset_index()
                source_counts.columns = ['Source', 'Lead Count']
                st.dataframe(source_counts, use_container_width=True)
            else:
                st.info("No leads found for the selected date range.")

        st.divider()

        # SECTION 3: CALLER METRICS (Includes Duplicates for Connect Rate)
        st.subheader("3. Calling Metrics (Connect Rate & Deep Conversations)")
        
        if not df_outgoing.empty:
            # Group by Employee Name
            caller_stats = df_outgoing.groupby('Employee Name').agg(
                Total_Attempts=('CleanPhone', 'count'), # Counts all attempts, including duplicates
                Connected_Calls=('DurationSec', lambda x: (x > 0).sum()),
                Deep_Conversations=('DurationSec', lambda x: (x > 120).sum())
            ).reset_index()

            # Calculate Connect %
            caller_stats['Connect Rate %'] = ((caller_stats['Connected_Calls'] / caller_stats['Total_Attempts']) * 100).round(1)
            
            # Format columns for display
            caller_stats['Connect Rate %'] = caller_stats['Connect Rate %'].astype(str) + '%'
            
            st.dataframe(caller_stats, use_container_width=True)
        else:
            st.info("No outgoing calls found for the selected date range.")

else:
    st.info("👆 Please upload your data files to view the dashboard.")