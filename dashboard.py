import streamlit as st
import sqlite3
import pandas as pd
import altair as alt
from streamlit_autorefresh import st_autorefresh



# st.set_page_config() must be the very first Streamlit command.
st.set_page_config(page_title="Wegovy Sampark Dashboard", layout="wide")

DB = "sampark.db"

def calculate_bmi(height, weight):
    try:
        h_m = height / 100
        bmi = weight / (h_m**2)
        if bmi < 18.5:
            category = "Underweight"
        elif bmi < 25:
            category = "Normal"
        elif bmi < 30:
            category = "Overweight"
        else:
            category = "Obese"
        return round(bmi, 1), category
    except:
        return None, None

def make_progress_bar(checkins, total=12):
    filled = int((checkins / total) * 10) if total > 0 else 0
    filled = max(0, min(10, filled))
    return "▰" * filled + "▱" * (10 - filled)

st.title("📊 Wegovy Sampark Dashboard")

# Autorefresh every 5s so judges see live updates
st_autorefresh(interval=5000, key="dashboard_refresh")

# Read DB
conn = sqlite3.connect(DB)
df = pd.read_sql("SELECT * FROM users", conn)
conn.close()

if df.empty:
    st.info("⚠️ No patients yet. Interact with the WhatsApp bot first.")
else:
    # Clamp checkins at 12 for display
    df["checkins"] = df["checkins"].clip(upper=12)

    # Compute BMI
    df["BMI"], df["BMI Category"] = zip(*df.apply(
        lambda row: calculate_bmi(row["height"], row["weight"]) if (row["height"] and row["weight"]) else (None, None),
        axis=1
    ))

    df["Adherence Progress"] = df["checkins"].apply(lambda x: make_progress_bar(x))

    # Mask phone numbers → only last 3 digits visible
    df["phone_masked"] = df["phone"].apply(lambda x: f"*******{x[-3:]}" if x else "—")

    df_display = df[["phone_masked", "name", "age", "height", "weight",
                     "BMI", "BMI Category", "family_member", "checkins", "Adherence Progress"]].fillna("—")

    st.subheader("Live Patients")
    st.dataframe(df_display, use_container_width=True)

    st.markdown("---")
    st.subheader("📈 Summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Patients", len(df))
    avg_bmi = df["BMI"].dropna().mean()
    col2.metric("Average BMI", f"{avg_bmi:.1f}" if not pd.isna(avg_bmi) else "—")
    col3.metric("Avg Check-ins", f"{df['checkins'].mean():.1f}")

    st.markdown("---")
    st.subheader("BMI Distribution")
    bmi_df = df.dropna(subset=["BMI"])
    if not bmi_df.empty:
        hist = alt.Chart(bmi_df).mark_bar().encode(
            alt.X("BMI:Q", bin=alt.Bin(maxbins=12), title="BMI"),
            alt.Y("count()", title="Patients"),
            color=alt.Color("BMI Category:N", title="Category")
        )
        st.altair_chart(hist, use_container_width=True)
    else:
        st.info("No BMI data yet.")

    st.markdown("---")
    st.subheader("Adherence Breakdown")
    checkins_chart = alt.Chart(df).mark_bar().encode(
            x=alt.X("name:N", sort="-y", title="Patient"),
            y=alt.Y("checkins:Q", title="Check-ins"),
            tooltip=["name", "checkins"]
    )
    st.altair_chart(checkins_chart, use_container_width=True)
