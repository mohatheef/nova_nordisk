# 📊 Wegovy Sampark Dashboard

A real-time dashboard built with **Streamlit** to track patient engagement, BMI distribution, and medication adherence for the Wegovy Sampark program.  
It connects to a local **SQLite database** (`sampark.db`) populated by a WhatsApp bot, and provides live insights for doctors, program managers, and hackathon judges.  

---

## Features
-  Live patient list with masked phone numbers  
-  Automatic BMI calculation + category assignment  
-  Visual adherence progress bar (check-ins)  
-  Summary metrics (total patients, average BMI, average check-ins)  
-  Interactive BMI distribution chart (Altair)  
-  Patient-wise adherence breakdown  
-  Auto-refresh every 5 seconds (judges see live updates)  

---

## 📦 Requirements
All dependencies are listed in `requirements.txt`.  
Key packages:
- Streamlit
- Pandas
- Altair
- streamlit-autorefresh  

---

## ⚙️ Installation & Setup

### 1️⃣ Clone the repo
```bash
git clone https://github.com/mohatheef/Nova_Nordisk_hackathon.git
cd wegovy-sampark-dashboard
