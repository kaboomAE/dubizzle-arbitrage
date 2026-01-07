import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import asyncio
import os
import subprocess
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# --- BROWSER INITIALIZATION FOR STREAMLIT CLOUD ---
def install_playwright_browsers():
    """
    In Streamlit Cloud, the 'playwright' python package is installed via requirements.txt,
    but the actual Chromium binaries need to be downloaded.
    """
    try:
        # Check if chromium is already available
        subprocess.run(["playwright", "install", "chromium"], check=True)
        return True
    except Exception as e:
        st.error(f"Error installing browser binaries: {e}")
        return False

# Run installation once per session
if 'browser_installed' not in st.session_state:
    with st.spinner("Setting up browser environment... this happens only on first run."):
        if install_playwright_browsers():
            st.session_state.browser_installed = True

# --- CONFIGURATION & STYLING ---
st.set_page_config(page_title="Dubizzle Arbitrage Pro", layout="wide", page_icon="🚀")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { border-radius: 10px; padding: 10px; background: white; border: 1px solid #eee; }
    .deal-card { 
        padding: 20px; 
        border-radius: 15px; 
        border-left: 5px solid #28a745; 
        background: white; 
        margin-bottom: 10px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

# --- REAL SCRAPER ENGINE ---
async def scrape_dubizzle(search_query):
    """
    Actual scraper using Playwright. 
    Note: Real-world use requires residential proxies for high volume.
    """
    results = []
    # URL construction for Dubai search
    url = f"https://uae.dubizzle.com/en/classified/search/?q={search_query.replace(' ', '+')}"
    
    async with async_playwright() as p:
        # Headless mode is mandatory for cloud environments
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            # Set a reasonable timeout for cloud latency
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Wait a few seconds for anti-bot checks to settle
            await asyncio.sleep(2)
            
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # Selectors based on Dubizzle's current layout
            listings = soup.find_all('div', {'data-testid': 'listing-card'})
            
            for item in listings:
                try:
                    title_elem = item.find('h2', {'data-testid': 'listing-title'})
                    price_elem = item.find('div', {'data-testid': 'listing-price'})
                    link_elem = item.find('a')
                    
                    if not title_elem or not price_elem:
                        continue
                        
                    title = title_elem.text.strip()
                    price_text = price_elem.text.strip()
                    price = int(''.join(filter(str.isdigit, price_text)))
                    link = "https://uae.dubizzle.com" + link_elem['href']
                    
                    location_elem = item.find('span', {'data-testid': 'listing-location'})
                    location = location_elem.text.strip() if location_elem else "Unknown"
                    
                    results.append({
                        "Timestamp": pd.Timestamp.now(),
                        "Title": title,
                        "Model": search_query,
                        "Price": price,
                        "Location": location,
                        "Link": link
                    })
                except Exception:
                    continue
        except Exception as e:
            st.error(f"Scrape encountered an issue: {e}")
        finally:
            await browser.close()
            
    return pd.DataFrame(results)

# --- ARBITRAGE LOGIC ---
def calculate_arbitrage(df):
    if df.empty: return df
    
    # Filter out extreme outliers that might be '1 AED' placeholder prices
    filtered_df = df[df['Price'] > 50].copy()
    
    if filtered_df.empty: return df

    median = filtered_df['Price'].median()
    filtered_df['Market_Median'] = median
    
    # Profit calculation
    filtered_df['Profit_AED'] = filtered_df['Market_Median'] - filtered_df['Price']
    filtered_df['ROI_%'] = (filtered_df['Profit_AED'] / filtered_df['Price']) * 100
    
    # Simple Z-Score calculation for anomaly detection
    std = filtered_df['Price'].std() if filtered_df['Price'].std() > 0 else 1
    filtered_df['Z_Score'] = (filtered_df['Price'] - median) / std
    
    return filtered_df

# --- UI MAIN ---
def main():
    st.sidebar.title("Search Parameters")
    category = st.sidebar.selectbox("Category", ["iPhone 15 Pro", "Rolex Submariner", "PS5 Console", "MacBook M3"])
    roi_threshold = st.sidebar.slider("Min ROI %", 0, 50, 10)
    
    st.title("🚀 Dubizzle Arbitrage Dashboard")
    st.info(f"Currently monitoring: {category}")

    if st.button("🔍 Scan Live Market"):
        if not st.session_state.get('browser_installed'):
            st.warning("Browser environment is still initializing. Please wait a moment and try again.")
            return

        with st.spinner("Extracting live listings..."):
            # Execute the async scraper
            raw_data = asyncio.run(scrape_dubizzle(category))
            
            if not raw_data.empty:
                df = calculate_arbitrage(raw_data)
                
                # Show Metrics
                deals = df[df['ROI_%'] >= roi_threshold].sort_values(by='ROI_%', ascending=False)
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Items Scanned", len(df))
                m2.metric("Hot Deals Found", len(deals))
                m3.metric("Market Median", f"AED {df['Market_Median'].iloc[0]:,.0f}" if not df.empty else "N/A")
                
                # Visuals
                col_left, col_right = st.columns([2, 1])
                with col_left:
                    fig = px.histogram(df, x="Price", title="Market Price Distribution", 
                                     color_discrete_sequence=['#ff4b4b'], labels={'Price': 'Price (AED)'})
                    st.plotly_chart(fig, use_container_width=True)
                
                with col_right:
                    st.markdown("### Strategy Insight")
                    st.write("Prices significantly lower than the median (left of the peak) are potential arbitrage opportunities.")
                
                # Results List
                st.subheader("🔥 Top Deals Identified")
                if deals.empty:
                    st.warning("No deals found matching your ROI criteria currently.")
                else:
                    for _, row in deals.iterrows():
                        with st.container():
                            c1, c2, c3 = st.columns([3, 1, 1])
                            c1.markdown(f"**{row['Title']}**\n\n📍 {row['Location']}")
                            c2.markdown(f"💰 **AED {row['Price']:,}**\n\n**ROI: {row['ROI_%']:.1f}%**")
                            c3.link_button("View Ad", row['Link'], type="primary", use_container_width=True)
                            st.divider()
            else:
                st.error("No data returned. Dubizzle's anti-bot system might be active. Try refreshing in a few minutes.")

if __name__ == "__main__":
    main()