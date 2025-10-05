import random
import os
import html
import re
import sqlite3
import urllib.parse

import pandas as pd
import folium
import requests
import altair as alt
import streamlit as st
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
from xml.etree import ElementTree

# -----------------------
# Layout
# -----------------------
st.set_page_config(page_title="Wegovy Sampark — Streamlit Prototype", layout="wide")
st.title("Wegovy Sampark — Streamlit Prototype")

# -----------------------
# Helper content
# -----------------------
FAQS = { ... }  # same as your dict
RECIPES = [ ... ]  # same as your list
DOCTOR_CONTACT = "👩‍⚕️ Connect to an expert: https://example.com/connect-doctor"

# -----------------------
# Helper functions
# -----------------------
def calculate_bmi(height_cm, weight_kg):
    try:
        h_m = float(height_cm)/100
        bmi = weight_kg/(h_m**2)
        if bmi<18.5: cat="Underweight"
        elif bmi<25: cat="Normal"
        elif bmi<30: cat="Overweight"
        else: cat="Obese"
        return round(bmi,1), cat
    except: return None, None

def avatar_for(name): return ["🟢","🔵","🟣","🟡","🔴","🟠","🟤"][hash(name) % 7]

_REL_MAP = {"brother":"Sibling","sister":"Sibling","sibling":"Sibling",
            "mom":"Parent","mother":"Parent","mum":"Parent",
            "dad":"Parent","father":"Parent",
            "husband":"Spouse","wife":"Spouse","spouse":"Spouse",
            "friend":"Friend","buddy":"Friend"}

def normalize_relation(raw:str) -> str:
    if not raw: return "Other"
    key = re.sub(r'[^a-zA-Z]','',raw).lower().strip()
    return _REL_MAP.get(key, raw.strip().title() if raw.strip().title() in ["Spouse","Parent","Sibling","Friend"] else "Other")

def make_progress_bar(checkins,total=12):
    filled = int((checkins/total)*10); filled = max(0,min(10,filled))
    return "▰"*filled + "▱"*(10-filled)

# -----------------------
# Session state
# -----------------------
if "chat_history" not in st.session_state: st.session_state.chat_history = [{"from":"bot","text":"✅ Product verified: Wegovy is authentic!"}]
if "user_profile" not in st.session_state:
    st.session_state.user_profile = {"name":None,"age":None,"height":None,"weight":None,
                                     "bmi":None,"bmi_cat":None,"city":None,
                                     "family_member":None,"pending_family_name":None,
                                     "checkins":0,"points":0,"cashback_unlocked":False,
                                     "state":"new","msg_count":0}
if "care_partners" not in st.session_state: st.session_state.care_partners=[]
if "community" not in st.session_state:
    st.session_state.community=[
        {"anon":"User_α","adherence": random.randint(60,100)},
        {"anon":"User_β","adherence": random.randint(40,95)},
        {"anon":"User_γ","adherence": random.randint(20,90)},
        {"anon":"You","adherence": 0}
    ]

profile = st.session_state.user_profile

# -----------------------
# Sidebar
# -----------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio("Pages",["Onboarding Chat","Menu (once ready)","Family Stack","Pharmacy Locator","Commit & Earn","Knowledge Hub","Community Leaderboard"])
st.sidebar.markdown("---")
st.sidebar.subheader("💰 Wallet Summary")
st.sidebar.metric("Adherence Points",profile["points"])
st.sidebar.metric("Weeks Checked-in",profile["checkins"])
if profile["cashback_unlocked"]: st.sidebar.success("₹500 Cashback unlocked 🎉")
else: st.sidebar.info("Complete ≥90% adherence to unlock ₹500")

