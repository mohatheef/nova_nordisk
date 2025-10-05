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
# Helper content
# -----------------------
FAQS = {
    "side effects": "🤒 Common side effects: nausea, vomiting, constipation. Ginger tea + small meals help.",
    "storage": "🧊 Store in fridge (2-8°C). Do not freeze.",
    "dose timing": "🕒 Morning or night — keep your schedule consistent.",
    "missed dose": "💉 If <5 days late: take when you remember. If >5 days: skip and continue your normal schedule.",
    "reduce nausea": "🍵 Ginger tea, small frequent meals, avoid greasy food, stay hydrated.",
    "weight loss": "📊 Usually between 4–8 weeks, varies by patient.",
    "exercise": "🏃 Yes — combine diet + exercise for best results.",
    "contraindications": "⚠️ Avoid if thyroid cancer history or MEN2 syndrome. Consult doctor.",
    "price": "💰 Price varies by pharmacy.",
    "alcohol": "🍷 Light alcohol is usually safe, but avoid if it worsens nausea."
}

RECIPES = [
    "🥗 Cucumber & tomato salad with lemon — light and filling.",
    "🍲 Lentil & veggie soup — protein-rich and gentle on the stomach.",
    "🥣 Overnight oats with chia — easy digestion & sustained energy."
]

DOCTOR_CONTACT = "👩‍⚕️ Connect to an expert: https://example.com/connect-doctor"

# -----------------------
# Helpers
# -----------------------
def calculate_bmi(height_cm, weight_kg):
    try:
        h_m = float(height_cm) / 100
        bmi = weight_kg / (h_m ** 2)
        if bmi < 18.5: cat = "Underweight"
        elif bmi < 25: cat = "Normal"
        elif bmi < 30: cat = "Overweight"
        else: cat = "Obese"
        return round(bmi, 1), cat
    except:
        return None, None

def avatar_for(name):
    emojis = ["🟢","🔵","🟣","🟡","🔴","🟠","🟤"]
    return emojis[hash(name) % len(emojis)]

_REL_MAP = {
    "brother": "Sibling", "sister": "Sibling", "sibling": "Sibling",
    "mom": "Parent", "mother": "Parent", "mum": "Parent",
    "dad": "Parent", "father": "Parent",
    "husband": "Spouse", "wife": "Spouse", "spouse": "Spouse",
    "friend": "Friend", "buddy": "Friend"
}
_STOPWORDS = {"as", "is", "my", "the", "a", "an", "named"}

def normalize_relation(raw: str) -> str:
    if not raw: return "Other"
    key = re.sub(r'[^a-zA-Z]', '', raw).lower().strip()
    if key in _REL_MAP: return _REL_MAP[key]
    title = raw.strip().title()
    if title in ["Spouse", "Parent", "Sibling", "Friend"]: return title
    return "Other"

# -----------------------
# Session state initialization
# -----------------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        {"from":"bot", "text":"✅ Product verified: Wegovy is authentic! Let’s get started."}
    ]

if "user_profile" not in st.session_state:
    st.session_state.user_profile = {
        "name": None, "age": None, "height": None, "weight": None,
        "bmi": None, "bmi_cat": None, "city": None,
        "family_member": None, "pending_family_name": None,
        "checkins": 0, "points": 0, "cashback_unlocked": False,
        "state": "new", "msg_count": 0
    }

if "care_partners" not in st.session_state:
    st.session_state.care_partners = []

if "community" not in st.session_state:
    st.session_state.community = [
        {"anon":"User_α","adherence": random.randint(60,100)},
        {"anon":"User_β","adherence": random.randint(40,95)},
        {"anon":"User_γ","adherence": random.randint(20,90)},
        {"anon":"You","adherence": 0}
    ]

profile = st.session_state.user_profile

# -----------------------
# Layout
# -----------------------
st.set_page_config(page_title="Wegovy Sampark — Streamlit Prototype", layout="wide")
st.title("Wegovy Sampark — Streamlit Prototype")

st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Pages",
    ["Onboarding Chat", "Menu (once ready)", "Family Stack",
     "Pharmacy Locator", "Commit & Earn", "Knowledge Hub", "Community Leaderboard"]
)

