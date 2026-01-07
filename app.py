import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import asyncio
import os
import subprocess
import random
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime

# --- 1. MUST BE THE ABSOLUTE FIRST STREAMLIT COMMAND ---
st.set_page_config(page_title="Dubizzle Arbitrage Pro", layout="wide", page_icon="🚀")

# --- BROWSER INITIALIZATION FOR STREAMLIT CLOUD ---
def install_playwright_browsers():
    try:
        # Standard install
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
async def scrape_dubizzle(search_query, debug_mode=False, proxy_list=None):
    results = []
    base_url = "https://uae.dubizzle.com/en/"
    search_url = f"https://uae.dubizzle.com/en/classified/search/?q={search_query.replace(' ', '+')}"
    
    add_log(f"Starting Proxy-Rotated Scrape for: {search_query}")
    
    screenshot_data = None
    html_sample = ""
    status_code = 0
    used_proxy = None

    # Determine proxy for this run
    proxy_config = None
    if proxy_list:
        proxy_str = random.choice(proxy_list).strip()
        if proxy_str:
            # Expected format: http://user:pass@host:port or http://host:port
            used_proxy = proxy_str
            proxy_config = {"server": proxy_str}
            add_log(f"Using Proxy: {used_proxy}")

    async with async_playwright() as p:
        # Launch with arguments to disable automation flags
        browser = await p.chromium.launch(
            headless=True,
            proxy=proxy_config,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox'
            ]
        )
        
        # Realistic User Agents
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]

        context = await browser.new_context(
            user_agent=random.choice(user_agents),
            viewport={'width': 1920, 'height': 1080},
            java_script_enabled=True,
            ignore_https_errors=True
        )

        page = await context.new_page()
        
        # Mask the webdriver property
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        try:
            # 1. First visit the homepage to solve initial JS challenges and get cookies
            add_log("Establishing session on homepage...")
            await page.goto(base_url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(random.uniform(2, 4))

            # 2. Navigate to search URL
            add_log(f"Navigating to search results...")
            response = await page.goto(search_url, wait_until="networkidle", timeout=60000)
            status_code = response.status
            add_log(f"Response Status: {status_code}")

            # 3. Handle possible Incapsula/Imperva delay
            page_text = await page.content()
            if "Incapsula" in page_text or "incident_id" in page_text:
                add_log("Detected Incapsula challenge. Waiting for resolution...")
                await asyncio.sleep(8) 

            # Take debug screenshot
            if debug_mode:
                screenshot_data = await page.screenshot(type="jpeg", quality=60)
                add_log("Screenshot captured.")

            # Scroll to trigger lazy loading and prove humanity
            await page.mouse.wheel(0, 500)
            await asyncio.sleep(2)
            
            content = await page.content()
            html_sample = content[:1500]
            
            soup = BeautifulSoup(content, 'html.parser')
            listings = soup.find_all('div', {'data-testid': 'listing-card'})
            
            add_log(f"Found {len(listings)} listings.")
            
            if not listings:
                # Secondary fallback for grid view
                listings = soup.select('div[class*="ListingCard"]')
                add_log(f"Fallback check: Found {len(listings)} items.")

            for item in listings:
                try:
                    title_elem = item.find('h2', {'data-testid': 'listing-title'}) or item.select_one('h2[class*="title"]')
                    price_elem = item.find('div', {'data-testid': 'listing-price'}) or item.select_one('div[class*="price"]')
                    link_elem = item.find('a')
                    
                    if title_elem and price_elem:
                        price_text = price_elem.text.strip()
                        price = int(''.join(filter(str.isdigit, price_text)))
                        
                        raw_link = link_elem['href'] if link_elem else "#"
                        full_link = raw_link if raw_link.startswith('http') else "https://uae.dubizzle.com" + raw_link
                        
                        results.append({
                            "Timestamp": pd.Timestamp.now(),
                            "Title": title_elem.text.strip(),
                            "Model": search_query,
                            "Price": price,
                            "Location": item.find('span', {'data-testid': 'listing-location'}).text.strip() if item.find('span', {'data-testid': 'listing-location'}) else "Dubai",
                            "Link": full_link
                        })
                except Exception:
                    continue
                    
        except Exception as e:
            add_log(f"CRITICAL ERROR: {str(e)}")
            st.error(f"Scraper Error: {e}")
        finally:
            await browser.close()
            add_log("Browser closed.")
            
    return pd.DataFrame(results), screenshot_data, html_sample, status_code, used_proxy

# --- ARBITRAGE LOGIC ---
def calculate_arbitrage(df):
    if df.empty: return df
    filtered_df = df[df['Price'] > 100].copy() # Filter spam prices
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
    
    # Proxy Management
    st.sidebar.subheader("🌐 Proxy Management")
    use_proxies = st.sidebar.toggle("Use Proxies", value=False)
    proxies_raw = st.sidebar.text_area(
        "Proxy List (one per line)", 
        placeholder="http://user:pass@host:port\nhttp://host2:port2",
        help="Paste your proxies here. Each search will pick one at random."
    )
    
    proxy_list = [p.strip() for p in proxies_raw.split("\n") if p.strip()] if use_proxies else None
    
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
            df_raw, screenshot, html_snippet, status, used_p = asyncio.run(scrape_dubizzle(category, debug_mode, proxy_list))
            
            if debug_mode:
                with st.expander("🛠️ Technical Debug View"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"**HTTP Status:** {status}")
                        st.write(f"**Proxy Used:** {used_p if used_p else 'Direct IP (Cloud)'}")
                        if screenshot:
                            st.image(screenshot, caption="What the Scraper Sees", use_container_width=True)
                    with c2:
                        st.write("**HTML Snippet:**")
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
                        cols[1].markdown(f"💰 **AED {row['Price']:,}**\n\n**ROI: {row['ROI_%']:.1f}%**")
                        cols[2].link_button("View Ad", row['Link'], use_container_width=True)
                        st.divider()
            else:
                st.error("Scraper returned no results.")
                if "Incapsula" in html_snippet or "incident_id" in html_snippet:
                    st.warning("Blocked by Imperva Firewall. Please use high-quality residential proxies.")

if __name__ == "__main__":
    main()