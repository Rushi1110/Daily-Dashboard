import streamlit as st
import pandas as pd
import requests
import datetime
import pytz
import re

st.set_page_config(page_title="Jumbo Homes Lead Dashboard", layout="wide")

# --- LOGIN SYSTEM ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.title("🔒 Jumbo Homes Secure Login")
    st.markdown("Please log in to access the dashboard.")
    
    # Create a small login form
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        
        if submit:
            if username == "admin" and password == "Jumbo":
                st.session_state["logged_in"] = True
                st.rerun() # Refreshes the page to show the dashboard
            else:
                st.error("Incorrect username or password.")
    st.stop() # Stops the rest of the code from running if not logged in

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
    phone_str = str(phone).strip()
    digits = re.sub(r'\D', '', phone_str)
    return digits[-10:] if len(digits) >= 10 else digits

def parse_duration_to_seconds(duration_str):
    try:
        h, m, s = str(duration_str).split(' ')
        return (int(h[:-1]) * 3600) + (int(m[:-1]) * 60) + int(s[:-1])
    except:
        return 0

def fetch_glide_api():
    """Hits the API without caching, allowing the button to trigger it manually."""
    url = "https://api.glideapp.io/api/function/queryTables"
    headers = {"Authorization": st.secrets["GLIDE_API_TOKEN"]}
    payload = {
        "appID": "zKbZpeBo5f2rDnkRshIq",
        "queries": [{"tableName": "native-table-1L4wPB53vJM273qy7HAu", "utc": True}]
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

# --- SIDEBAR: DATE FILTERS ---
st.sidebar.header("Dashboard Filters")
ist = pytz.timezone('Asia/Kolkata')
today = datetime.datetime.now(ist).date()
yesterday = today - datetime.timedelta(days=1)

start_date = st.sidebar.date_input("Start Date", yesterday)
end_date = st.sidebar.date_input("End Date", yesterday)

if st.sidebar.button("Log Out"):
    st.session_state["logged_in"] = False
    st.session_state["glide_master_df"] = None
    st.rerun()


# --- MAIN APP FLOW ---
st.title("📊 Jumbo Homes Lead Dashboard")

# Initialize session state to hold the database so it doesn't disappear
if "glide_master_df" not in st.session_state:
    st.session_state["glide_master_df"] = None

# 1. MANUAL GLIDE FETCH BUTTON
if st.button("🔄 Fetch Latest Database from Glide"):
    with st.spinner("Connecting to Glide API..."):
        try:
            glide_raw = fetch_glide_api()
            if isinstance(glide_raw, list) and 'rows' in glide_raw[0]:
                df_temp = pd.DataFrame(glide_raw[0]['rows'])
                
                # Process the data immediately and save to session state
                df_temp['Created_IST'] = pd.to_datetime(df_temp['z6nvn']).dt.tz_convert('Asia/Kolkata').dt.date
                df_temp['Lead Owner'] = df_temp['qlWht'].map(OWNER_MAPPING).fillna(df_temp['qlWht'])
                df_temp['CleanPhone'] = df_temp['a92mh'].apply(clean_phone)
                
                # Save to memory so date filters don't trigger a new API call
                st.session_state["glide_master_df"] = df_temp
                st.success("Database synced successfully!")
            else:
                st.error("Received unexpected format from Glide API.")
        except Exception as e:
            st.error(f"Failed to connect to Glide API. Error: {e}")

# Only show the rest of the dashboard IF the database has been fetched
if st.session_state["glide_master_df"] is not None:
    
    # Apply date filters to the saved database
    df_glide = st.session_state["glide_master_df"]
    mask_glide = (df_glide['Created_IST'] >= start_date) & (df_glide['Created_IST'] <= end_date)
    df_glide_filtered = df_glide[mask_glide]
    df_leads_unique = df_glide_filtered.drop_duplicates(subset=['CleanPhone'])
    
    st.divider()
    
    # 2. CALLYZER UPLOAD
    callyzer_file = st.file_uploader("Upload your Callyzer Report (.csv) to generate metrics", type=['csv'])

    if callyzer_file:
        with st.spinner("Analyzing call data..."):
            df_callyzer = pd.read_csv(callyzer_file)
            df_callyzer['Call Date'] = pd.to_datetime(df_callyzer['Call Date'], format='%d %b %Y').dt.date
            
            mask_callyzer = (df_callyzer['Call Date'] >= start_date) & (df_callyzer['Call Date'] <= end_date)
            df_call_filtered = df_callyzer[mask_callyzer].copy()

            df_outgoing = df_call_filtered[df_call_filtered['Call Type'] == 'Outgoing'].copy()
            df_outgoing['CleanPhone'] = df_outgoing['To Number'].apply(clean_phone)
            df_outgoing['DurationSec'] = df_outgoing['Duration'].apply(parse_duration_to_seconds)

            # --- DASHBOARD METRICS ---
            st.subheader("Overview Metrics")
            m1, m2, m3 = st.columns(3)
            
            total_unique_leads = len(df_leads_unique)
            unique_numbers_called = df_outgoing['CleanPhone'].nunique()
            
            # Check against the master DB, not just the filtered date range DB
            glide_database_numbers = set(df_glide['CleanPhone'].dropna()) 
            numbers_called_in_db = df_outgoing[df_outgoing['CleanPhone'].isin(glide_database_numbers)]['CleanPhone'].nunique()
            
            db_attempt_pct = (numbers_called_in_db / unique_numbers_called * 100) if unique_numbers_called > 0 else 0

            m1.metric("Total Unique Leads Added", total_unique_leads)
            m2.metric("Total Outgoing Attempts", len(df_outgoing))
            m3.metric("Database Call Attempt %", f"{db_attempt_pct:.1f}%")

            st.divider()

            col_table1, col_table2 = st.columns(2)

            with col_table1:
                st.subheader("1. Lead Owner vs Lead Status")
                if not df_leads_unique.empty:
                    status_pivot = pd.crosstab(df_leads_unique['Lead Owner'], df_leads_unique['WlkAx'], margins=True, margins_name="Total")
                    st.dataframe(status_pivot, use_container_width=True)
                else:
                    st.info("No leads found for the selected date range.")

            with col_table2:
                st.subheader("2. Source Wise Leads")
                if not df_leads_unique.empty:
                    source_counts = df_leads_unique['fYTgZ'].value_counts().reset_index()
                    source_counts.columns = ['Source', 'Lead Count']
                    st.dataframe(source_counts, use_container_width=True)
                else:
                    st.info("No leads found for the selected date range.")

            st.divider()

            st.subheader("3. Calling Metrics (Connect Rate & Deep Conversations)")
            if not df_outgoing.empty:
                caller_stats = df_outgoing.groupby('Employee Name').agg(
                    Total_Attempts=('CleanPhone', 'count'), 
                    Connected_Calls=('DurationSec', lambda x: (x > 0).sum()),
                    Deep_Conversations=('DurationSec', lambda x: (x > 120).sum())
                ).reset_index()

                caller_stats['Connect Rate %'] = ((caller_stats['Connected_Calls'] / caller_stats['Total_Attempts']) * 100).round(1)
                caller_stats['Connect Rate %'] = caller_stats['Connect Rate %'].astype(str) + '%'
                
                st.dataframe(caller_stats, use_container_width=True)
            else:
                st.info("No outgoing calls found for the selected date range.")
else:
    st.info("👆 Click the fetch button above to load the latest database.")