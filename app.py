import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import json
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Page configuration
st.set_page_config(
    page_title="UK Air Quality PM10 Analysis - Site RI2",
    page_icon="🌬️",
    layout="wide"
)

st.title("🌬️ UK Air Quality Time Series Analysis")
st.subheader("Air Pollutant Data (2000-2024)")

# API endpoint base URLs
ANNUAL_API_URL = "https://api.erg.ic.ac.uk/AirQuality/Annual/MonitoringReport/SiteCode={}/Year={}/json"
HOURLY_API_URL = "https://api.erg.ic.ac.uk/AirQuality/Data/Site/SiteCode={}/StartDate={}/EndDate={}/Json"

def fetch_annual_data(site_code, year):
    """
    Fetch annual air quality data for a specific site and year from the UK Air Quality API
    
    Args:
        site_code (str): The site code to fetch data for
        year (int): The year to fetch data for
        
    Returns:
        dict: JSON response from the API or None if failed
    """
    try:
        url = ANNUAL_API_URL.format(site_code, year)
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to fetch data for site {site_code}, year {year}: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        st.error(f"Failed to parse JSON for site {site_code}, year {year}: {str(e)}")
        return None

def fetch_hourly_data(site_code, start_date, end_date):
    """
    Fetch hourly air quality data for a specific site and date range from the UK Air Quality API
    
    Args:
        site_code (str): The site code to fetch data for
        start_date (str): Start date in YYYY-MM-DD format
        end_date (str): End date in YYYY-MM-DD format
        
    Returns:
        dict: JSON response from the API or None if failed
    """
    try:
        url = HOURLY_API_URL.format(site_code, start_date, end_date)
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to fetch data for site {site_code}, {start_date} to {end_date}: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        st.error(f"Failed to parse JSON for site {site_code}, {start_date} to {end_date}: {str(e)}")
        return None

def extract_pollutant_data(data, pollutant_type, averaging_type="annual"):
    """
    Extract pollutant data from the nested JSON structure
    
    Args:
        data (dict): JSON response from the API
        pollutant_type (str): Type of pollutant (PM10, PM25, NO2)
        averaging_type (str): "annual" or "monthly"
        
    Returns:
        dict: Data with annual value or monthly values, or None if not found/invalid
    """
    # Check if data is None or empty
    if not data:
        return None
        
    try:
        # Navigate to the ReportItem array
        site_report = data.get("SiteReport", {})
        if not site_report:
            return None
            
        report_items = site_report.get("ReportItem", [])
        if not report_items:
            return None
        
        # Define mapping for different pollutant types and their report items
        pollutant_mapping = {
            "PM10": {"species_code": "PM10", "report_item": "7"},  # Mean: (AQS Objective < 40ug/m3)
            "PM25": {"species_code": "PM25", "report_item": "7"},  # Mean: (AQS Objective < 25ug/m3)
            "NO2": {"species_code": "NO2", "report_item": "7"}     # Mean: (AQS Objective < 40ug/m3)
        }
        
        if pollutant_type not in pollutant_mapping:
            return None
            
        target_species = pollutant_mapping[pollutant_type]["species_code"]
        target_report_item = pollutant_mapping[pollutant_type]["report_item"]
        
        # Search for pollutant data - look for the specific ReportItem with concentration data
        for item in report_items:
            if (item.get("@SpeciesCode") == target_species and 
                item.get("@ReportItem") == target_report_item and
                item.get("@ReportItemName", "").startswith("Mean:")):  # Only get the concentration data
                
                if averaging_type == "annual":
                    annual_value = item.get("@Annual")
                    if annual_value and annual_value != "-999":
                        try:
                            return {"annual": float(annual_value)}
                        except ValueError:
                            continue
                            
                elif averaging_type == "monthly":
                    monthly_data = {}
                    months = ["Month1", "Month2", "Month3", "Month4", "Month5", "Month6",
                             "Month7", "Month8", "Month9", "Month10", "Month11", "Month12"]
                    
                    has_valid_data = False
                    for i, month in enumerate(months, 1):
                        month_value = item.get(f"@{month}")
                        if month_value and month_value != "-999":
                            try:
                                monthly_data[i] = float(month_value)
                                has_valid_data = True
                            except ValueError:
                                continue
                    
                    if has_valid_data:
                        return {"monthly": monthly_data}
        
        return None
        
    except Exception:
        # Return None silently for any parsing errors
        return None