# -----------------------
# Onboarding Chat
# -----------------------
if page=="Onboarding Chat":
    st.subheader("WhatsApp-style Onboarding")
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    for m in st.session_state.chat_history:
        safe_text = html.escape(m["text"])
        cls = "msg-bot" if m["from"]=="bot" else "msg-user"
        st.markdown(f'<div class="{cls}">{safe_text}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    if "input_temp" not in st.session_state: st.session_state.input_temp=""
    
    def send_message():
        msg = st.session_state.input_temp.strip()
        if not msg: return
        st.session_state.chat_history.append({"from":"user","text":msg})
        profile["msg_count"] += 1
        reply=""
        # --- state machine ---
        if profile["state"]=="new": profile["state"]="awaiting_name"; reply="What’s your *name*?"
        elif profile["state"]=="awaiting_name": profile["name"]=msg.title(); profile["state"]="awaiting_age"; reply=f"Hi {profile['name']}! 🎉 How old are you?"
        elif profile["state"]=="awaiting_age":
            try: profile["age"]=int(msg); profile["state"]="awaiting_height"; reply="Got it! Height in cm?"
            except: reply="Enter a valid age."
        elif profile["state"]=="awaiting_height":
            try: profile["height"]=float(msg); profile["state"]="awaiting_weight"; reply="Weight in kg?"
            except: reply="Enter a valid height."
        elif profile["state"]=="awaiting_weight":
            try:
                profile["weight"]=float(msg)
                profile["bmi"],profile["bmi_cat"]=calculate_bmi(profile["height"],profile["weight"])
                profile["state"]="awaiting_city"; reply=f"✅ BMI {profile['bmi']} ({profile['bmi_cat']}). Which city?"
            except: reply="Enter a valid weight."
        elif profile["state"]=="awaiting_city":
            profile["city"]=msg.title(); profile["state"]="awaiting_family_name"; reply="Family member name?"
        elif profile["state"]=="awaiting_family_name":
            profile["pending_family_name"]=msg.strip().title(); profile["state"]="awaiting_family_relation"; reply="Relation?"
        elif profile["state"]=="awaiting_family_relation":
            fam_name = profile.get("pending_family_name","Unknown")
            fam_relation = normalize_relation(msg)
            profile["family_member"]=f"{fam_name} ({fam_relation})"; profile["state"]="ready"
            st.session_state.care_partners.append({"name":fam_name,"relation":fam_relation})
            reply=f"📨 Added: {fam_name} ({fam_relation}) ❤️"
        else: reply="✅ Onboarding complete!"
        st.session_state.chat_history.append({"from":"bot","text":reply})
        st.session_state.input_temp=""

    st.text_input("Type here:", key="input_temp", on_change=send_message)
    st.button("Send", on_click=send_message)

# -----------------------
# Menu (ready)
# -----------------------
elif page=="Menu (once ready)":
    if profile["state"]!="ready": st.warning("⚠️ Complete onboarding first.")
    else:
        st.subheader(f"Welcome, {profile['name']} 👋")
        choice = st.radio("Choose:",["Onboarding Video","Side-effect Tips","Weekly Check-in","Recipe","Ask a Question","Doctor Contact"])
        if choice=="Onboarding Video": st.video("https://www.w3schools.com/html/mov_bbb.mp4")
        elif choice=="Side-effect Tips": st.info(FAQS["side effects"])
        elif choice=="Weekly Check-in":
            profile["checkins"]=min(profile["checkins"]+1,12); profile["points"]=profile["checkins"]*10
            if profile["checkins"]/12>=0.9: profile["cashback_unlocked"]=True
            st.success(f"✅ Checked-in {profile['checkins']}/12 weeks"); st.progress(profile["checkins"]/12)
        elif choice=="Recipe": st.write(random.choice(RECIPES))
        elif choice=="Ask a Question":
            q = st.text_input("Ask about Wegovy:").strip().lower()
            if q: ans = next((FAQS[k] for k in FAQS if k in q), "🤔 Sorry, I don’t have an answer yet."); st.info(ans)
        elif choice=="Doctor Contact": st.info(DOCTOR_CONTACT)

# -----------------------
# Family Stack
# -----------------------
elif page=="Family Stack":
    st.subheader("Family Stack — Care Partners")
    with st.form("manual_add", clear_on_submit=True):
        name = st.text_input("Name", key="manual_name")
        rel = st.selectbox("Relation", ["Spouse","Parent","Sibling","Friend","Other"], key="manual_rel")
        if st.form_submit_button("Invite"):
            if name.strip():
                st.session_state.care_partners.append({"name":name.strip().title(),"relation":normalize_relation(rel)})
                st.success(f"Invited {name.title()}")
            else: st.warning("Enter a name.")
    st.markdown("### Current Care Partners")
    for idx, cp in enumerate(st.session_state.care_partners):
        st.write(f"**{cp['name']}** — {cp['relation']}")

# -----------------------
# Pharmacy Locator
# -----------------------
elif page=="Pharmacy Locator":
    st.subheader("💊 Pharmacy Locator")
    if not profile.get("city"): st.warning("Enter your city first.")
    elif profile["city"].lower() in ["bangalore","bengaluru"]:
        try: df=pd.read_csv("pharmacies_with_dosages.csv")
        except: st.error("pharmacies_with_dosages.csv missing"); df=None
        if df is not None:
            st.dataframe(df)
            m = folium.Map(location=[12.9716,77.5946], zoom_start=12)
            for _,r in df.iterrows():
                folium.Marker([r['Latitude'],r['Longitude']],tooltip=f"{r['Name']} | {r['Type']} | {r.get('Dosages','')}",icon=folium.Icon(color="green" if r['Type']=="Offline" else "red")).add_to(m)
            st.components.v1.html(m._repr_html_(),height=500)
    else: st.info("Pharmacy locator currently only supports Bangalore.")

# -----------------------
# Commit & Earn
# -----------------------
elif page=="Commit & Earn":
    st.subheader("12-Week Challenge")
    weeks_total=12; new_checkins=0
    for i in range(1,weeks_total+1):
        if st.checkbox(f"Week {i}", value=i<=profile["checkins"]): new_checkins+=1
    profile["checkins"]=new_checkins; profile["points"]=profile["checkins"]*10
    if profile["checkins"]/weeks_total>=0.9: profile["cashback_unlocked"]=True
    st.metric("Adherence Points",profile["points"])
    st.metric("Weeks Checked-in",profile["checkins"])
    if profile["cashback_unlocked"]: st.success("🎉 Cashback unlocked: ₹500!")

# -----------------------
# Knowledge Hub
# -----------------------
elif page=="Knowledge Hub":
    st.subheader("🩺 Knowledge Hub")
    if st
