from flask import Flask, request, Response, send_from_directory
from twilio.twiml.messaging_response import MessagingResponse
import difflib
import sqlite3
import traceback
import random
import os
import requests
import urllib.parse
from xml.etree import ElementTree
import pandas as pd

# -------------------------------
# Flask app and database setup
# -------------------------------
app = Flask(__name__)
DB = "sampark.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            phone TEXT PRIMARY KEY,
            name TEXT,
            age INTEGER,
            height REAL,
            weight REAL,
            checkins INTEGER DEFAULT 0,
            family_member TEXT,
            state TEXT DEFAULT 'new',
            msg_count INTEGER DEFAULT 0,
            city TEXT,
            fam_name TEXT,
            fam_relation TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# -------------------------------
# FAQ, Recipes, and Tips
# -------------------------------
FAQS = {
    "what are side effects": "🤒 Common side effects: nausea, vomiting, constipation. Ginger tea + small meals help.\n(Type 'doctor' to connect to our experts)",
    "how to store wegovy": "🧊 Store in fridge (2-8°C). Do not freeze.",
    "can i take it at night": "🕒 Yes, morning or night — keep your schedule consistent.",
    "what to do if i miss a dose": "💉 If <5 days late: take as soon as you remember. If >5 days: skip and continue your normal schedule.",
    "how to reduce nausea": "🍵 Ginger tea, small frequent meals, avoid greasy food, stay hydrated.",
    "when will i see weight loss": "📊 Usually between 4–8 weeks, varies by patient.",
    "can i exercise": "🏃 Yes — combine diet + exercise for best results.",
    "who should not take wegovy": "⚠️ Those with thyroid cancer history or MEN2 syndrome should avoid. Consult doctor.",
    "what is the price": "💰 Price varies by pharmacy. Type 'doctor' to ask clinical or cost queries.",
    "can i drink alcohol": "🍷 Light alcohol is usually safe, but avoid if it worsens nausea."
}

RECIPES = [
    "🥗 Quick recipe: Cucumber & tomato salad with lemon and olive oil — light and filling.",
    "🍲 Lentil & veggie soup: protein-rich and gentle on the stomach.",
    "🥣 Overnight oats with chia: easy digestion & sustained energy."
]

HYDRATION_TIPS = [
    "💧 Tip: sip water throughout the day — small, frequent sips reduce nausea.",
    "🥤 Try an electrolyte drink if you feel light-headed after injections."
]

DOCTOR_CONTACT = "👩‍⚕️ Connect to an expert here: https://example.com/connect-doctor"

# -------------------------------
# Helper Functions
# -------------------------------
def find_answer(user_text):
    user_text = user_text.lower()
    matches = difflib.get_close_matches(user_text, FAQS.keys(), n=1, cutoff=0.4)
    return FAQS[matches[0]] if matches else None

def make_progress_bar(current, total=12):
    current = min(current, total)
    filled = int((current / total) * 10) if total > 0 else 0
    return "▰" * filled + "▱" * (10 - filled)

def calculate_bmi(height_cm, weight_kg):
    try:
        h_m = float(height_cm) / 100.0
        bmi = float(weight_kg) / (h_m ** 2)
        if bmi < 18.5: category = "Underweight"
        elif bmi < 25: category = "Normal"
        elif bmi < 30: category = "Overweight"
        else: category = "Obese"
        return round(bmi, 1), category
    except:
        return None, None

def safe_db_fetch(phone):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (phone, state, checkins, msg_count) VALUES (?, 'new', 0, 0)", (phone,))
    conn.commit()
    c.execute("SELECT name, age, height, weight, checkins, family_member, state, msg_count, city, fam_name, fam_relation FROM users WHERE phone=?", (phone,))
    row = c.fetchone()
    conn.close()
    return row

def update_field(phone, field, value):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(f"UPDATE users SET {field}=? WHERE phone=?", (value, phone))
    conn.commit()
    conn.close()

# -------------------------------
# City Normalization
# -------------------------------
CITY_MAP = {
    "bengaluru": "Bangalore",
    "bangalore": "Bangalore",
    "bombay": "Mumbai",
    "mumbai": "Mumbai",
    "madras": "Chennai",
    "chennai": "Chennai",
    "delhi": "Delhi",
    "new delhi": "Delhi"
}

def normalize_city(city: str):
    if not city:
        return None
    city_norm = city.lower().strip()
    return CITY_MAP.get(city_norm, city.title())

