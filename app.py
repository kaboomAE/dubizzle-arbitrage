import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import asyncio
import os
import subprocess
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime

# --- 1. MUST BE THE ABSOLUTE FIRST STREAMLIT COMMAND ---
st.set_page_config(page_title="Dubizzle Arbitrage Pro", layout="wide", page_icon="🚀")

# --- BROWSER INITIALIZATION FOR STREAMLIT CLOUD ---
def install_playwright_browsers():
    try:
        subprocess.run(["playwright", "install", "chromium"], check=True)
        return True
    except Exception as e:
        print(f"Error installing browser binaries: {e}")
        return False

if 'browser_installed' not in st.session_state:
    with st.spinner("Setting up browser environment..."):
        if install_playwright_browsers():
            st.session_state.browser_installed = True

# --- DEBUGGING UTILS ---
if 'debug_logs' not in st.session_state:
    st.session_state.debug_logs = []

def add_log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.debug_logs.append(f"[{timestamp}] {msg}")
    if len(st.session_state.debug_logs) > 20:
        st.session_state.debug_logs.pop(0)

# --- CONFIGURATION & STYLING ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { border-radius: 10px; padding: 10px; background: white; border: 1px solid #eee; }
    .debug-log { 
        font-family: monospace; 
        background-color: #1e1e1e; 
        color: #00ff00; 
        padding: 10px; 
        border-radius: 5px; 
        font-size: 0.8rem;
        max-height: 200px;
        overflow-y: auto;
    }
    </style>
    """, unsafe_allow_html=True)

# --- REAL SCRAPER ENGINE ---
async def scrape_dubizzle(search_query, debug_mode=False):
    results = []
    url = f"https://uae.dubizzle.com/en/classified/search/?q={search_query.replace(' ', '+')}"
    
    add_log(f"Starting scrape for: {search_query}")
    add_log(f"URL: {url}")
    
    screenshot_data = None
    html_sample = ""
    status_code = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page = await context.new_page()
        
        try:
            add_log("Navigating to page...")
            response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            status_code = response.status
            add_log(f"Response Status: {status_code}")

            # Take a debug screenshot if needed
            if debug_mode:
                screenshot_data = await page.screenshot(type="jpeg", quality=50)
                add_log("Screenshot captured.")

            # Wait for content or anti-bot
            await asyncio.sleep(3)
            
            content = await page.content()
            html_sample = content[:1000] # Grab start of HTML for debugging
            
            soup = BeautifulSoup(content, 'html.parser')
            listings = soup.find_all('div', {'data-testid': 'listing-card'})
            
            add_log(f"Found {len(listings)} listing cards via primary selector.")
            
            if not listings:
                add_log("Attempting fallback selectors...")
                listings = soup.select('div[class*="listing-card"]')
                add_log(f"Found {len(listings)} cards via fallback.")

            for item in listings:
                try:
                    title_elem = item.find('h2', {'data-testid': 'listing-title'})
                    price_elem = item.find('div', {'data-testid': 'listing-price'})
                    link_elem = item.find('a')
                    
                    if title_elem and price_elem:
                        price_text = price_elem.text.strip()
                        price = int(''.join(filter(str.isdigit, price_text)))
                        
                        results.append({
                            "Timestamp": pd.Timestamp.now(),
                            "Title": title_elem.text.strip(),
                            "Model": search_query,
                            "Price": price,
                            "Location": item.find('span', {'data-testid': 'listing-location'}).text.strip() if item.find('span', {'data-testid': 'listing-location'}) else "Unknown",
                            "Link": "https://uae.dubizzle.com" + link_elem['href'] if not link_elem['href'].startswith('http') else link_elem['href']
                        })
                except Exception as e:
                    continue
                    
        except Exception as e:
            add_log(f"CRITICAL ERROR: {str(e)}")
            st.error(f"Scraper Error: {e}")
        finally:
            await browser.close()
            add_log("Browser closed.")
            
    return pd.DataFrame(results), screenshot_data, html_sample, status_code

# --- ARBITRAGE LOGIC ---
def calculate_arbitrage(df):
    if df.empty: return df
    filtered_df = df[df['Price'] > 50].copy()
    if filtered_df.empty: return df
    median = filtered_df['Price'].median()
    filtered_df['Market_Median'] = median
    filtered_df['Profit_AED'] = filtered_df['Market_Median'] - filtered_df['Price']
    filtered_df['ROI_%'] = (filtered_df['Profit_AED'] / filtered_df['Price']) * 100
    return filtered_df

# --- UI MAIN ---
def main():
    st.sidebar.title("🔧 Settings & Debug")
    category = st.sidebar.selectbox("Category", ["iPhone 15 Pro", "Rolex Submariner", "PS5 Console", "MacBook M3"])
    roi_threshold = st.sidebar.slider("Min ROI %", 0, 50, 10)
    
    debug_mode = st.sidebar.checkbox("Enable Debug Mode", value=True)
    
    if debug_mode:
        st.sidebar.subheader("Live Logs")
        log_text = "\n".join(st.session_state.debug_logs)
        st.sidebar.markdown(f'<div class="debug-log">{log_text}</div>', unsafe_allow_html=True)
        if st.sidebar.button("Clear Logs"):
            st.session_state.debug_logs = []
            st.rerun()

    st.title("🚀 Dubizzle Arbitrage Dashboard")
    
    if st.button("🔍 Scan Live Market", use_container_width=True):
        if not st.session_state.get('browser_installed'):
            st.warning("Browser not ready.")
            return

        with st.spinner("Extracting live listings..."):
            df_raw, screenshot, html_snippet, status = asyncio.run(scrape_dubizzle(category, debug_mode))
            
            if debug_mode:
                with st.expander("🛠️ Technical Debug View"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"**HTTP Status:** {status}")
                        if screenshot:
                            st.image(screenshot, caption="Scraper Visual Context", use_container_width=True)
                    with c2:
                        st.write("**HTML Snippet (Top 1000 chars):**")
                        st.code(html_snippet, language="html")

            if not df_raw.empty:
                df = calculate_arbitrage(df_raw)
                deals = df[df['ROI_%'] >= roi_threshold].sort_values(by='ROI_%', ascending=False)
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Scanned", len(df))
                m2.metric("Hot Deals", len(deals))
                m3.metric("Median Price", f"AED {df['Market_Median'].iloc[0]:,.0f}")
                
                st.plotly_chart(px.histogram(df, x="Price", title="Price Distribution"), use_container_width=True)
                
                st.subheader("🔥 Best Opportunities")
                for _, row in deals.iterrows():
                    with st.container():
                        cols = st.columns([3, 1, 1])
                        cols[0].markdown(f"**{row['Title']}**\n\n📍 {row['Location']}")
                        cols[1].markdown(f"💰 **AED {row['Price']:,}**\n\nROI: {row['ROI_%']:.1f}%")
                        cols[2].link_button("View", row['Link'], use_container_width=True)
                        st.divider()
            else:
                st.error("Scraper returned no results.")
                if status == 403:
                    st.warning("Dubizzle is blocking this server's IP. You may need a residential proxy.")

if __name__ == "__main__":
    main()