import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import asyncio
import os
import random
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# --- BROWSER INITIALIZATION FOR STREAMLIT CLOUD ---
def install_playwright():
    """Ensures playwright browsers are installed on the Streamlit server."""
    try:
        import playwright
    except ImportError:
        os.system("pip install playwright")
    
    # This command installs chromium specifically for the Linux environment
    os.system("playwright install chromium")

# Run installation only once per session
if 'browser_installed' not in st.session_state:
    with st.spinner("Installing browser dependencies... this may take a minute on first run."):
        install_playwright()
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
    url = f"https://uae.dubizzle.com/en/classified/search/?q={search_query.replace(' ', '+')}"
    
    async with async_playwright() as p:
        # Launching in headless mode is mandatory for Streamlit Cloud
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # Selectors based on Dubizzle's 2025/2026 layout
            listings = soup.find_all('div', {'data-testid': 'listing-card'})
            
            for item in listings:
                try:
                    title = item.find('h2', {'data-testid': 'listing-title'}).text.strip()
                    price_text = item.find('div', {'data-testid': 'listing-price'}).text.strip()
                    price = int(''.join(filter(str.isdigit, price_text)))
                    link = "https://uae.dubizzle.com" + item.find('a')['href']
                    location = item.find('span', {'data-testid': 'listing-location'}).text.strip() if item.find('span', {'data-testid': 'listing-location'}) else "Unknown"
                    
                    results.append({
                        "Timestamp": pd.Timestamp.now(),
                        "Title": title,
                        "Model": search_query, # Simplified for demo
                        "Price": price,
                        "Location": location,
                        "Link": link
                    })
                except Exception:
                    continue
        except Exception as e:
            st.error(f"Scrape failed: {e}")
        finally:
            await browser.close()
            
    return pd.DataFrame(results)

# --- ARBITRAGE LOGIC ---
def calculate_arbitrage(df):
    if df.empty: return df
    
    median = df['Price'].median()
    df['Market_Median'] = median
    
    # Profit calculation
    df['Profit_AED'] = df['Market_Median'] - df['Price']
    df['ROI_%'] = (df['Profit_AED'] / df['Price']) * 100
    
    # Simple Z-Score calculation for anomaly detection
    std = df['Price'].std() if df['Price'].std() > 0 else 1
    df['Z_Score'] = (df['Price'] - median) / std
    
    return df

# --- UI MAIN ---
def main():
    st.sidebar.title("Search Parameters")
    category = st.sidebar.selectbox("Category", ["iPhone 15 Pro", "Rolex Submariner", "PS5 Console"])
    roi_threshold = st.sidebar.slider("Min ROI %", 0, 50, 10)
    
    st.title("🚀 Dubizzle Arbitrage Dashboard")
    st.info(f"Currently monitoring: {category}")

    if st.button("🔍 Scan Live Market"):
        with st.spinner("Accessing Dubizzle..."):
            # Execute the async scraper
            raw_data = asyncio.run(scrape_dubizzle(category))
            
            if not raw_data.empty:
                df = calculate_arbitrage(raw_data)
                
                # Show Metrics
                deals = df[df['ROI_%'] >= roi_threshold].sort_values(by='ROI_%', ascending=False)
                m1, m2, m3 = st.columns(3)
                m1.metric("Items Scanned", len(df))
                m2.metric("Hot Deals Found", len(deals))
                m3.metric("Market Median", f"AED {df['Market_Median'].iloc[0]:,.0f}")
                
                # Plot
                fig = px.histogram(df, x="Price", title="Market Price Distribution", color_discrete_sequence=['#ff4b4b'])
                st.plotly_chart(fig, use_container_width=True)
                
                # Results List
                st.subheader("🔥 Top Deals Identified")
                if deals.empty:
                    st.warning("No deals found matching your ROI criteria.")
                else:
                    for _, row in deals.iterrows():
                        with st.container():
                            c1, c2, c3 = st.columns([3, 1, 1])
                            c1.markdown(f"**{row['Title']}**\n\n📍 {row['Location']}")
                            c2.markdown(f"💰 **AED {row['Price']:,}**\n\nROI: {row['ROI_%']:.1f}%")
                            c3.link_button("View Ad", row['Link'], type="primary")
                            st.divider()
            else:
                st.error("No data returned. Dubizzle may be blocking the request. Try a different search term.")

if __name__ == "__main__":
    main()