def extract_hourly_data(data, pollutant_type, averaging_type="hourly"):
    """
    Extract hourly data from the hourly API response and optionally aggregate to daily
    
    Args:
        data (dict): JSON response from the hourly API
        pollutant_type (str): Type of pollutant (PM10, PM25, NO2)
        averaging_type (str): "hourly" or "daily"
        
    Returns:
        list: List of data points with timestamps and values
    """
    if not data:
        return []
        
    try:
        air_quality_data = data.get("AirQualityData", {})
        if not air_quality_data:
            return []
            
        data_items = air_quality_data.get("Data", [])
        if not data_items:
            return []
        
        # Filter for the specific pollutant
        pollutant_data = []
        for item in data_items:
            if item.get("@SpeciesCode") == pollutant_type:
                timestamp = item.get("@MeasurementDateGMT")
                value = item.get("@Value")
                
                if timestamp and value and value != "-999":
                    try:
                        pollutant_data.append({
                            "timestamp": pd.to_datetime(timestamp),
                            "value": float(value)
                        })
                    except (ValueError, TypeError):
                        continue
        
        if not pollutant_data:
            return []
        
        # Convert to DataFrame for easier processing
        df = pd.DataFrame(pollutant_data)
        df = df.sort_values("timestamp")
        
        if averaging_type == "hourly":
            return df.to_dict('records')
            
        elif averaging_type == "daily":
            # Group by date and calculate daily averages
            df['date'] = df['timestamp'].dt.date
            daily_data = df.groupby('date')['value'].mean().reset_index()
            daily_data['timestamp'] = pd.to_datetime(daily_data['date'])
            
            return [{"timestamp": row['timestamp'], "value": row['value']} 
                   for _, row in daily_data.iterrows()]
        
        return []
        
    except Exception:
        return []

