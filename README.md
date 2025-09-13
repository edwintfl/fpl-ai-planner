# FPL AI Picker (Streamlit)
Deploy on Streamlit Cloud (free) or run locally.

## Deploy (Streamlit Cloud)
1. Put these files in a **public GitHub repo** (app.py at repo root).
2. In Streamlit Cloud: New app → pick repo → `app.py` → Deploy.
3. Open your app on phone or PC. It fetches live data from `fantasy.premierleague.com/api/`.

## Local Run
```
pip install -r requirements.txt
streamlit run app.py
```
