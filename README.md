# UK Air Quality Analysis Dashboard

A comprehensive Streamlit application for analyzing UK air quality data from the Department for Environment, Food and Rural Affairs (DEFRA) monitoring network.

## Features

- **Multi-site Analysis**: Compare air quality across 11 monitoring sites in London
- **Time Series Visualization**: View annual, monthly, daily, or hourly pollution trends
- **Pollutant Monitoring**: Track PM10, PM2.5, and NO2 concentrations
- **Interactive Charts**: Plotly-powered visualizations with WHO/UK limit guidelines
- **Data Export**: Download analysis results as CSV files
- **Gap Detection**: Charts show data gaps instead of connecting missing periods

## Monitoring Sites

- **WA2** - Wandsworth Town Hall
- **WA7** - Putney High Street
- **WA8** - Putney High Street facade
- **WA9** - Felsham Road, Putney
- **WAA** - Thessaly Road, Battersea
- **WAB** - Tooting High Street
- **WAC** - Lavander Hill, Clapham Junction
- **ME2** - Merton Road, South Wimbledon
- **ME9** - Civic Centre, Morden
- **RI1** - Castlenau Library, Barnes
- **RI2** - Wetland Centre, Barnes

## Data Source

This application uses real-time data from the UK Air Quality Network API, providing:
- Annual averages (2000-2024)
- Monthly breakdowns
- Daily measurements
- Hourly readings

All concentration values are measured in micrograms per cubic meter (μg/m³).

## Usage

1. Select the time period (Annual, Monthly, Daily, or Hourly)
2. Choose date/year range
3. Select monitoring sites of interest
4. Pick pollutant types to analyze
5. Click "Fetch Data" to generate visualizations
6. Use the chart width slider to adjust display
7. Download data as CSV for further analysis

## Technical Details

- Built with Streamlit and Plotly
- Parallel API requests for efficient data collection
- Automatic data validation and quality checks
- Responsive design with customizable chart widths