# -------------------------------
# Pharmacy Locator
# -------------------------------
def pharmacy_locator(city):
    if not city:
        return "⚠️ City not set. Please complete onboarding."
    city_std = normalize_city(city)
    if city_std == "Bangalore":
        try:
            df = pd.read_csv("pharmacies_with_dosages.csv")
        except FileNotFoundError:
            return "⚠️ Pharmacy data not available. Please upload pharmacies_with_dosages.csv"
        results = []
        for _, row in df.iterrows():
            results.append(f"{row['Name']} ({row['Type']}) — Dosages: {row.get('Dosages','N/A')}")
        return "💊 Pharmacies in Bangalore:\n" + "\n".join(results[:5])
    else:
        return f"🌍 Pharmacy locator is currently available only for Bangalore. (Your city: {city_std})"

# -------------------------------
# Knowledge Hub (PubMed + Trials)
# -------------------------------
def fetch_pubmed(query="Wegovy AND Novo Nordisk AND obesity", max_results=3):
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    search_url = f"{base_url}esearch.fcgi?db=pubmed&term={urllib.parse.quote(query)}&retmax={max_results}&retmode=json"
    try:
        search_resp = requests.get(search_url, timeout=10).json()
        pmids = search_resp.get("esearchresult", {}).get("idlist", [])
    except Exception:
        return ["⚠️ PubMed fetch failed."]
    articles = []
    for pmid in pmids:
        try:
            fetch_url = f"{base_url}efetch.fcgi?db=pubmed&id={pmid}&retmode=xml"
            xml = requests.get(fetch_url, timeout=10).text
            root = ElementTree.fromstring(xml)
            title = root.findtext(".//ArticleTitle")
            articles.append(f"• {title}\n🔗 https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
        except Exception:
            continue
    return articles or ["⚠️ No PubMed results."]

def fetch_clinical_trials(query="Wegovy Novo Nordisk", max_results=3):
    api_url = f"https://clinicaltrials.gov/api/query/study_fields?expr={urllib.parse.quote(query)}&fields=BriefTitle,Condition,OverallStatus,URL&min_rnk=1&max_rnk={max_results}&fmt=json"
    try:
        resp = requests.get(api_url, timeout=10)
        data = resp.json()
    except Exception:
        return ["⚠️ ClinicalTrials.gov fetch failed."]
    trials = []
    for study in data.get("StudyFieldsResponse", {}).get("StudyFields", []):
        title = study.get("BriefTitle", ["No title"])[0]
        condition = study.get("Condition", [""])[0]
        status = study.get("OverallStatus", [""])[0]
        url = study.get("URL", [""])[0]
        trials.append(f"• {title}\nCondition: {condition} | Status: {status}\n🔗 {url}")
    return trials or ["⚠️ No clinical trials found."]

# -------------------------------
# Serve Video
# -------------------------------
@app.route('/video/<path:filename>')
def video_files(filename):
    folder = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(folder, filename)

# -------------------------------
# Main Webhook for WhatsApp
# -------------------------------
@app.route("/incoming", methods=["POST"])
def incoming():
    try:
        frm = request.values.get("From")
        body_raw = request.values.get("Body") or ""
        phone = (frm or "").replace("whatsapp:", "")
        body = body_raw.strip()
        body_lc = body.lower()

        resp = MessagingResponse()
        msg = resp.message()

        row = safe_db_fetch(phone)
        if not row:
            msg.body("⚠️ Temporary DB error. Please try again in a moment.")
            return Response(str(resp), mimetype="application/xml")

        name, age, height, weight, checkins, family_member, state, msg_count, city, fam_name, fam_relation = row
        msg_count = (msg_count or 0) + 1
        update_field(phone, "msg_count", msg_count)

        # ---- Onboarding states ----
        if state == "new":
            update_field(phone, "state", "awaiting_name")
            msg.body("✅ Product verified: Wegovy authenticity confirmed.\n👋 Welcome to Wegovy Sampark! What's your *name*?")
            return Response(str(resp), mimetype="application/xml")

        if state == "awaiting_name":
            update_field(phone, "name", body.title())
            update_field(phone, "state", "awaiting_age")
            msg.body(f"Hi {body.title()}! 🎉 How old are you?")
            return Response(str(resp), mimetype="application/xml")

        if state == "awaiting_age":
            try:
                age_val = int(body)
                update_field(phone, "age", age_val)
                update_field(phone, "state", "awaiting_height")
                msg.body("Got it! What is your *height* in cm?")
            except:
                msg.body("Please enter a valid number for age.")
            return Response(str(resp), mimetype="application/xml")

        if state == "awaiting_height":
            try:
                h_val = float(body)
                update_field(phone, "height", h_val)
                update_field(phone, "state", "awaiting_weight")
                msg.body("Great! Now tell me your *weight* in kg.")
            except:
                msg.body("Please enter a valid height in cm.")
            return Response(str(resp), mimetype="application/xml")

        if state == "awaiting_weight":
            try:
                w_val = float(body)
                update_field(phone, "weight", w_val)
                update_field(phone, "state", "awaiting_city")
                bmi, cat = calculate_bmi(height, w_val)
                msg.body(f"✅ Saved your details!\nYour BMI is *{bmi}* ({cat}).\nWhich *city* are you from?")
            except:
                msg.body("Please enter a valid weight in kg.")
            return Response(str(resp), mimetype="application/xml")

        if state == "awaiting_city":
            city_std = normalize_city(body)
            update_field(phone, "city", city_std)
            update_field(phone, "state", "awaiting_family_name")
            msg.body(f"🏙️ Got it! You’re from {city_std}.\nNow tell me your *family member’s name*.")
            return Response(str(resp), mimetype="application/xml")

        if state == "awaiting_family_name":
            update_field(phone, "fam_name", body.title())
            update_field(phone, "state", "awaiting_family_relation")
            msg.body("And what is their *relation* to you? (e.g., Brother, Mother)")
            return Response(str(resp), mimetype="application/xml")

        if state == "awaiting_family_relation":
            update_field(phone, "fam_relation", body.title())
            fam_info = f"{fam_name or ''} ({body.title()})"
            update_field(phone, "family_member", fam_info)
            update_field(phone, "state", "ready")
            msg.body(f"📨 Family member added: {fam_info} ❤️\nType 'menu' to see options.")
            return Response(str(resp), mimetype="application/xml")

        # ---- Menu ----
        if body_lc == "menu":
            menu_text = (
                "📌 *Main Menu*\n\n"
                "1️⃣ Onboarding Video\n"
                "2️⃣ Side-effect Tips\n"
                "3️⃣ Weekly Check-in\n"
                "4️⃣ Recipe\n"
                "5️⃣ Pharmacy Locator\n"
                "6️⃣ Knowledge Hub\n\n"
                "Reply with a number (1-6), or just ask me your question!"
            )
            msg.body(menu_text)
            return Response(str(resp), mimetype="application/xml")

        # ---- Menu options ----
        if body_lc == "1":
            msg.body("📹 Watch the onboarding video here:\nhttps://www.dropbox.com/scl/fi/kgizm8vb8uhdqlaxswqfx/onboarding.mp4?rlkey=7f5krq9j630jd8n2wp5fohypc&st=9eaijrh8&dl=1")
        elif body_lc == "2":
            msg.body(find_answer("what are side effects"))
        elif body_lc == "3":
            body_lc = "check-in"
        elif body_lc == "4":
            msg.body(random.choice(RECIPES))
        elif body_lc == "5":
            msg.body(pharmacy_locator(city))
        elif body_lc == "6":
            pubs = fetch_pubmed()
            trials = fetch_clinical_trials()
            msg.body("🩺 *Knowledge Hub — PubMed*\n" + "\n\n".join(pubs))
            msg.body("🧪 *Clinical Trials*\n" + "\n\n".join(trials))

        # ---- Weekly check-in ----
        if body_lc in ("check-in", "checkin", "check in"):
            if checkins < 12:
                checkins += 1
                update_field(phone, "checkins", checkins)
                reply = f"✅ Check-in recorded! Progress: {make_progress_bar(checkins)} ({checkins}/12 weeks)"
                if checkins == 12:
                    reply += "\n🎉 Challenge complete!"
                elif checkins == 6:
                    reply += "\n👏 Halfway there!"
                reply += "\n\n" + random.choice(HYDRATION_TIPS) + "\n" + random.choice(RECIPES)
            else:
                reply = "✅ You’ve already completed all 12 weeks! 🎉 Challenge already complete."
            msg.body(reply)

        # ---- Fallback ----
        ans = find_answer(body_lc)
        if ans:
            msg.body(ans)
        elif body_lc not in ("1","2","3","4","5","6","check-in","checkin","check in","doctor"):
            msg.body("🤔 Sorry, I didn't get that. Type 'menu' to see options or ask me anything about Wegovy.")

        # ---- Hydration reminder ----
        if state == "ready" and (msg_count % 2 == 0) and body_lc not in ("check-in","checkin","check in"):
            msg.body(random.choice(HYDRATION_TIPS))

        return Response(str(resp), mimetype="application/xml")

    except Exception as e:
        print("❌ Error in /incoming:", str(e))
        traceback.print_exc()
        resp = MessagingResponse()
        resp.message("⚠️ Oops — server error. Please type 'menu' to continue.")
        return Response(str(resp), mimetype="application/xml")

# -------------------------------
# Run app
# -------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False, use_reloader=False)

