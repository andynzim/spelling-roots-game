
# spelling_roots_game.py  (OFFLINE-FIRST)
# ---------------------------------------------------------
# Works fully offline using a local CSV database of words & etymologies.
# It will ONLY try online Wiktionary if you enable it (toggle in the sidebar).
#
# How to run (PowerShell):
#   cd "C:\Users\andre\Downloads"
#   python -m pip install streamlit requests beautifulsoup4
#   python -m streamlit run spelling_roots_game.py
#
# Optional: Put 'etymology_db.csv' in the SAME folder as this .py file.
# You can also upload a CSV from the UI (columns: word, etymology, notes).
#
# CSV format (headers required):
#   word,etymology,notes
#   prestigious,"From French ‘prestigieux’, from Latin ‘praestīgium’ (illusion). Modern sense ‘highly respected’ is later.",""
#
# ---------------------------------------------------------

import os
import re
import csv
import json
import pathlib
import requests
import streamlit as st
from io import StringIO
from bs4 import BeautifulSoup

APP_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_DB_PATH = APP_DIR / "etymology_db.csv"

# ------------- Roots cheat sheet -------------
COMMON_ROOTS = {
    # Greek roots
    "phono": "Greek ‘phōnē’ = sound/voice (telephone, symphony)",
    "photo": "Greek ‘phōs/phōt-’ = light (photograph, photosynthesis)",
    "tele": "Greek ‘tēle’ = far/at a distance (telephone, telescope)",
    "geo": "Greek ‘gē’ = earth (geography, geology)",
    "auto": "Greek ‘autós’ = self (autobiography, automobile)",
    "chrono": "Greek ‘khrónos’ = time (chronology, synchronous)",
    "micro": "Greek ‘mikrós’ = small (microscope, microbe)",
    "macro": "Greek ‘makrós’ = large (macroeconomics, macromolecule)",
    "graph": "Greek ‘graphein’ = write (autograph, graphic)",
    "bio": "Greek ‘bíos’ = life (biology, biography)",
    "psycho": "Greek ‘psukhē’ = mind/soul (psychology, psychiatrist)",
    "hydro": "Greek ‘húdōr’ = water (hydroelectric, dehydrate)",
    "logos": "Greek ‘lógos’ = word/reason (biology, theology)",
    # Latin roots
    "port": "Latin ‘portare’ = carry (transport, import)",
    "scrib": "Latin ‘scribere’ = write (describe, scribe)",
    "script": "Latin ‘scriptum’ = write (manuscript, inscription)",
    "spect": "Latin ‘spectare’ = look/see (inspect, spectacle)",
    "vid": "Latin ‘vidēre’ = see (video, evidence)",
    "vis": "Latin ‘vidēre’ variant (vision, visible)",
    "dict": "Latin ‘dicere’ = say/speak (predict, dictionary)",
    "ject": "Latin ‘iacere’ = throw (project, eject)",
    "rupt": "Latin ‘rumpere’ = break (interrupt, rupture)",
    "cred": "Latin ‘credere’ = believe (credible, credit)",
    "terra": "Latin ‘terra’ = earth/land (terrain, territory)",
    "aqua": "Latin ‘aqua’ = water (aquarium, aquatic)",
    "bene": "Latin ‘bene’ = good/well (benefit, benevolent)",
    "mal": "Latin ‘malus’ = bad (malady, malfunction)",
    "mater": "Latin ‘mater’ = mother (maternal, matrimony)",
    "pater": "Latin ‘pater’ = father (paternal, paternity)",
    "urb": "Latin ‘urbs’ = city (urban, suburb)",
    "vac": "Latin ‘vacuus’ = empty (vacant, evacuate)",
    "voc": "Latin ‘vox/vocis’ = voice (vocal, advocate)",
    "ann": "Latin ‘annus’ = year (anniversary, annual)",
    "mort": "Latin ‘mors/mortis’ = death (mortal, mortician)",
    # Prefixes/suffixes
    "pre": "Prefix ‘pre-’ = before (preview, predict)",
    "re": "Prefix ‘re-’ = again/back (rewrite, return)",
    "un": "Prefix ‘un-’ = not/opposite (unhappy, unfair)",
    "mis": "Prefix ‘mis-’ = wrong/badly (misplace, misunderstand)",
    "anti": "Prefix ‘anti-’ = against (antibiotic, antifreeze)",
    "sub": "Prefix ‘sub-’ = under/below (subway, submarine)",
    "inter": "Prefix ‘inter-’ = between/among (international, interact)",
    "trans": "Prefix ‘trans-’ = across/beyond (transport, transcend)",
    "tri": "Prefix ‘tri-’ = three (triangle, tripod)",
    "ful": "Suffix ‘-ful’ = full of (joyful, helpful)",
    "less": "Suffix ‘-less’ = without (fearless, tireless)",
    "ology": "Suffix ‘-ology’ = study of (biology, geology)",
    "ist": "Suffix ‘-ist’ = person who does (artist, scientist)",
}
ROOT_REGEX = re.compile("|".join(sorted(COMMON_ROOTS.keys(), key=len, reverse=True)), re.IGNORECASE)