def main():
    """Main application logic"""
    
    # Create columns for layout
    col1, col2 = st.columns([2, 1])
    
    with col2:
        st.info("""
        **About this application:**
        
        This tool fetches air quality data from the UK Air Quality API 
        for selected monitoring sites and pollutant types.
        
        **Data Source:** 
        UK Department for Environment, Food and Rural Affairs (DEFRA)
        
        **Measurement:** 
        Annual average of hourly means (μg/m³)
        
        **Available Pollutants:**
        - PM10: Particulate matter ≤10μm
        - PM25: Particulate matter ≤2.5μm  
        - NO2: Nitrogen Dioxide
        """)
    
    with col1:
        # Add data selection controls
        st.markdown("### Data Selection")
        
        # Averaging type selection
        averaging_type = st.radio(
            "Averaging period:",
            ["Annual", "Monthly", "Daily", "Hourly"],
            index=0,
            horizontal=True
        )
        
        # Initialize variables
        start_year = end_year = 2000
        start_date = end_date = pd.to_datetime("2024-01-01").date()
        
        # Date/Year range selection based on averaging type
        if averaging_type in ["Annual", "Monthly"]:
            # Year range selection for annual/monthly data
            col_start, col_end = st.columns(2)
            with col_start:
                start_year = st.selectbox(
                    "Start year:",
                    range(2000, 2025),
                    index=0  # Default to 2000
                )
            with col_end:
                end_year = st.selectbox(
                    "End year:",
                    range(2000, 2025),
                    index=24  # Default to 2024
                )
            
            # Validate year range
            if start_year > end_year:
                st.error("Start year must be less than or equal to end year")
                return
                
        else:  # Daily or Hourly
            # Date range selection for daily/hourly data
            col_start, col_end = st.columns(2)
            with col_start:
                start_date = st.date_input(
                    "Start date:",
                    value=pd.to_datetime("2024-01-01").date(),
                    min_value=pd.to_datetime("2000-01-01").date(),
                    max_value=pd.to_datetime("2024-12-31").date()
                )
            with col_end:
                end_date = st.date_input(
                    "End date:",
                    value=pd.to_datetime("2024-01-07").date(),
                    min_value=pd.to_datetime("2000-01-01").date(),
                    max_value=pd.to_datetime("2024-12-31").date()
                )
            
            # Validate date range
            if start_date > end_date:
                st.error("Start date must be before or equal to end date")
                return
            
            # Check if date range is too large for hourly/daily data
            date_diff = (end_date - start_date).days
            if averaging_type == "Hourly" and date_diff > 183:  # 6 months (approximately)
                st.warning("For hourly data, please select a date range of 6 months or less to avoid performance issues")
                return
            elif averaging_type == "Daily" and date_diff > 730:  # 2 years
                st.warning("For daily data, please select a date range of 2 years or less to avoid performance issues")
                return
        
        # Site selection (multiple) with full names
        site_mapping = {
            "WA2": "Wandsworth Town Hall",
            "WA7": "Putney High Street", 
            "WA8": "Putney High Street facade",
            "WA9": "Felsham Road, Putney",
            "WAA": "Thessaly Road, Battersea",
            "WAB": "Tooting High Street",
            "WAC": "Lavander Hill, Clapham Junction",
            "ME2": "Merton Road, South Wimbledon",
            "ME9": "Civic Centre, Morden",
            "RI1": "Castlenau Library, Barnes",
            "RI2": "Wetland Centre, Barnes"
        }
        
        available_sites = list(site_mapping.keys())
        st.markdown("**Select monitoring sites:**")
        
        # Create columns for site checkboxes
        site_cols = st.columns(4)
        selected_sites = []
        
        for i, site_code in enumerate(available_sites):
            with site_cols[i % 4]:
                site_display = f"{site_code} - {site_mapping[site_code]}"
                if st.checkbox(site_display, value=(site_code == "RI2"), key=f"site_{site_code}"):  # Default RI2 selected
                    selected_sites.append(site_code)
        
        if not selected_sites:
            st.warning("Please select at least one monitoring site")
            return
        
        # Pollutant selection (multiple)
        available_pollutants = ["PM10", "PM25", "NO2"]
        st.markdown("**Select pollutant types:**")
        
        poll_cols = st.columns(3)
        selected_pollutants = []
        
        for i, pollutant in enumerate(available_pollutants):
            with poll_cols[i]:
                if st.checkbox(pollutant, value=(pollutant == "PM10")):  # Default PM10 selected
                    selected_pollutants.append(pollutant)
        
        if not selected_pollutants:
            st.warning("Please select at least one pollutant type")
            return
        
        st.markdown("### Data Collection")
        
        # Create fetch button text based on averaging type
        if averaging_type in ["Annual", "Monthly"]:
            fetch_button_text = f"🔄 Fetch {averaging_type} Data ({start_year}-{end_year})"
            date_range_display = f"{start_year}-{end_year}"
        else:
            fetch_button_text = f"🔄 Fetch {averaging_type} Data ({start_date} to {end_date})"
            date_range_display = f"{start_date} to {end_date}"
            
        if st.button(fetch_button_text, type="primary"):
            
            # Initialize progress tracking
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Initialize data storage
            all_data = []
            status_text.text("Fetching data from API (this may take a moment)...")
            
            if averaging_type in ["Annual", "Monthly"]:
                # Handle annual/monthly data
                years_range = list(range(start_year, end_year + 1))
                total_requests = len(years_range) * len(selected_sites) * len(selected_pollutants)
                
                def fetch_annual_combination(site, pollutant, year):
                    """Helper function to fetch annual/monthly data"""
                    annual_data = fetch_annual_data(site, year)
                    if annual_data:
                        pollutant_data = extract_pollutant_data(annual_data, pollutant, averaging_type.lower())
                        if pollutant_data:
                            return {
                                'site': site,
                                'pollutant': pollutant,
                                'year': year,
                                'data': pollutant_data,
                                'status': 'success'
                            }
                        else:
                            return {'site': site, 'pollutant': pollutant, 'year': year, 'status': 'no_data'}
                    else:
                        return {'site': site, 'pollutant': pollutant, 'year': year, 'status': 'failed'}
                
                # Create all combinations to fetch
                fetch_tasks = []
                for site in selected_sites:
                    for pollutant in selected_pollutants:
                        for year in years_range:
                            fetch_tasks.append((site, pollutant, year))
                
                # Use ThreadPoolExecutor for parallel requests
                with ThreadPoolExecutor(max_workers=8) as executor:
                    future_to_task = {executor.submit(fetch_annual_combination, site, pollutant, year): (site, pollutant, year) 
                                     for site, pollutant, year in fetch_tasks}
                    
                    completed = 0
                    missing_combinations = []
                    
                    for future in as_completed(future_to_task):
                        completed += 1
                        progress_bar.progress(completed / total_requests)
                        
                        result = future.result()
                        if result['status'] == 'success':
                            all_data.append(result)
                        elif result['status'] == 'no_data':
                            missing_combinations.append(f"{result['pollutant']} at {result['site']} for {result['year']}")
                
                date_range_info = (start_year, end_year)
                
            else:  # Daily or Hourly
                # Handle hourly/daily data
                total_requests = len(selected_sites) * len(selected_pollutants)
                start_date_str = start_date.strftime('%Y-%m-%d')
                end_date_str = end_date.strftime('%Y-%m-%d')
                
                def fetch_hourly_combination(site, pollutant):
                    """Helper function to fetch hourly/daily data"""
                    hourly_data = fetch_hourly_data(site, start_date_str, end_date_str)
                    if hourly_data:
                        pollutant_data = extract_hourly_data(hourly_data, pollutant, averaging_type.lower())
                        if pollutant_data:
                            return {
                                'site': site,
                                'pollutant': pollutant,
                                'data': pollutant_data,
                                'status': 'success'
                            }
                        else:
                            return {'site': site, 'pollutant': pollutant, 'status': 'no_data'}
                    else:
                        return {'site': site, 'pollutant': pollutant, 'status': 'failed'}
                
                # Create all combinations to fetch
                fetch_tasks = []
                for site in selected_sites:
                    for pollutant in selected_pollutants:
                        fetch_tasks.append((site, pollutant))
                
                # Use ThreadPoolExecutor for parallel requests
                with ThreadPoolExecutor(max_workers=4) as executor:  # Fewer workers for larger requests
                    future_to_task = {executor.submit(fetch_hourly_combination, site, pollutant): (site, pollutant) 
                                     for site, pollutant in fetch_tasks}
                    
                    completed = 0
                    missing_combinations = []
                    
                    for future in as_completed(future_to_task):
                        completed += 1
                        progress_bar.progress(completed / total_requests)
                        
                        result = future.result()
                        if result['status'] == 'success':
                            all_data.append(result)
                        elif result['status'] == 'no_data':
                            missing_combinations.append(f"{result['pollutant']} at {result['site']}")
                
                date_range_info = (start_date_str, end_date_str)
            
            # Clear progress indicators
            progress_bar.empty()
            status_text.empty()
            
            if all_data:
                # Store in session state for persistence
                st.session_state['all_data'] = all_data
                st.session_state['selected_sites'] = selected_sites
                st.session_state['selected_pollutants'] = selected_pollutants
                st.session_state['averaging_type'] = averaging_type
                st.session_state['date_range'] = date_range_info
                st.session_state['site_mapping'] = site_mapping
                
                st.success(f"Successfully collected data from {len(all_data)} requests out of {total_requests} total")
                
                # Display missing data summary
                if missing_combinations:
                    with st.expander(f"Missing data for {len(missing_combinations)} combinations (click to expand)"):
                        for combo in missing_combinations[:50]:  # Show first 50
                            st.text(combo)
                        if len(missing_combinations) > 50:
                            st.text(f"... and {len(missing_combinations) - 50} more")
                
            else:
                st.error("No data could be retrieved for any combination of sites, pollutants, and time period")
    
    # Display results if data is available
    if 'all_data' in st.session_state:
        all_data = st.session_state['all_data']
        sites = st.session_state['selected_sites']
        pollutants = st.session_state['selected_pollutants']
        avg_type = st.session_state['averaging_type']
        date_range = st.session_state['date_range']
        site_mapping = st.session_state.get('site_mapping', {})
        
        st.markdown("---")
        if avg_type in ["Annual", "Monthly"]:
            st.markdown(f"### 📊 {avg_type} Time Series Analysis ({date_range[0]}-{date_range[1]})")
        else:
            st.markdown(f"### 📊 {avg_type} Time Series Analysis ({date_range[0]} to {date_range[1]})")
        
        # Process data based on averaging type
        if avg_type == "Annual":
            # Create DataFrame for annual data
            chart_data = []
            for item in all_data:
                if 'annual' in item['data']:
                    site_name = site_mapping.get(item['site'], item['site'])
                    chart_data.append({
                        'Year': item['year'],
                        'Site': item['site'],
                        'Site_Name': site_name,
                        'Pollutant': item['pollutant'],
                        'Value': item['data']['annual'],
                        'Series': f"{item['pollutant']} - {item['site']} ({site_name})"
                    })
            
            df = pd.DataFrame(chart_data)
            
        elif avg_type == "Monthly":
            # Create DataFrame for monthly data
            chart_data = []
            
            for item in all_data:
                if 'monthly' in item['data']:
                    site_name = site_mapping.get(item['site'], item['site'])
                    for month_num, value in item['data']['monthly'].items():
                        # Create date for plotting
                        date_str = f"{item['year']}-{month_num:02d}"
                        chart_data.append({
                            'Date': pd.to_datetime(date_str),
                            'Year': item['year'],
                            'Month': month_num,
                            'Site': item['site'],
                            'Site_Name': site_name,
                            'Pollutant': item['pollutant'],
                            'Value': value,
                            'Series': f"{item['pollutant']} - {item['site']} ({site_name})"
                        })
            
            df = pd.DataFrame(chart_data)
            if not df.empty:
                df = df.sort_values('Date')
            
        else:  # Hourly or Daily
            # Create DataFrame for hourly/daily data
            chart_data = []
            
            for item in all_data:
                site_name = site_mapping.get(item['site'], item['site'])
                for data_point in item['data']:
                    chart_data.append({
                        'Timestamp': data_point['timestamp'],
                        'Site': item['site'],
                        'Site_Name': site_name,
                        'Pollutant': item['pollutant'],
                        'Value': data_point['value'],
                        'Series': f"{item['pollutant']} - {item['site']} ({site_name})"
                    })
            
            df = pd.DataFrame(chart_data)
            if not df.empty:
                df = df.sort_values('Timestamp')
        
        if df.empty:
            st.error("No valid data found for the selected criteria")
            return
        
        # Display summary metrics
        st.markdown("#### Summary Statistics")
        metrics_cols = st.columns(4)
        
        with metrics_cols[0]:
            st.metric("Data Points", len(df))
        with metrics_cols[1]:
            st.metric("Sites", len(df['Site'].unique()))
        with metrics_cols[2]:
            st.metric("Pollutants", len(df['Pollutant'].unique()))
        with metrics_cols[3]:
            st.metric("Avg Value", f"{df['Value'].mean():.1f} μg/m³")
        
        # CSV download functionality
        csv_data = df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=f"air_quality_data_{pd.Timestamp.now().date().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
        
        # Initialize session state for chart width if not exists
        if 'chart_width' not in st.session_state:
            st.session_state.chart_width = 100
        
        chart_width_percent = st.session_state.chart_width
        
        # Create scientific-style time series plot
        fig = go.Figure()
        
        # Generate distinct colors for each series
        colors = ['#2E86C1', '#E74C3C', '#F39C12', '#27AE60', '#8E44AD', '#17A2B8', 
                 '#FD7E14', '#6F42C1', '#20C997', '#DC3545', '#795548', '#607D8B']
        
        # Plot each series separately with gaps for missing data
        unique_series = df['Series'].unique()
        for i, series in enumerate(unique_series):
            series_data = df[df['Series'] == series].copy()
            color = colors[i % len(colors)]
            
            if avg_type == "Annual":
                # Sort by year to ensure proper line connection
                series_data = series_data.sort_values(by='Year').reset_index(drop=True)
                x_data = series_data['Year']
                hover_template = '<b>%{fullData.name}</b><br>Year: %{x}<br>Value: %{y:.2f} μg/m³<extra></extra>'
                
                # Create complete year range and insert None for missing years
                if len(series_data) > 0:
                    min_year = int(series_data['Year'].min())
                    max_year = int(series_data['Year'].max())
                    complete_years = list(range(min_year, max_year + 1))
                    
                    x_complete = []
                    y_complete = []
                    
                    for year in complete_years:
                        year_data = series_data[series_data['Year'] == year]
                        if len(year_data) > 0:
                            x_complete.append(year)
                            y_complete.append(float(year_data['Value'].iloc[0]))
                        else:
                            x_complete.append(year)
                            y_complete.append(None)  # None creates gaps in plotly
                    
                    x_data = x_complete
                    y_data = y_complete
                else:
                    y_data = series_data['Value']
                    
            elif avg_type == "Monthly":
                # Sort by date to ensure proper line connection
                series_data = series_data.sort_values(by='Date').reset_index(drop=True)
                x_data = series_data['Date']
                hover_template = '<b>%{fullData.name}</b><br>Date: %{x}<br>Value: %{y:.2f} μg/m³<extra></extra>'
                
                # Create complete monthly range and insert None for missing months
                if len(series_data) > 0:
                    min_date = series_data['Date'].min()
                    max_date = series_data['Date'].max()
                    
                    # Generate complete monthly range
                    date_range = pd.date_range(start=min_date, end=max_date, freq='MS')
                    
                    x_complete = []
                    y_complete = []
                    
                    for date in date_range:
                        month_data = series_data[series_data['Date'].dt.to_period('M') == date.to_period('M')]
                        if len(month_data) > 0:
                            x_complete.append(date)
                            y_complete.append(float(month_data['Value'].iloc[0]))
                        else:
                            x_complete.append(date)
                            y_complete.append(None)  # None creates gaps in plotly
                    
                    x_data = x_complete
                    y_data = y_complete
                else:
                    y_data = series_data['Value']
                    
            else:  # Hourly or Daily
                # Sort by timestamp to ensure proper line connection
                series_data = series_data.sort_values(by='Timestamp').reset_index(drop=True)
                hover_template = '<b>%{fullData.name}</b><br>Time: %{x}<br>Value: %{y:.2f} μg/m³<extra></extra>'
                
                # Create complete time range and insert None for missing periods
                if len(series_data) > 0:
                    min_time = series_data['Timestamp'].min()
                    max_time = series_data['Timestamp'].max()
                    
                    # Generate complete time range based on averaging type
                    if avg_type == "Hourly":
                        time_range = pd.date_range(start=min_time, end=max_time, freq='h')
                        tolerance = pd.Timedelta(minutes=30)  # 30 minute tolerance for hourly data
                    else:  # Daily
                        time_range = pd.date_range(start=min_time, end=max_time, freq='D')
                        tolerance = pd.Timedelta(hours=12)  # 12 hour tolerance for daily data
                    
                    x_complete = []
                    y_complete = []
                    
                    for time_point in time_range:
                        # Find data points within tolerance of this time point
                        time_data = series_data[abs(series_data['Timestamp'] - time_point) <= tolerance]
                        if len(time_data) > 0:
                            x_complete.append(time_point)
                            y_complete.append(float(time_data['Value'].iloc[0]))
                        else:
                            x_complete.append(time_point)
                            y_complete.append(None)  # None creates gaps in plotly
                    
                    x_data = x_complete
                    y_data = y_complete
                else:
                    x_data = series_data['Timestamp']
                    y_data = series_data['Value']
            
            # Adjust chart style based on averaging type
            if avg_type == "Hourly":
                mode = 'lines'  # Only lines for hourly data
                line_width = 1.5
                marker_config = None
            else:
                mode = 'lines+markers'  # Lines with markers for other types
                line_width = 2.5
                marker_config = dict(
                    size=4 if avg_type == "Monthly" else 6, 
                    color=color,
                    symbol='circle',
                    line=dict(width=1, color='white')
                )
            
            fig.add_trace(go.Scatter(
                x=x_data,
                y=y_data,
                mode=mode,
                name=series,
                line=dict(color=color, width=line_width),
                marker=marker_config,
                hovertemplate=hover_template,
                connectgaps=False  # This ensures gaps are shown for None values
            ))
        
        # Add reference lines for each pollutant type present in the data
        unique_pollutants = df['Pollutant'].unique()
        
        for pollutant in unique_pollutants:
            if pollutant == "PM10":
                # WHO guideline for PM10 (15 μg/m³ annual mean)
                fig.add_hline(
                    y=15, 
                    line_dash="dash", 
                    line_color="#2E86C1",
                    line_width=1.5,
                    annotation_text="WHO PM10 (15 μg/m³)",
                    annotation_position="top left",
                    annotation=dict(
                        font=dict(size=11, color="#2E86C1"),
                        bgcolor="rgba(255,255,255,0.8)",
                        bordercolor="#2E86C1",
                        borderwidth=1
                    )
                )
                # UK legal limit for PM10 (40 μg/m³ annual mean)
                fig.add_hline(
                    y=40, 
                    line_dash="dot", 
                    line_color="#FF8C00",
                    line_width=1.5,
                    annotation_text="UK PM10 Limit (40 μg/m³)",
                    annotation_position="top left",
                    annotation=dict(
                        font=dict(size=11, color="#FF8C00"),
                        bgcolor="rgba(255,255,255,0.8)",
                        bordercolor="#FF8C00",
                        borderwidth=1
                    )
                )
            elif pollutant == "PM25":
                # WHO guideline for PM2.5 (5 μg/m³ annual mean)
                fig.add_hline(
                    y=5, 
                    line_dash="dash", 
                    line_color="#2E86C1",
                    line_width=1.5,
                    annotation_text="WHO PM2.5 (5 μg/m³)",
                    annotation_position="top left",
                    annotation=dict(
                        font=dict(size=11, color="#2E86C1"),
                        bgcolor="rgba(255,255,255,0.8)",
                        bordercolor="#2E86C1",
                        borderwidth=1
                    )
                )
                # UK legal limit for PM2.5 (25 μg/m³ annual mean)
                fig.add_hline(
                    y=25, 
                    line_dash="dot", 
                    line_color="#FF8C00",
                    line_width=1.5,
                    annotation_text="UK PM2.5 Limit (25 μg/m³)",
                    annotation_position="top left",
                    annotation=dict(
                        font=dict(size=11, color="#FF8C00"),
                        bgcolor="rgba(255,255,255,0.8)",
                        bordercolor="#FF8C00",
                        borderwidth=1
                    )
                )
            elif pollutant == "NO2":
                # WHO guideline for NO2 (10 μg/m³ annual mean)
                fig.add_hline(
                    y=10, 
                    line_dash="dash", 
                    line_color="#2E86C1",
                    line_width=1.5,
                    annotation_text="WHO NO2 (10 μg/m³)",
                    annotation_position="top left",
                    annotation=dict(
                        font=dict(size=11, color="#2E86C1"),
                        bgcolor="rgba(255,255,255,0.8)",
                        bordercolor="#2E86C1",
                        borderwidth=1
                    )
                )
                # UK legal limit for NO2 (40 μg/m³ annual mean)
                fig.add_hline(
                    y=40, 
                    line_dash="dot", 
                    line_color="#FF8C00",
                    line_width=1.5,
                    annotation_text="UK NO2 Limit (40 μg/m³)",
                    annotation_position="top left",
                    annotation=dict(
                        font=dict(size=11, color="#FF8C00"),
                        bgcolor="rgba(255,255,255,0.8)",
                        bordercolor="#FF8C00",
                        borderwidth=1
                    )
                )
        
        # Set up chart title and axis labels
        if avg_type == "Annual":
            x_title = '<b>Year</b>'
            chart_title = f'<b>Air Quality {avg_type} Data ({date_range[0]}-{date_range[1]})</b>'
        elif avg_type == "Monthly":
            x_title = '<b>Date</b>'
            chart_title = f'<b>Air Quality {avg_type} Data ({date_range[0]}-{date_range[1]})</b>'
        else:  # Hourly or Daily
            x_title = '<b>Time</b>'
            chart_title = f'<b>Air Quality {avg_type} Data ({date_range[0]} to {date_range[1]})</b>'
        
        fig.update_layout(
            title={
                'text': chart_title,
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20, 'color': '#2C3E50'}
            },
            xaxis=dict(
                title=dict(text=x_title, font=dict(size=18, color='#2C3E50')),
                tickfont=dict(size=16, color='#2C3E50'),
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(128,128,128,0.2)',
                zeroline=False,
                showline=True,
                linewidth=2,
                linecolor='#2C3E50',
                mirror=True,
                ticks='outside',
                tickwidth=1,
                tickcolor='#2C3E50',
                **(dict(dtick=1) if avg_type == "Annual" else {})
            ),
            yaxis=dict(
                title=dict(text='<b>Concentration (μg/m³)</b>', font=dict(size=18, color='#2C3E50')),
                tickfont=dict(size=16, color='#2C3E50'),
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(128,128,128,0.2)',
                zeroline=True,
                zerolinewidth=1,
                zerolinecolor='rgba(128,128,128,0.3)',
                showline=True,
                linewidth=2,
                linecolor='#2C3E50',
                mirror=True,
                ticks='outside',
                tickwidth=1,
                tickcolor='#2C3E50',
                rangemode='tozero'
            ),
            plot_bgcolor='white',
            paper_bgcolor='white',
            hovermode='x unified',
            height=600,
            showlegend=True,
            legend=dict(
                x=0.98,
                y=0.98,
                xanchor='right',
                yanchor='top',
                bgcolor='rgba(255,255,255,0.9)',
                bordercolor='#2C3E50',
                borderwidth=1,
                font=dict(size=14, color='#2C3E50')
            ),
            margin=dict(l=80, r=40, t=80, b=60)
        )
        
        # Display chart with custom width and center alignment
        if chart_width_percent < 100:
            # Create centered columns for custom width
            left_margin = (100 - chart_width_percent) / 2
            col1, col2, col3 = st.columns([left_margin, chart_width_percent, left_margin])
            
            with col2:
                st.plotly_chart(fig, use_container_width=True)
        else:
            # Full width display
            st.plotly_chart(fig, use_container_width=True)
        
        # Chart width slider below the chart
        chart_width_percent = st.slider(
            "Chart width",
            min_value=50,
            max_value=100,
            value=st.session_state.chart_width,
            step=5,
            format="%d%%",
            key="chart_width_slider"
        )
        
        # Update session state when slider changes
        if chart_width_percent != st.session_state.chart_width:
            st.session_state.chart_width = chart_width_percent
            st.rerun()
        
        # Data table display
        st.markdown("### Complete Dataset")
        
        # Format the dataframe for display
        display_df = df.copy()
        display_df['Value'] = display_df['Value'].round(2)
        
        if avg_type == "Annual":
            display_columns = ['Year', 'Site', 'Site_Name', 'Pollutant', 'Value']
        elif avg_type == "Monthly":
            display_columns = ['Date', 'Site', 'Site_Name', 'Pollutant', 'Value']
            display_df['Date'] = display_df['Date'].dt.strftime('%Y-%m')
        else:  # Hourly or Daily
            display_columns = ['Timestamp', 'Site', 'Site_Name', 'Pollutant', 'Value']
            display_df['Timestamp'] = display_df['Timestamp'].dt.strftime('%Y-%m-%d %H:%M' if avg_type == "Hourly" else '%Y-%m-%d')
        
        st.dataframe(
            display_df[display_columns],
            use_container_width=True,
            hide_index=True
        )
        
        # Data validation and quality information
        st.markdown("### Data Quality Information")
        
        info_col1, info_col2 = st.columns(2)
        
        with info_col1:
            st.info(f"""
            **Data Source Validation:**
            - API Endpoint: UK Air Quality Network
            - Sites: {', '.join(sites)}
            - Pollutants: {', '.join(pollutants)}
            - Averaging: {avg_type}
            - Units: Micrograms per cubic meter (μg/m³)
            - Missing data values (-999) are automatically excluded
            """)
        
        with info_col2:
            if avg_type in ["Annual", "Monthly"]:
                years_requested = date_range[1] - date_range[0] + 1
                if avg_type == "Annual":
                    total_possible = years_requested * len(sites) * len(pollutants)
                else:
                    total_possible = years_requested * 12 * len(sites) * len(pollutants)
                period_info = f"{date_range[0]}-{date_range[1]} ({years_requested} years)"
            else:  # Hourly or Daily
                from datetime import datetime
                start_dt = datetime.strptime(date_range[0], '%Y-%m-%d')
                end_dt = datetime.strptime(date_range[1], '%Y-%m-%d')
                days_requested = (end_dt - start_dt).days + 1
                if avg_type == "Hourly":
                    total_possible = days_requested * 24 * len(sites) * len(pollutants)
                else:  # Daily
                    total_possible = days_requested * len(sites) * len(pollutants)
                period_info = f"{date_range[0]} to {date_range[1]} ({days_requested} days)"
            
            st.info(f"""
            **Dataset Summary:**
            - Period: {period_info}
            - Data points collected: {len(df)}
            - Total possible data points: {total_possible}
            - Data completeness: {(len(df)/total_possible)*100:.1f}%
            - Sites with data: {len(df['Site'].unique())}
            - Pollutants with data: {len(df['Pollutant'].unique())}
            """)

if __name__ == "__main__":
    main()