# Wallet summary always visible
st.sidebar.markdown("---")
st.sidebar.subheader("💰 Wallet Summary")
st.sidebar.metric("Adherence Points", profile["points"])
st.sidebar.metric("Weeks Checked-in", profile["checkins"])
if profile["cashback_unlocked"]:
    st.sidebar.success("₹500 Cashback unlocked 🎉")
else:
    st.sidebar.info("Complete ≥90% adherence to unlock ₹500")

# -----------------------
# Onboarding Chat (UPDATED: family name & relation separate)
# -----------------------
if page == "Onboarding Chat":
    st.subheader("WhatsApp-style Onboarding")
    st.markdown("""
    <style>
    .chat-container { border:1px solid #ddd; border-radius:12px; padding:12px; background:#f9f9f9; }
    .msg-bot { display:inline-block; background:#ffffff; color:#000; padding:8px 12px; margin:6px 0; border-radius:12px; border:1px solid #eee; max-width:70%; }
    .msg-user { display:inline-block; background:#25D366; color:white; padding:8px 12px; margin:6px 0; border-radius:12px; margin-left:auto; text-align:right; max-width:70%; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    for m in st.session_state.chat_history:
        safe_text = html.escape(m["text"])
        if m["from"] == "bot": 
            st.markdown(f'<div class="msg-bot">{safe_text}</div>', unsafe_allow_html=True)
        else: 
            st.markdown(f'<div class="msg-user">{safe_text}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if "input_temp" not in st.session_state:
        st.session_state.input_temp = ""

    def send_message():
        msg = st.session_state.input_temp.strip()
        if not msg:
            st.session_state.input_temp = ""
            return

        st.session_state.chat_history.append({"from": "user", "text": msg})
        profile["msg_count"] += 1
        reply = ""

        if profile["state"] == "new":
            profile["state"] = "awaiting_name"
            reply = "What’s your *name*?"

        elif profile["state"] == "awaiting_name":
            profile["name"] = msg.title()
            profile["state"] = "awaiting_age"
            reply = f"Hi {profile['name']}! 🎉 How old are you?"

        elif profile["state"] == "awaiting_age":
            try:
                profile["age"] = int(msg)
                profile["state"] = "awaiting_height"
                reply = "Got it! What is your *height* in cm?"
            except:
                reply = "Please enter a valid number for age (e.g., 34)."

        elif profile["state"] == "awaiting_height":
            try:
                profile["height"] = float(msg)
                profile["state"] = "awaiting_weight"
                reply = "Great! Now tell me your *weight* in kg."
            except:
                reply = "Please enter a valid height in cm (e.g., 172)."

        elif profile["state"] == "awaiting_weight":
            try:
                profile["weight"] = float(msg)
                profile["bmi"], profile["bmi_cat"] = calculate_bmi(profile["height"], profile["weight"])
                profile["state"] = "awaiting_city"
                reply = f"✅ Saved! Your BMI is {profile['bmi']} ({profile['bmi_cat']}).\nWhich city are you from?"
            except:
                reply = "Please enter a valid weight in kg."

        elif profile["state"] == "awaiting_city":
            profile["city"] = msg.title()
            profile["state"] = "awaiting_family_name"
            reply = f"Got it! You’re from {profile['city']} 🌆.\nPlease tell me your family member’s *name*."

        elif profile["state"] == "awaiting_family_name":
            profile["pending_family_name"] = msg.strip().title()
            profile["state"] = "awaiting_family_relation"
            reply = f"👍 Saved {profile['pending_family_name']}. Now, what’s their *relation* to you? (e.g., Brother, Mother, Friend)"

        elif profile["state"] == "awaiting_family_relation":
            fam_name = profile.get("pending_family_name", "Unknown")
            fam_relation_norm = normalize_relation(msg)
            profile["family_member"] = f"{fam_name} ({fam_relation_norm})"
            profile["state"] = "ready"

            st.session_state.care_partners.append({
                "name": fam_name,
                "relation": fam_relation_norm
            })

            reply = f"📨 Family member added: {fam_name} ({fam_relation_norm}) ❤️\nNow you can use the Menu page!"

        else:
            reply = "👍 You're already onboarded! Go to the *Menu (once ready)* page."

        st.session_state.chat_history.append({"from": "bot", "text": reply})
        st.session_state.input_temp = ""

    st.text_input("Type your reply here:", key="input_temp", on_change=send_message)
    if st.button("Send"):
        send_message()

# -----------------------
# Menu
# -----------------------
elif page == "Menu (once ready)":
    if profile["state"] != "ready": st.warning("⚠️ Complete onboarding in the *Onboarding Chat* page first.")
    else:
        st.subheader(f"Welcome, {profile['name']} 👋")
        menu_choice = st.radio("Choose an option:", ["Onboarding Video", "Side-effect Tips", "Weekly Check-in", "Recipe", "Ask a Question", "Doctor Contact"])
        if menu_choice == "Onboarding Video":
            video_path = "onboarding.mp4"
            if os.path.exists(video_path): st.video(video_path)
            else: st.warning("Onboarding video not found — showing sample instead."); st.video("https://www.w3schools.com/html/mov_bbb.mp4")
        elif menu_choice == "Side-effect Tips": st.info(FAQS["side effects"])
        elif menu_choice == "Weekly Check-in":
            profile["checkins"] = min(profile["checkins"]+1, 12); profile["points"] = profile["checkins"] * 10
            done = profile["checkins"]; st.success(f"✅ Check-in recorded! Progress: {done}/12 weeks"); st.progress(min(done/12, 1.0))
            if done == 12: st.balloons(); st.info("🎉 Challenge complete!")
            if (done/12) >= 0.9: profile["cashback_unlocked"] = True
            pct = int((profile["checkins"]/12)*100)
            for c in st.session_state.community:
                if c["anon"] == "You": c["adherence"] = pct
        elif menu_choice == "Recipe": st.write(random.choice(RECIPES))
        elif menu_choice == "Ask a Question":
            if "ask_q" not in st.session_state: st.session_state.ask_q = ""
            if "last_answer" not in st.session_state: st.session_state.last_answer = ""
            def handle_question():
                q = st.session_state.ask_q.strip().lower()
                ans = next((FAQS[k] for k in FAQS if k in q), None)
                st.session_state.last_answer = str(ans) if ans else "🤔 Sorry, I don’t have an answer for that yet."
            st.text_input("Ask me about Wegovy (e.g., 'side effects', 'storage')", key="ask_q", on_change=handle_question)
            if st.session_state.last_answer:
                if "Sorry" in st.session_state.last_answer: st.warning(st.session_state.last_answer)
                else: st.success(st.session_state.last_answer)
        elif menu_choice == "Doctor Contact": st.info(DOCTOR_CONTACT)

# -----------------------
# Family Stack
# -----------------------
elif page == "Family Stack":
    st.subheader("Family Stack — Manage Care Partners")
    with st.form("manual_add", clear_on_submit=True):
        name = st.text_input("Care partner name", key="manual_name")
        relation_select = st.selectbox("Relation", ["Spouse","Parent","Sibling","Friend","Other"], key="manual_rel")
        submitted = st.form_submit_button("Invite (simulate)")
        if submitted:
            if name.strip():
                rel_norm = normalize_relation(relation_select)
                st.session_state.care_partners.append({"name": name.strip().title(), "relation": rel_norm})
                st.success(f"Invited {name.strip().title()} ({rel_norm}).")
            else: st.warning("Enter a name.")
    st.markdown("### Current Care Partners")
    if not st.session_state.care_partners: st.info("No care partners yet.")
    else:
        for idx, cp in enumerate(st.session_state.care_partners):
            cols = st.columns([4,1,1])
            with cols[0]: st.markdown(f"**{cp['name']}** — {cp['relation']}")
            with cols[1]:
                if st.button(f"✏️ Edit {idx}", key=f"edit_btn_{idx}"): st.session_state[f"editing_{idx}"] = True
            with cols[2]:
                if st.button(f"🗑️ Remove {idx}", key=f"remove_btn_{idx}"): st.session_state.care_partners.pop(idx); st.experimental_rerun()
            if st.session_state.get(f"editing_{idx}", False):
                with st.form(f"edit_form_{idx}", clear_on_submit=False):
                    new_name = st.text_input("Name", value=cp["name"], key=f"edit_name_{idx}")
                    new_rel = st.selectbox("Relation", ["Spouse","Parent","Sibling","Friend","Other"], index=["Spouse","Parent","Sibling","Friend","Other"].index(cp["relation"]) if cp["relation"] in ["Spouse","Parent","Sibling","Friend","Other"] else 4, key=f"edit_rel_{idx}")
                    save = st.form_submit_button("Save"); cancel = st.form_submit_button("Cancel")
                    if save: st.session_state.care_partners[idx] = {"name": new_name.strip().title(), "relation": normalize_relation(new_rel)}; st.session_state[f"editing_{idx}"] = False; st.experimental_rerun()
                    if cancel: st.session_state[f"editing_{idx}"] = False; st.experimental_rerun()

# -----------------------
# Pharmacy Locator (with city alias mapping)
# -----------------------
elif page == "Pharmacy Locator":
    st.subheader("💊 Pharmacy Locator")

    if not profile.get("city"):
        st.warning("⚠️ Please complete onboarding and enter your city first.")
    else:
        # ✅ Normalize user city with alias mapping
        city_aliases = {
            "bangalore": "bangalore",
            "bengaluru": "bangalore",
            "bombay": "mumbai",
            "madras": "chennai",
            "delhi": "delhi",
            "new delhi": "delhi"
        }

        user_city = profile["city"].lower().strip()
        normalized_city = city_aliases.get(user_city, user_city)

        st.markdown(f"### Showing pharmacy locations for **{profile['city']}**")

        if normalized_city == "bangalore":
            try:
                df = pd.read_csv("pharmacies_with_dosages.csv")  # Name, Type, Latitude, Longitude, Dosages
            except FileNotFoundError:
                st.error("⚠️ pharmacies_with_dosages.csv not found. Please upload it.")
                df = None

            if df is not None:
                st.dataframe(df)

                # Center map on Bangalore
                bangalore_coords = [12.9716, 77.5946]
                m = folium.Map(location=bangalore_coords, zoom_start=12)

                # Add markers
                for _, row in df.iterrows():
                    color = "green" if row['Type'] == "Offline" else "red"
                    dosage_info = row['Dosages'] if 'Dosages' in df.columns else "Not specified"
                    tooltip_text = f"{row['Name']} — {row['Type']} | Dosages: {dosage_info}"

                    folium.Marker(
                        [row['Latitude'], row['Longitude']],
                        tooltip=tooltip_text,
                        icon=folium.Icon(color=color, icon="info-sign")
                    ).add_to(m)

                # ✅ Render map as HTML iframe (bypasses JSON serialization error)
                map_html = m._repr_html_()
                st.components.v1.html(map_html, height=500)

        else:
            st.info(f"🌍 Pharmacy locator is currently available only for Bangalore. "
                    f"We can add support for **{profile['city']}** in the future.")
            
# -----------------------
# Commit & Earn
# -----------------------
elif page == "Commit & Earn":
    st.subheader("Commit & Earn — 12-Week Challenge")
    weeks_total = 12; new_checkins = 0
    for i in range(1, weeks_total+1):
        checked = st.checkbox(f"Week {i}", value=i <= profile["checkins"])
        if checked: new_checkins += 1
    profile["checkins"] = new_checkins; profile["points"] = profile["checkins"] * 10
    if (profile["checkins"]/weeks_total) >= 0.9: profile["cashback_unlocked"] = True
    pct = int((profile["checkins"]/weeks_total)*100)
    for c in st.session_state.community:
        if c["anon"] == "You": c["adherence"] = pct
    st.markdown("### Wallet Summary")
    st.metric("Adherence Points", profile["points"])
    st.metric("Weeks Checked-in", profile["checkins"])
    if profile["cashback_unlocked"]: st.success("🎉 Cashback unlocked: ₹500 will be credited!")
    else: st.info("Complete ≥90% adherence to unlock ₹500 cashback.")

# -----------------------
# Knowledge Hub
# -----------------------
elif page == "Knowledge Hub":
    st.subheader("🩺 Knowledge Hub - Wegovy (Novo Nordisk)")
    def fetch_pubmed(query="Wegovy AND Novo Nordisk AND obesity AND India", max_results=5):
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        search_url = f"{base_url}esearch.fcgi?db=pubmed&term={query}&retmax={max_results}&retmode=json"
        try: search_resp = requests.get(search_url, timeout=10).json()
        except (requests.exceptions.RequestException, ValueError): return []
        pmids = search_resp.get("esearchresult", {}).get("idlist", []); articles = []
        for pmid in pmids:
            try:
                fetch_url = f"{base_url}efetch.fcgi?db=pubmed&id={pmid}&retmode=xml"; fetch_resp = requests.get(fetch_url, timeout=10).text
                root = ElementTree.fromstring(fetch_resp)
                articles.append({"pmid": pmid, "title": root.findtext(".//ArticleTitle"), "abstract": root.findtext(".//AbstractText")})
            except Exception: continue
        return articles

    success_stories = [
        {"title": "Novo Nordisk announces Wegovy approval for obesity management","description": "Wegovy has been approved as a treatment for adults with obesity, showing significant efficacy in clinical trials.","url": "https://www.novonordisk.com/media/news-details.2337680.html","source": "Novo Nordisk News"},
        {"title": "Clinical trial results: Wegovy for weight management","description": "Phase 3 clinical trials demonstrate substantial weight loss in patients treated with Wegovy.","url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8463470/","source": "PubMed Central"},
        {"title": "Real-world outcomes with Wegovy","description": "Patients using Wegovy report positive weight management outcomes, supporting clinical trial results.","url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8569585/","source": "PubMed Central"}
    ]

    def fetch_clinical_trials(query="Wegovy Novo Nordisk", max_results=5):
        api_url = f"https://clinicaltrials.gov/api/query/study_fields?expr={urllib.parse.quote(query)}&fields=BriefTitle,Condition,OverallStatus,URL&min_rnk=1&max_rnk={max_results}&fmt=json"
        try: resp = requests.get(api_url, timeout=10); resp.raise_for_status(); data = resp.json()
        except (requests.exceptions.RequestException, ValueError): return []
        trials = []
        for study in data.get("StudyFieldsResponse", {}).get("StudyFields", []):
            trials.append({"title": study.get("BriefTitle", ["No title"])[0],"condition": study.get("Condition", [""])[0],"status": study.get("OverallStatus", [""])[0],"url": study.get("URL", [""])[0]})
        return trials

    if st.button("📥 Fetch Latest Articles & Trials"):
        st.header("📄 Research Articles")
        articles = fetch_pubmed()
        if not articles: st.warning("No PubMed articles found.")
        else:
            for art in articles:
                st.subheader(art['title'])
                st.write(art['abstract'] if art['abstract'] else "No abstract available")
                st.markdown(f"[Read on PubMed](https://pubmed.ncbi.nlm.nih.gov/{art['pmid']}/)")
                st.markdown("---")

        st.header("📰 Success Stories & News")
        for story in success_stories:
            st.subheader(story['title'])
            st.write(story['description'])
            st.markdown(f"[Read full story]({story['url']}) - Source: {story['source']}")
            st.markdown("---")

        st.header("🧪 NIH Clinical Trials")
        trials = fetch_clinical_trials()
        if not trials: st.warning("No clinical trials found.")
        else:
            for t in trials:
                st.subheader(t['title'])
                st.write(f"Condition: {t['condition']} | Status: {t['status']}")
                if t['url']: st.markdown(f"[View on ClinicalTrials.gov]({t['url']})")
                st.markdown("---")

        pubmed_search_url = "https://pubmed.ncbi.nlm.nih.gov/?term=" + urllib.parse.quote("Wegovy AND Novo Nordisk AND obesity AND India")
        st.markdown(f"🔍 [Explore more on PubMed]({pubmed_search_url})")

# -----------------------
# Community Leaderboard
# -----------------------
elif page == "Community Leaderboard":
    st.subheader("Community Sampark — Leaderboard (anonymous)")
    for c in st.session_state.community:
        if c["anon"] != "You": c["adherence"] = min(100, max(10, c["adherence"] + random.randint(-3,5)))
    sorted_comm = sorted(st.session_state.community, key=lambda x: x["adherence"], reverse=True)
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for rank, item in enumerate(sorted_comm, start=1):
        medal = medals.get(rank, ""); badge = avatar_for(item["anon"])
        st.markdown(f"**{rank}. {medal} {badge} {item['anon']}** — {item['adherence']}% adherence")
        st.progress(item["adherence"]/100)
    st.markdown("---")
    msg = st.text_area("Post a short encouragement")
    if st.button("Post encouragement"):
        st.success("Encouragement posted!") if msg.strip() else st.warning("Write something encouraging.")