# ------------- Optional Online lookup (toggle) -------------
WIKI_API = "https://en.wiktionary.org/w/api.php"

def wiktionary_parse(title: str) -> str | None:
    try:
        resp = requests.get(WIKI_API, params={
            "action": "parse",
            "page": title,
            "prop": "text",
            "format": "json",
            "redirects": "1",
            "formatversion": "2",
        }, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("parse") or {}).get("text")
    except Exception:
        return None

def wiktionary_opensearch(word: str) -> str | None:
    try:
        resp = requests.get(WIKI_API, params={
            "action": "opensearch",
            "search": word,
            "limit": 5,
            "namespace": 0,
            "format": "json"
        }, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        titles = data[1] if isinstance(data, list) and len(data) >= 2 else []
        low = word.lower()
        for t in titles:
            if t.lower() == low:
                return t
        return titles[0] if titles else None
    except Exception:
        return None

def fetch_etymology_html(word: str) -> tuple[str | None, str | None]:
    for cand in [word.lower(), word.capitalize(), word]:
        html = wiktionary_parse(cand)
        if html:
            return html, cand
    title = wiktionary_opensearch(word)
    if title:
        html = wiktionary_parse(title)
        if html:
            return html, title
    return None, None

def extract_etymology_sections(html: str) -> list[dict]:
    out = []
    soup = BeautifulSoup(html, "html.parser")
    for h in soup.find_all(["h2", "h3", "h4"]):
        heading_text = h.get_text(" ", strip=True)
        if re.search(r"\bEtymology\b", heading_text, re.IGNORECASE):
            texts = []
            current_level = int(h.name[1])
            for sib in h.next_siblings:
                name = getattr(sib, "name", None)
                if name in ["h2", "h3", "h4"]:
                    lvl = int(name[1])
                    if lvl <= current_level:
                        break
                if name in ["p", "ul", "ol", "dl"]:
                    texts.append(sib.get_text(" ", strip=True))
            if texts:
                out.append({"heading": heading_text, "text": "\n\n".join(texts)})
    return out

# ------------- CSV load/save helpers -------------
def load_db_from_path(path: str | os.PathLike) -> list[dict]:
    rows = []
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if r.get("word"):
                    rows.append({
                        "word": r.get("word","").strip(),
                        "etymology": r.get("etymology","").strip(),
                        "notes": r.get("notes","").strip(),
                    })
    except FileNotFoundError:
        pass
    return rows

def save_db_to_path(path: str | os.PathLike, rows: list[dict]):
    fieldnames = ["word", "etymology", "notes"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k,"") for k in fieldnames})

def clean_word(w: str) -> str:
    return re.sub(r"[^A-Za-z\-\']", "", (w or "")).strip()

# ------------- UI -------------
st.title("🧠 Spelling Roots Game — Offline First")
st.caption("Type a word or choose one. Explanations come from your local CSV first. (Online lookup is optional.)")

with st.sidebar:
    st.subheader("Settings")
    use_online = st.toggle("Try online Wiktionary if not found locally", value=False,
                           help="Turn this ON if your internet connectivity and firewall allow it.")
    st.markdown("**Local DB file:** `etymology_db.csv` (same folder as this app).")

