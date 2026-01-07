import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from scipy import stats
import time
import random

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

# --- MOCK DATA GENERATOR (Simulating Scraper Engine) ---
# In a production environment, this function would call Playwright/BS4
def get_mock_dubizzle_data(category):
    models = {
        "iPhone": ["iPhone 15 Pro", "iPhone 15 Pro Max", "iPhone 14", "iPhone 13"],
        "Luxury Watches": ["Rolex Submariner", "Omega Speedmaster", "Tag Heuer Carrera"],
        "Gaming": ["PS5 Console", "Xbox Series X", "Gaming PC RTX 4080"]
    }
    
    current_models = models.get(category, ["Generic Item"])
    data = []
    
    # Establish a "True Market Value" for simulations
    market_bases = {
        "iPhone 15 Pro": 3200, "iPhone 15 Pro Max": 3800, "iPhone 14": 2000, 
        "Rolex Submariner": 45000, "Omega Speedmaster": 18000,
        "PS5 Console": 1600, "Gaming PC RTX 4080": 7500
    }

    for _ in range(30):
        item_name = random.choice(current_models)
        base = market_bases.get(item_name, 1000)
        # Create a range of prices (some high, some low, most near base)
        price = int(np.random.normal(base, base * 0.15))
        
        data.append({
            "Title": f"{item_name} - {'Excellent' if price > base else 'Urgent Sale'}",
            "Model": item_name,
            "Price": max(price, 100), # Min price 100
            "Location": random.choice(["Dubai Marina", "Business Bay", "Deira", "JLT", "Abu Dhabi"]),
            "Link": "https://uae.dubizzle.com/search/"
        })
    return pd.DataFrame(data)

# --- ARBITRAGE ENGINE ---
def calculate_arbitrage(df):
    if df.empty:
        return df
    
    # Calculate Market Median per Model (more robust than mean)
    market_stats = df.groupby('Model')['Price'].transform('median')
    df['Market_Median'] = market_stats
    
    # Calculate Standard Deviation to find Z-Score (Anomalies)
    # If only one item, std is 0. Handle edge cases.
    std_stats = df.groupby('Model')['Price'].transform('std').fillna(1)
    df['Z_Score'] = (df['Price'] - df['Market_Median']) / std_stats
    
    # ROI Calculation: Potential Profit if sold at Market Median
    df['Profit_AED'] = df['Market_Median'] - df['Price']
    df['ROI_%'] = (df['Profit_AED'] / df['Price']) * 100
    
    return df

# --- UI COMPONENTS ---
def sidebar():
    st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/6/69/Dubizzle_logo.svg/1200px-Dubizzle_logo.svg.png", width=150)
    st.sidebar.title("Search Parameters")
    cat = st.sidebar.selectbox("Category", ["iPhone", "Luxury Watches", "Gaming"])
    roi_threshold = st.sidebar.slider("Min ROI %", 0, 50, 15)
    max_price = st.sidebar.number_input("Max Budget (AED)", value=50000)
    return cat, roi_threshold, max_price

def main():
    cat, roi_threshold, max_price = sidebar()
    
    st.title(f"🔍 Dubizzle Arbitrage: {cat}")
    st.caption("Scanning live listings for statistical price anomalies...")

    # Fetch and Process Data
    with st.spinner('Calculating market spreads...'):
        # In real app: df = scrape_dubizzle(cat)
        raw_df = get_mock_dubizzle_data(cat)
        df = calculate_arbitrage(raw_df)

    # Filter by user preferences
    deals = df[(df['ROI_%'] >= roi_threshold) & (df['Price'] <= max_price)].sort_values(by='ROI_%', ascending=False)

    # Metrics Row
    m1, m2, m3 = st.columns(3)
    m1.metric("Scanned Items", len(df))
    m2.metric("Hot Deals Found", len(deals))
    m3.metric("Avg. Potential ROI", f"{df['ROI_%'].mean():.1f}%")

    # Visualizations
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        st.subheader("📊 Market Price Distribution")
        fig = px.box(df, x="Model", y="Price", color="Model", points="all", 
                     title="Price Spreads (Look for outliers below the boxes)")
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("💡 Arbitrage Insight")
        st.write("""
            **The Z-Score Strategy:**
            Items with a **Z-Score < -1.5** are priced significantly lower than their peers. 
            Check for damage or missing accessories, then secure the flip!
        """)
        # Show Top ROI Table
        st.dataframe(deals[['Title', 'Price', 'ROI_%']].head(5), hide_index=True)

    # Deal Display
    st.divider()
    st.subheader("🔥 Live Opportunities")
    
    if deals.empty:
        st.info("No deals matching your ROI threshold found. Try lowering the threshold or changing categories.")
    else:
        for _, row in deals.iterrows():
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                with c1:
                    st.markdown(f"**{row['Title']}**")
                    st.caption(f"📍 {row['Location']}")
                with c2:
                    st.markdown(f"💰 **AED {row['Price']:,}**")
                    st.caption(f"Mkt: AED {row['Market_Median']:,}")
                with c3:
                    color = "green" if row['ROI_%'] > 20 else "orange"
                    st.markdown(f"📈 <span style='color:{color}'>**{row['ROI_%']:.1f}% ROI**</span>", unsafe_allow_html=True)
                    st.caption(f"+AED {row['Profit_AED']:,} Profit")
                with c4:
                    st.link_button("View Ad", row['Link'], type="primary")
                st.markdown("<hr style='margin: 10px 0; border:0; border-top:1px solid #eee;'>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()