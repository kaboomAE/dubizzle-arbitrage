import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import asyncio
import os
import subprocess
import random
import re
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
    if len(st.session_state.debug_logs) > 30:
        st.session_state.debug_logs.pop(0)

# --- PROXY PARSER ---
def parse_proxy(proxy_str):
    """
    Enhanced Proxy Parser.
    Handles:
    - user:pass@host:port
    - host:port:user:pass
    - host:port
    Automatically adds http:// if protocol is missing.
    """
    proxy_str = proxy_str.strip()
    if not proxy_str:
        return None
    
    # Check for host:port:user:pass format first
    parts = proxy_str.split(':')
    if len(parts) == 4:
        return {
            "server": f"http://{parts[0]}:{parts[1]}",
            "username": parts[2],
            "password": parts[3]
        }
    
    # Check for user:pass@host:port (or variations with/without http)
    regex = r"^(?:https?://)?(?:(?P<user>[^:]+):(?P<pass>[^@]+)@)?(?P<host>[^:]+):(?P<port>\d+)$"
    match = re.match(regex, proxy_str)
    
    if match:
        d = match.groupdict()
        config = {"server": f"http://{d['host']}:{d['port']}"}
        if d['user'] and d['pass']:
            config["username"] = d['user']
            config["password"] = d['pass']
        return config
    
    # Fallback: Just assume it's host:port if it looks like it
    if ":" in proxy_str:
        clean_proxy = proxy_str if "://" in proxy_str else f"http://{proxy_str}"
        return {"server": clean_proxy}
        
    return None

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
        max-height: 300px;
        overflow-y: auto;
    }
    </style>
    """, unsafe_allow_html=True)

# --- REAL SCRAPER ENGINE ---
async def scrape_dubizzle(search_query, debug_mode=False, proxy_list=None):
    results = []
    base_url = "https://uae.dubizzle.com/en/"
    search_url = f"https://uae.dubizzle.com/en/classified/search/?q={search_query.replace(' ', '+')}"
    
    add_log(f"Starting Scrape for: {search_query}")
    
    screenshot_data = None
    html_sample = ""
    status_code = 0
    proxy_config = None

    if proxy_list:
        raw_proxy = random.choice(proxy_list)
        proxy_config = parse_proxy(raw_proxy)
        if proxy_config:
            add_log(f"Using Proxy Server: {proxy_config['server']}")
            if "username" in proxy_config:
                add_log("Proxy credentials applied successfully.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy=proxy_config,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security'
            ]
        )
        
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        ]

        context = await browser.new_context(
            user_agent=random.choice(user_agents),
            viewport={'width': 1280, 'height': 800},
            java_script_enabled=True
        )

        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        try:
            add_log("Connecting via proxy and setting cookies...")
            response = await page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
            add_log(f"Initial Connection Status: {response.status}")
            
            if response.status == 407:
                add_log("CRITICAL: Proxy Authentication Required (407).")
                st.error("Authentication failed. Please verify your proxy username and password.")
                return pd.DataFrame(), None, "407 Error", 407, proxy_config

            await asyncio.sleep(random.uniform(1, 3))

            add_log(f"Fetching search results...")
            response = await page.goto(search_url, wait_until="networkidle", timeout=45000)
            status_code = response.status
            add_log(f"Search Results Status: {status_code}")

            if debug_mode:
                try:
                    add_log("Capturing visual state...")
                    screenshot_data = await page.screenshot(type="jpeg", quality=50, timeout=10000, animations="disabled")
                    add_log("Screenshot saved.")
                except Exception as e:
                    add_log(f"Screenshot skipped: {str(e)}")

            page_content = await page.content()
            if "Incapsula" in page_content or "incident_id" in page_content:
                add_log("Firewall Block detected in HTML content.")
            
            html_sample = page_content[:1000]
            
            soup = BeautifulSoup(page_content, 'html.parser')
            listings = soup.find_all('div', {'data-testid': 'listing-card'})
            
            add_log(f"Parsed {len(listings)} items from the page.")
            
            for item in listings:
                try:
                    title_elem = item.find('h2', {'data-testid': 'listing-title'})
                    price_elem = item.find('div', {'data-testid': 'listing-price'})
                    link_elem = item.find('a')
                    
                    if title_elem and price_elem:
                        price_val = int(''.join(filter(str.isdigit, price_elem.text.strip())))
                        raw_link = link_elem['href'] if link_elem else "#"
                        
                        results.append({
                            "Timestamp": pd.Timestamp.now(),
                            "Title": title_elem.text.strip(),
                            "Model": search_query,
                            "Price": price_val,
                            "Location": item.find('span', {'data-testid': 'listing-location'}).text.strip() if item.find('span', {'data-testid': 'listing-location'}) else "UAE",
                            "Link": raw_link if raw_link.startswith('http') else "https://uae.dubizzle.com" + raw_link
                        })
                except: continue
                    
        except Exception as e:
            add_log(f"ERROR: {str(e)}")
        finally:
            await browser.close()
            add_log("Browser closed.")
            
    return pd.DataFrame(results), screenshot_data, html_sample, status_code, proxy_config

# --- ARBITRAGE LOGIC ---
def calculate_arbitrage(df):
    if df.empty: return df
    filtered_df = df[df['Price'] > 100].copy()
    if filtered_df.empty: return df
    median = filtered_df['Price'].median()
    filtered_df['Market_Median'] = median
    filtered_df['Profit_AED'] = filtered_df['Market_Median'] - filtered_df['Price']
    filtered_df['ROI_%'] = (filtered_df['Profit_AED'] / filtered_df['Price']) * 100
    return filtered_df

# --- UI MAIN ---
def main():
    st.sidebar.title("🔧 Arbitrage Settings")
    category = st.sidebar.selectbox("Category", ["iPhone 15 Pro", "Rolex Submariner", "PS5 Console", "MacBook M3"])
    roi_threshold = st.sidebar.slider("Min ROI % Filter", 0, 50, 10)
    
    st.sidebar.subheader("🌐 Proxy Settings")
    use_proxies = st.sidebar.toggle("Enable Proxies", value=True)
    proxies_raw = st.sidebar.text_area(
        "Proxy List (one per line)", 
        placeholder="host:port:user:pass OR user:pass@host:port",
        help="Paste your proxies here. The app will automatically clean the format."
    )
    
    proxy_list = [p.strip() for p in proxies_raw.split("\n") if p.strip()] if use_proxies else None
    debug_mode = st.sidebar.checkbox("Enable Debug Mode", value=True)
    
    if debug_mode:
        st.sidebar.subheader("Terminal Output")
        log_text = "\n".join(st.session_state.debug_logs)
        st.sidebar.markdown(f'<div class="debug-log">{log_text}</div>', unsafe_allow_html=True)
        if st.sidebar.button("Clear History"):
            st.session_state.debug_logs = []
            st.rerun()

    st.title("🚀 Dubizzle Arbitrage Dashboard")
    
    if st.button("🔍 Scan Live Market", use_container_width=True):
        if not st.session_state.get('browser_installed'):
            st.error("Wait for browser setup to complete.")
            return

        with st.spinner("Scanning..."):
            df_raw, screenshot, html_snippet, status, p_used = asyncio.run(scrape_dubizzle(category, debug_mode, proxy_list))
            
            if debug_mode:
                with st.expander("🛠️ Debug Information"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"**HTTP Status:** {status}")
                        if p_used: st.write(f"**Used Proxy:** {p_used['server']}")
                        if screenshot: st.image(screenshot, caption="Last Scanned View")
                    with c2:
                        st.code(html_snippet, language="html")

            if not df_raw.empty:
                df = calculate_arbitrage(df_raw)
                deals = df[df['ROI_%'] >= roi_threshold].sort_values(by='ROI_%', ascending=False)
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Scanned", len(df))
                m2.metric("Hot Deals", len(deals))
                m3.metric("Median Price", f"AED {df['Market_Median'].iloc[0]:,.0f}")
                
                st.plotly_chart(px.histogram(df, x="Price", title="Price Distribution"), use_container_width=True)
                
                st.subheader("🔥 Top Deals")
                for _, row in deals.iterrows():
                    with st.container():
                        cols = st.columns([3, 1, 1])
                        cols[0].markdown(f"**{row['Title']}**\n\n📍 {row['Location']}")
                        cols[1].markdown(f"💰 **AED {row['Price']:,}**\n\n**ROI: {row['ROI_%']:.1f}%**")
                        cols[2].link_button("View Ad", row['Link'], use_container_width=True)
                        st.divider()
            else:
                st.error("No items found.")
                if status == 407:
                    st.warning("Authentication failed. Check your proxy list format.")

if __name__ == "__main__":
    main()