# Load local DB at startup
local_rows = load_db_from_path(DEFAULT_DB_PATH)
local_map = {r["word"].lower(): r for r in local_rows}
grade8 = sorted({r["word"] for r in local_rows if r["notes"].lower().strip() == "grade8"}) or []

colA, colB = st.columns([2,1])
with colA:
    word = st.text_input("Enter a word:", value="prestigious")
with colB:
    pick = st.selectbox("…or pick from Grade 8:", ["(none)"] + grade8)
    if pick != "(none)":
        word = pick

st.write("")

# Upload/extend database
with st.expander("📥 Load/extend from a CSV (columns: word, etymology, notes)"):
    f = st.file_uploader("Upload CSV to extend/replace the local database", type=["csv"])
    mode = st.radio("How to apply uploaded CSV?", ["Append (keep existing)", "Replace (overwrite)"], horizontal=True)
    if f is not None:
        try:
            text = f.read().decode("utf-8")
            reader = csv.DictReader(StringIO(text))
            new_rows = []
            for r in reader:
                if r.get("word"):
                    new_rows.append({
                        "word": r.get("word","").strip(),
                        "etymology": r.get("etymology","").strip(),
                        "notes": r.get("notes","").strip(),
                    })
            if mode.startswith("Replace"):
                local_rows = new_rows
            else:
                local_rows.extend(new_rows)
            save_db_to_path(DEFAULT_DB_PATH, local_rows)
            st.success(f"Saved {len(new_rows)} rows. Database now has {len(local_rows)} entries.")
            st.stop()
        except Exception as e:
            st.error(f"Upload failed: {e}")

# Guess-the-root mini-game
if "score" not in st.session_state:
    st.session_state.score = 0
if "rounds" not in st.session_state:
    st.session_state.rounds = 0

col1, col2 = st.columns([1,1])
with col1:
    guess = st.text_input("Guess a root/prefix/suffix (e.g., pre, bio, port):", value="pre")
with col2:
    if st.button("Check guess"):
        st.session_state.rounds += 1
        g = clean_word(guess).lower()
        if g in COMMON_ROOTS:
            st.session_state.score += 1
            st.success(f"Nice! **{g}** → {COMMON_ROOTS[g]}")
        else:
            st.error(f"Good try! **{g}** isn’t in our cheat sheet. Try: *pre, auto, geo, port, photo…*")

st.metric("Score", st.session_state.score)
st.caption(f"Rounds played: {st.session_state.rounds}")

# Main action
if st.button("Explain origins"):
    w = clean_word(word)
    if not w:
        st.error("Please enter letters only.")
    else:
        key = w.lower()
        row = local_map.get(key)

        if row and row.get("etymology"):
            st.success("Found in local database ✅")
            st.markdown(f"**{w}** — {row['etymology']}")
            if row.get("notes"):
                st.caption(f"Notes: {row['notes']}")
        else:
            st.warning("Not in local database.")
            # Heuristic root hints (always work offline)
            matches = sorted(set(m.group(0).lower() for m in ROOT_REGEX.finditer(w)))
            if matches:
                st.subheader("🔎 Hints from common roots (offline)")
                for r in matches:
                    st.markdown(f"- **{r}** — {COMMON_ROOTS[r]}")
            else:
                st.info("No obvious roots found. Try prefixes/suffixes like pre-, re-, -ology, -ist.")

            # Optional online lookup
            if use_online:
                with st.spinner(f"Trying online Wiktionary for '{w}'…"):
                    html, title = fetch_etymology_html(w)
                if not html:
                    st.error("Online lookup failed (network/firewall or page not found).")
                else:
                    if title and title.lower() != w.lower():
                        st.info(f"Showing results for **{title}**")
                    sections = extract_etymology_sections(html)
                    if not sections:
                        st.warning("No explicit Etymology section found on the page.")
                    else:
                        st.success(f"Found {len(sections)} etymology section(s) online.")
                        for sec in sections:
                            st.markdown(f"**{sec['heading']}**")
                            st.write(sec["text"])

st.divider()
st.markdown("Made for curious spellers. ✨  •  Offline-first with optional online lookup")
