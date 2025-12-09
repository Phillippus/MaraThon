import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import requests
from ics import Calendar
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
import random
import math

# --- REPORTLAB PRE PDF + UNICODE ---
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import urllib.request

# --- KONFIGURÁCIA ---
CONFIG_FILE = 'hospital_config.json'
HISTORY_FILE = 'room_history.json'
PRIVATE_CALENDAR_URL = "https://calendar.google.com/calendar/ical/fntnonk%40gmail.com/private-e8ce4e0639a626387fff827edd26b87f/basic.ics"
GIST_FILENAME_CONFIG = "hospital_config_v17.json"
GIST_FILENAME_HISTORY = "room_history_v17.json"

ROOMS_LIST = [
    (1, 3), (2, 3), (3, 3), (4, 3), (5, 3),
    (7, 1), (8, 3), (9, 3), (10, 1), (11, 1),
    (12, 2), (13, 2), (14, 2), (15, 2), (16, 2), (17, 2),
    (18, 3), (19, 3)
]

# --- REGISTER UNICODE FONT PRE PDF ---
def setup_pdf_fonts():
    font_dir = "/tmp"
    font_name = "DejaVuSans"
    font_path = os.path.join(font_dir, f"{font_name}.ttf")
    try:
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            return font_name
    except: pass
    
    if not os.path.exists(font_path):
        try:
            font_url = "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/ttf/DejaVuSans.ttf"
            urllib.request.urlretrieve(font_url, font_path)
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            return font_name
        except: pass
    return "Helvetica"

# --- GIST ULOŽISKO ---
def get_gist_id(filename):
    if "github" not in st.secrets: return None
    try:
        token = st.secrets["github"]["token"]
        headers = {"Authorization": f"token {token}"}
        resp = requests.get("https://api.github.com/gists", headers=headers)
        resp.raise_for_status()
        for gist in resp.json():
            if filename in gist['files']: return gist['id']
    except: pass
    return None

def load_data_from_gist(filename):
    if "github" not in st.secrets: return None
    gist_id = get_gist_id(filename)
    if not gist_id: return None
    try:
        token = st.secrets["github"]["token"]
        headers = {"Authorization": f"token {token}"}
        resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=headers)
        resp.raise_for_status()
        content = resp.json()['files'][filename]['content']
        return json.loads(content)
    except: return None

def save_data_to_gist(filename, data):
    if "github" not in st.secrets: return
    try:
        token = st.secrets["github"]["token"]
        headers = {"Authorization": f"token {token}"}
        gist_id = get_gist_id(filename)
        payload = {
            "description": f"Storage for {filename}",
            "public": False,
            "files": { filename: {"content": json.dumps(data, ensure_ascii=False, indent=2)} }
        }
        if gist_id: requests.patch(f"https://api.github.com/gists/{gist_id}", json=payload, headers=headers)
        else: requests.post("https://api.github.com/gists", json=payload, headers=headers)
    except: pass

def _load_data(gist_filename, local_filename, default_factory):
    data = load_data_from_gist(gist_filename)
    if data is not None: return data
    if os.path.exists(local_filename):
        try:
            with open(local_filename, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return default_factory()

def load_config():
    config = _load_data(GIST_FILENAME_CONFIG, CONFIG_FILE, get_default_config)
    config, changed = migrate_homolova_to_vidulin(config)
    if 'closures' not in config:
        config['closures'] = {}
        changed = True
    if changed: save_config(config)
    return config

def load_history(): return _load_data(GIST_FILENAME_HISTORY, HISTORY_FILE, lambda: {})

def save_config(config):
    try: 
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(config, f, ensure_ascii=False, indent=2)
    except: pass
    save_data_to_gist(GIST_FILENAME_CONFIG, config)

def save_history(history):
    try: 
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f: json.dump(history, f, ensure_ascii=False, indent=2)
    except: pass
    save_data_to_gist(GIST_FILENAME_HISTORY, history)

def get_default_config():
    return {
        "total_beds": 42,
        "closures": {}, 
        "email_settings": { "default_to": "", "default_subject": "Rozpis služieb", "default_body": "Dobrý deň,\nv prílohe rozpis." },
        "ambulancie": {
            "Konziliarna": { "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"], "priority": ["Kohutekova", "Kohutek", "Bystricky", "Zavrelova"] },
            "Velka dispenzarna": { "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"], "priority": ["Bocak", "Stratena", "Vidulin", "Kurisova", "Blahova", "Hrabosova", "Miklatkova", "Martinka"] },
            "Mala dispenzarna": { "dni": ["Pondelok", "Piatok"], "priority": ["Spanik", "Stratena", "Vidulin", "Kurisova", "Blahova", "Hrabosova", "Miklatkova"] },
            "Radio 2A": { "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"], "priority": ["Zavrelova", "Kohutek", "Kurisova", "Miklatkova", "Bystricky"], "check_presence": ["Zavrelova", "Martinka"] },
            "Radio 2B": { "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"], "priority": ["Martinka"], "conditional_owner": "Martinka" },
            "Chemo 8A": { "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"], "priority": ["Hatalova", "Kohutek", "Stratena", "Bystricky"] },
            "Chemo 8B": { "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"], "priority": ["Riedlova", "Kohutek", "Stratena", "Bystricky", "Vidulin", "Blahova"] },
            "Chemo 8C": { "dni": ["Utorok", "Streda", "Stvrtok"], "priority": ["Stratena", "Kohutek", "Bystricky", "Vidulin", "Blahova"] },
            "Wolf": { "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"], "priority": ["Spanik", "Miklatkova", "Kurisova", "Kohutek"] }
        },
        "lekari": {
            "Bystricky": { "moze": ["Konziliarna", "Velka dispenzarna", "Mala dispenzarna", "Radio 2A", "Chemo 8A", "Chemo 8B", "Chemo 8C", "Wolf"], "active": True },
            "Kohutek": { "moze": ["Oddelenie", "Konziliarna", "Velka dispenzarna", "Mala dispenzarna", "Radio 2A", "Chemo 8A", "Chemo 8B", "Chemo 8C", "Wolf"], "pevne_dni": {"Pondelok": "Chemo 8B", "Utorok": "Chemo 8B"}, "active": True },
            "Kohutekova": { "moze": ["Konziliarna"], "pevne_dni": {"Pondelok": "Konziliarna", "Utorok": "Konziliarna", "Streda": "Konziliarna", "Stvrtok": "Konziliarna"}, "nepracuje": ["Piatok"], "active": True },
            "Riedlova": { "moze": ["Chemo 8B"], "pevne_dni": {"Streda": "Chemo 8B", "Stvrtok": "Chemo 8B"}, "nepracuje": ["Pondelok", "Utorok"], "active": True },
            "Zavrelova": { "moze": ["Radio 2A", "Konziliarna"], "pevne_dni": {"Pondelok": "Radio 2A", "Utorok": "Radio 2A", "Streda": "Radio 2A", "Stvrtok": "Radio 2A", "Piatok": "Radio 2A"}, "active": True },
            "Martinka": { "moze": ["Radio 2B", "Oddelenie", "Velka dispenzarna"], "pevne_dni": {"Pondelok": "Radio 2B", "Utorok": "Radio 2B", "Streda": "Radio 2B", "Stvrtok": "Radio 2B", "Piatok": "Radio 2B"}, "active": True },
            "Hatalova": { "moze": ["Chemo 8A"], "pevne_dni": {"Pondelok": "Chemo 8A", "Utorok": "Chemo 8A", "Streda": "Chemo 8A", "Stvrtok": "Chemo 8A", "Piatok": "Chemo 8A"}, "active": True },
            "Stratena": { "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna", "Chemo 8A", "Chemo 8B", "Chemo 8C"], "pevne_dni": {"Utorok": "Chemo 8C", "Streda": "Chemo 8C", "Stvrtok": "Chemo 8C"}, "active": True },
            "Vidulin": { "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna", "Chemo 8A", "Chemo 8B", "Chemo 8C"], "active": True },
            "Miklatkova": { "moze": ["Oddelenie", "Wolf"], "active": True },
            "Kurisova": { "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna", "Radio 2A", "Wolf"], "special": "veduca", "active": True },
            "Blahova": { "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna", "Chemo 8B", "Chemo 8C"], "active": False },
            "Hrabosova": { "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna"], "active": False, "extra_dni": [] },
            "Bocak": { "moze": ["Velka dispenzarna"], "pevne_dni": {"Pondelok": "Velka dispenzarna", "Utorok": "Velka dispenzarna", "Streda": "Velka dispenzarna", "Stvrtok": "Velka dispenzarna", "Piatok": "Velka dispenzarna"}, "active": True },
            "Spanik": { "moze": ["Wolf", "Mala dispenzarna"], "pevne_dni": {"Pondelok": "Mala dispenzarna", "Utorok": "Wolf", "Streda": "Wolf", "Stvrtok": "Wolf", "Piatok": "Mala dispenzarna"}, "active": True },
            "Kacurova": { "moze": ["Oddelenie"], "active": True },
            "Hunakova": { "moze": ["Oddelenie"], "active": True }
        }
    }

def migrate_homolova_to_vidulin(config):
    changed = False
    if "Homolova" in config["lekari"]:
        config["lekari"]["Vidulin"] = config["lekari"].pop("Homolova")
        changed = True
    for amb_name, amb_data in config["ambulancie"].items():
        if isinstance(amb_data["priority"], list):
            if "Homolova" in amb_data["priority"]:
                amb_data["priority"] = ["Vidulin" if x == "Homolova" else x for x in amb_data["priority"]]
                changed = True
        elif isinstance(amb_data["priority"], dict):
            for day_key, day_list in amb_data["priority"].items():
                if "Homolova" in day_list:
                    amb_data["priority"][day_key] = ["Vidulin" if x == "Homolova" else x for x in day_list]
                    changed = True
    return config, changed

def distribute_rooms(doctors_list, wolf_doc_name, previous_assignments=None, manual_preferences=None):
    if not doctors_list: return {}, {}
    if manual_preferences is None: manual_preferences = {}
    if previous_assignments is None: previous_assignments = {}
    
    rt_help_doc = "Miklatkova" if "Miklatkova" in doctors_list else None
    head_doc = "Kurisova" if "Kurisova" in doctors_list else None
    
    assignment = {d: [] for d in doctors_list}
    current_beds = {d: 0 for d in doctors_list}
    available_rooms = sorted(ROOMS_LIST, key=lambda x: x[0]) 
    
    # --- 1. TARGET CALCULATION (SPRAVODLIVOSŤ) ---
    rt_group = [d for d in doctors_list if d == rt_help_doc or d == wolf_doc_name]
    full_group = [d for d in doctors_list if d not in rt_group and d != head_doc]
    if head_doc and head_doc not in rt_group and len(full_group) < 2: full_group.append(head_doc)
    
    total_beds = sum(r[1] for r in ROOMS_LIST)
    targets = {}
    used_by_rt = 0
    
    rt_limit = 9 if len(full_group) >= 3 else 12
    for d in rt_group:
        targets[d] = rt_limit
        used_by_rt += targets[d]
        
    beds_for_full = total_beds - used_by_rt
    if full_group:
        fair_share = min(15, math.floor(beds_for_full / len(full_group)) + 1)
        for d in full_group: targets[d] = fair_share

    if head_doc and head_doc not in targets: targets[head_doc] = 0

    # --- 2. PREFERENCIE (MANUAL) ---
    for doc, nums in manual_preferences.items():
        if doc not in doctors_list: continue
        my_target = targets.get(doc, 15)
        for num in nums:
            r_obj = next((r for r in available_rooms if r[0] == num), None)
            if not r_obj: continue
            if current_beds[doc] + r_obj[1] <= my_target:
                assignment[doc].append(r_obj)
                current_beds[doc] += r_obj[1]
                available_rooms.remove(r_obj)

    # --- 3. KONTINUITA (PREVIOUS) ---
    if previous_assignments:
        for doc in doctors_list:
            if doc in previous_assignments:
                my_prev = []
                for r_id in previous_assignments[doc]:
                    found = next((r for r in available_rooms if r[0] == r_id), None)
                    if found: my_prev.append(found)
                my_target = targets.get(doc, 15)
                random.shuffle(my_prev)
                for r_obj in my_prev:
                    if current_beds[doc] + r_obj[1] <= my_target:
                        assignment[doc].append(r_obj)
                        current_beds[doc] += r_obj[1]
                        available_rooms.remove(r_obj)

    # --- 4. DOROVNÁVANIE ---
    while available_rooms:
        candidates = [d for d in doctors_list if current_beds[d] < targets.get(d, 15)]
        if not candidates: candidates = doctors_list
        candidates.sort(key=lambda d: current_beds[d])
        receiver = candidates[0]
        best_room = available_rooms[0]
        if assignment[receiver]:
            avgs = sum(r[0] for r in assignment[receiver]) / len(assignment[receiver])
            best_room = min(available_rooms, key=lambda r: abs(r[0] - avgs))
        assignment[receiver].append(best_room)
        current_beds[receiver] += best_room[1]
        available_rooms.remove(best_room)

    result_text, result_raw = {}, {}
    for doc in doctors_list:
        rooms = sorted(assignment[doc], key=lambda x: x[0])
        result_raw[doc] = [r[0] for r in rooms]
        r_str = ", ".join([str(r[0]) for r in rooms])
        suf = ""
        if doc == wolf_doc_name: suf = " + Wolf"
        elif doc == head_doc and "RT" not in suf: suf = " + RT oddelenie"
        elif doc == rt_help_doc: suf = " + RT oddelenie"
        
        if not rooms:
             if doc == wolf_doc_name: result_text[doc] = "Wolf (0L)"
             elif doc == head_doc: result_text[doc] = "RT oddelenie"
             elif doc == rt_help_doc: result_text[doc] = "RT oddelenie (0L)"
             else: result_text[doc] = ""
        else:
             result_text[doc] = f"{r_str}{suf}"
             
    return result_text, result_raw

def get_ical_events(start_date, end_date):
    try:
        response = requests.get(PRIVATE_CALENDAR_URL)
        response.raise_for_status()
        c = Calendar(response.text)
        absences = {}
        for event in c.events:
            ev_start, ev_end = event.begin.date(), event.end.date()
            if ev_end < start_date.date() or ev_start > end_date.date(): continue
            raw = event.name.strip()
            name, typ = raw, "Dovolenka"
            if raw.upper().endswith('PN'): typ, name = "PN", raw[:-2].rstrip(' -')
            elif raw.upper().endswith('VZ'): typ, name = "Vzdelávanie", raw[:-2].rstrip(' -')
            elif raw.upper().endswith('S') and not raw.upper().endswith('OS'): typ, name = "Stáž", raw[:-1].rstrip(' -')
            elif '-' in raw and typ == "Dovolenka":
                parts = raw.split('-')
                name = parts[0].strip()
            curr, limit = max(ev_start, start_date.date()), min(ev_end, end_date.date())
            while curr < limit:
                absences.setdefault(curr.strftime('%Y-%m-%d'), {})[name] = typ
                curr += timedelta(days=1)
        return absences
    except: return {}

def generate_data_structure(config, absences, start_date, save_hist=True):
    days_map = {0: "Pondelok", 1: "Utorok", 2: "Streda", 3: "Stvrtok", 4: "Piatok"}
    weekday = start_date.weekday()
    thursday = start_date + timedelta(days=(3 - weekday) % 7)
    dates, data_grid = [], {}
    all_doctors, doctors_info = [], {}
    week_dates_str = [(thursday + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7) if (thursday + timedelta(days=i)).weekday() < 5]

    for d_name, props in config['lekari'].items():
        if props.get('active', True) or any(ed in week_dates_str for ed in props.get('extra_dni', [])):
            all_doctors.append(d_name)
            if not props.get('active', True):
                readable = [datetime.strptime(ed, '%Y-%m-%d').strftime('%d.%m.') for ed in props.get('extra_dni', []) if ed in week_dates_str]
                doctors_info[d_name] = f"⚠️ len {', '.join(readable)}"

    all_doctors.sort()
    history = load_history()
    last_day_assignments = history.get((thursday - timedelta(days=1)).strftime('%Y-%m-%d'), {})
    manual_all = st.session_state.get("manual_core", {})
    closures = config.get('closures', {})
    
    for i in range(7):
        curr_date = thursday + timedelta(days=i)
        day_name = days_map.get(curr_date.weekday())
        if not day_name: continue
        date_str = curr_date.strftime('%d.%m.%Y')
        date_key = curr_date.strftime('%Y-%m-%d')
        dates.append(date_str)
        day_absences = absences.get(date_key, {})
        closed_today = closures.get(date_key, [])
        data_grid[date_str] = {}
        
        available = [d for d in all_doctors if (config['lekari'][d].get('active', True) or date_key in config['lekari'][d].get('extra_dni', [])) and d not in day_absences and day_name not in config['lekari'][d].get('nepracuje', [])]
        assigned_amb = {}
        
        for doc in list(available):
            if fixed := config['lekari'][doc].get('pevne_dni', {}).get(day_name):
                for t in [t.strip() for t in fixed.split(',')]:
                    if t in closed_today: assigned_amb[t] = "ZATVORENÉ"
                    else: assigned_amb[t] = doc
                available.remove(doc)
        
        ambs_to_process = ["Radio 2A", "Radio 2B", "Chemo 8B", "Chemo 8A", "Chemo 8C", "Wolf", "Konziliarna", "Velka dispenzarna", "Mala dispenzarna"]
        amb_scarcity = []
        for amb_name in ambs_to_process:
            if amb_name in assigned_amb or amb_name in closed_today: 
                if amb_name in closed_today: assigned_amb[amb_name] = "ZATVORENÉ"
                continue
            if day_name not in config['ambulancie'][amb_name]['dni']:
                assigned_amb[amb_name] = "---"
                continue
            if amb_name == "Radio 2B" and "Martinka" not in available:
                assigned_amb[amb_name] = "ZATVORENÉ"
                continue
            prio = config['ambulancie'][amb_name]['priority']
            if isinstance(prio, dict): prio = prio.get(str(curr_date.weekday()), prio.get('default', []))
            cands = [d for d in prio if d in available and amb_name in config['lekari'][d].get('moze', [])]
            amb_scarcity.append({"name": amb_name, "candidates": cands, "count": len(cands), "idx": ambs_to_process.index(amb_name)})
        
        amb_scarcity.sort(key=lambda x: (x['count'], x['idx']))
        for item in amb_scarcity:
            amb = item['name']
            cands = [c for c in item['candidates'] if c in available]
            if amb == "Wolf" and "Spanik" in all_doctors and "Spanik" not in day_absences and assigned_amb.get("Mala dispenzarna") == "Spanik":
                 assigned_amb["Wolf"] = "Spanik"
                 continue
            if not cands:
                assigned_amb[amb] = "NEOBSADENÉ"
                continue
            chosen = cands[0]
            assigned_amb[amb] = chosen
            available.remove(chosen)

        for k, v in assigned_amb.items(): data_grid[date_str][k] = v
        
        wolf_doc = assigned_amb.get("Wolf")
        if "ODDELENIE (Celé)" in closed_today:
            room_text_map, room_raw_map = {}, {}
            for d in all_doctors: room_text_map[d] = "ZATVORENÉ"
        else:
            ward_cands = [d for d in available if "Oddelenie" in config['lekari'][d].get('moze', [])]
            if wolf_doc and wolf_doc not in ward_cands and "Oddelenie" in config['lekari'].get(wolf_doc, {}).get('moze', []):
                ward_cands.append(wolf_doc)
            
            daily_pref = manual_all.get(date_key, {})
            if not daily_pref and i < 7:
                 first_day_key = dates[0] if dates else date_key
                 start_key = start_date.strftime('%Y-%m-%d')
                 if start_key in manual_all:
                     daily_pref = manual_all[start_key]

            room_text_map, room_raw_map = distribute_rooms(ward_cands, wolf_doc, last_day_assignments, daily_pref)
            last_day_assignments = room_raw_map
            if save_hist: history[date_key] = room_raw_map
        
        for doc in all_doctors:
            if not (config['lekari'][doc].get('active', True) or date_key in config['lekari'][doc].get('extra_dni', [])):
                data_grid[date_str][doc] = ""
                continue
            if doc in day_absences: data_grid[date_str][doc] = day_absences[doc]
            elif doc in room_text_map: data_grid[date_str][doc] = room_text_map[doc]
            else:
                my = [a for a, d in assigned_amb.items() if d == doc]
                data_grid[date_str][doc] = " + ".join(my) if my else ""
                
        if save_hist: save_history(history)
    return dates, data_grid, all_doctors, doctors_info

def scan_future_problems(config, weeks_ahead=12):
    problems = []
    start = datetime.now()
    end = start + timedelta(weeks=weeks_ahead)
    absences = get_ical_events(start, end)
    closures = config.get('closures', {})
    current = start
    while current <= end:
        dates, grid, docs, info = generate_data_structure(config, absences, current, save_hist=False)
        for date_str in dates:
            date_obj = datetime.strptime(date_str, '%d.%m.%Y')
            date_key = date_obj.strftime('%Y-%m-%d')
            closed_today = closures.get(date_key, [])
            for amb_name in ["Konziliarna", "Velka dispenzarna", "Mala dispenzarna", "Radio 2A", "Radio 2B", "Chemo 8A", "Chemo 8B", "Chemo 8C", "Wolf"]:
                val = grid[date_str].get(amb_name, "")
                if val in ["NEOBSADENÉ", "???", ""] and amb_name not in closed_today and "ODDELENIE (Celé)" not in closed_today:
                     problems.append({"Dátum": date_str, "Pracovisko": amb_name})
        current += timedelta(weeks=1)
    return pd.DataFrame(problems) if problems else None

def create_display_df(dates, data_grid, all_doctors, doctors_info, motto, config):
    rows = []
    ward_doctors = [d for d in all_doctors if "Oddelenie" in config['lekari'][d].get('moze', [])]
    display_map = { "Radio 2A": "Radio 2A", "Konziliarna": "Konziliárna amb.", "Velka dispenzarna": "velký dispenzár", "Mala dispenzarna": "malý dispenzár" }
    
    rows.append(["Oddelenie"] + dates)
    for doc in ward_doctors:
        vals = []
        for date in dates:
            val = data_grid[date].get(doc, "")
            for old, new in display_map.items(): val = val.replace(old, new)
            vals.append(val)
        label = f"Dr {doc}" + (f" {doctors_info[doc]}" if doc in doctors_info else "")
        rows.append([label] + vals)
    rows.append([motto or "Motto"] + [""] * len(dates))
    sections = [("Konziliárna amb", ["Konziliarna"]), ("RT ambulancie", ["Radio 2A", "Radio 2B"]), ("Chemo amb", ["Chemo 8A", "Chemo 8B", "Chemo 8C"]), ("Disp. Ambulancia", ["Velka dispenzarna", "Mala dispenzarna"]), ("RTG Terapia", ["Wolf"])]
    for title, ambs in sections:
        rows.append([title] + dates)
        for amb in ambs:
            vals = [data_grid[d].get(amb, "").replace("---", "").replace("NEOBSADENÉ", "???") for d in dates]
            rows.append([display_map.get(amb, amb)] + vals)
        rows.append([""] * (len(dates) + 1))
    return pd.DataFrame(rows)

def create_excel_report(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="Rozpis")
        ws = writer.sheets['Rozpis']
        bold, center, thin = Font(bold=True), Alignment(horizontal="center", vertical="center", wrap_text=True), Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        ws.cell(1, 1, f"Rozpis prác Onkologická klinika {df.columns[1]} - {df.columns[-1]}").font = bold
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(df.columns))
        ws['A1'].alignment = center
        for r, row in enumerate(df.iterrows(), 2):
            is_header = row[1][0] in ["Oddelenie", "Konziliárna amb", "RT ambulancie", "Chemo amb", "Disp. Ambulancia", "RTG Terapia"]
            is_motto = (row[1][0] == st.session_state.get('motto', 'Motto'))
            for c, val in enumerate(row[1], 1):
                cell = ws.cell(r, c, val)
                cell.border = thin
                cell.alignment = center
                if is_header or (c==1 and not is_motto): cell.font = bold
                if is_motto:
                    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(df.columns))
                    cell.font, cell.fill = Font(bold=True, italic=True), PatternFill(start_color="EEEEEE", end_color="EEEEEE", fill_type="solid")
                    ws.row_dimensions[r].height = 25
                    break
        ws.column_dimensions['A'].width = 25
        for i in range(2, len(df.columns) + 1): ws.column_dimensions[get_column_letter(i)].width = 18
    return output.getvalue()

def create_pdf_report(df, motto):
    buffer = io.BytesIO()
    font_name = setup_pdf_fonts()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=10, leftMargin=10, topMargin=10, bottomMargin=10)
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle('C', parent=styles['Normal'], fontName=font_name, fontSize=7, leading=8, alignment=1)
    data = [[Paragraph(str(c), ParagraphStyle('H', parent=styles['Normal'], fontName=font_name, fontSize=8, alignment=1)) for c in df.columns]]
    for _, row in df.iterrows():
        row_data = []
        is_motto = (row[0] == (motto or "Motto"))
        for i, val in enumerate(row.values):
            txt = str(val) if val else ""
            if is_motto and i==0: 
                # Motto centered across all columns
                p = Paragraph(f"<para align='center'><b><i>{txt}</i></b></para>", ParagraphStyle('M', parent=cell_style, fontSize=9, padding=6, alignment=1))
            elif is_motto: p = ""
            elif i==0: p = Paragraph(f"<b>{txt}</b>", cell_style)
            else: p = Paragraph(txt, cell_style)
            row_data.append(p)
        data.append(row_data)
    t = Table(data, colWidths=[130] + [135]*(len(df.columns)-1))
    style = TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('BACKGROUND', (0,0), (-1,0), colors.grey)])
    for i, row in enumerate(df.iterrows()):
        if row[1][0] in ["Oddelenie", "Konziliárna amb", "RT ambulancie", "Chemo amb", "Disp. Ambulancia", "RTG Terapia"]:
            style.add('BACKGROUND', (0, i+1), (-1, i+1), colors.lightgrey)
        if row[1][0] == (motto or "Motto"):
            style.add('SPAN', (0, i+1), (-1, i+1))
            style.add('BACKGROUND', (0, i+1), (-1, i+1), colors.whitesmoke)
            style.add('ALIGN', (0, i+1), (-1, i+1), 'CENTER')
    t.setStyle(style)
    doc.build([Paragraph(f"Rozpis prác {df.columns[1]} - {df.columns[-1]}", styles['Title']), t])
    buffer.seek(0)
    return buffer.getvalue()

def send_email_with_pdf(pdf_bytes, filename, to_email, subject, body):
    if "email" not in st.secrets: return False
    try:
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = st.secrets["email"]["username"], to_email, subject
        msg.attach(MIMEText(body, 'plain'))
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename={filename}')
        msg.attach(part)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(msg['From'], st.secrets["email"]["password"])
        server.send_message(msg)
        server.quit()
        return True
    except: return False

def group_closures_to_intervals(closures_dict):
    sorted_dates = sorted(closures_dict.keys())
    if not sorted_dates: return []
    intervals, curr_start, curr_end, curr_val = [], sorted_dates[0], sorted_dates[0], sorted(closures_dict[sorted_dates[0]])
    for d_str in sorted_dates[1:]:
        d, prev = datetime.strptime(d_str, '%Y-%m-%d').date(), datetime.strptime(curr_end, '%Y-%m-%d').date()
        val = sorted(closures_dict[d_str])
        if (d - prev).days == 1 and val == curr_val: curr_end = d_str
        else:
            intervals.append((curr_start, curr_end, curr_val))
            curr_start, curr_end, curr_val = d_str, d_str, val
    intervals.append((curr_start, curr_end, curr_val))
    return intervals

# --- MAIN APP ---
st.set_page_config(page_title="Rozpis FN Trenčín", layout="wide")
st.title("🏥 Rozpis prác - Onkologická klinika FN Trenčín")

if 'config' not in st.session_state: st.session_state.config = load_config()
if 'manual_core' not in st.session_state: st.session_state.manual_core = {}
if 'temp_exceptions' not in st.session_state: st.session_state.temp_exceptions = []

mode = st.sidebar.radio("Navigácia", ["🚀 Generovať rozpis", "⚙️ Nastavenia lekárov", "🏥 Nastavenia ambulancií", "📧 Nastavenia Emailu"])

if mode == "🚀 Generovať rozpis":
    c1, c2 = st.columns(2)
    st.session_state.motto = c1.text_input("📢 Motto:", placeholder="...")
    start_d = c2.date_input("Začiatok:", datetime.now())

    with st.expander("📅 Výnimky", expanded=True):
        if st.session_state.config.get('closures'):
            st.markdown("##### 💾 Aktívne výnimky:")
            for s, e, l in group_closures_to_intervals(st.session_state.config['closures']):
                c1, c2, c3 = st.columns([2, 4, 1])
                lbl = f"{datetime.strptime(s, '%Y-%m-%d').strftime('%d.%m.')} - {datetime.strptime(e, '%Y-%m-%d').strftime('%d.%m.')}" if s!=e else datetime.strptime(s, '%Y-%m-%d').strftime('%d.%m.')
                c1.text(lbl)
                c2.text(", ".join(l) if len(l)<5 else "VIACERÉ")
                if c3.button("🗑️", key=f"d_{s}"):
                    curr = datetime.strptime(s, '%Y-%m-%d')
                    while curr <= datetime.strptime(e, '%Y-%m-%d'):
                        st.session_state.config['closures'].pop(curr.strftime('%Y-%m-%d'), None)
                        curr += timedelta(days=1)
                    save_config(st.session_state.config)
                    st.rerun()

        st.markdown("---")
        c1, c2 = st.columns([1, 2])
        nr = c1.date_input("Nový rozsah:", value=[], key="n_r")
        nc = c2.multiselect("Zatvoriť:", ["ODDELENIE (Celé)"] + list(st.session_state.config['ambulancie'].keys()), key="n_c")
        if st.button("➕ Pridať"):
            if nr and nc:
                st.session_state.temp_exceptions.append(((nr[0], nr[1] if len(nr)>1 else nr[0]), nc))
                st.rerun()

        if st.session_state.temp_exceptions:
            st.write("Nové (neuložené):")
            for i, (r, l) in enumerate(st.session_state.temp_exceptions):
                st.text(f"{r[0]} - {r[1]}: {l}")
            if st.button("💾 Uložiť všetko"):
                for r, l in st.session_state.temp_exceptions:
                    c = r[0]
                    while c <= r[1]:
                        k = c.strftime('%Y-%m-%d')
                        st.session_state.config['closures'][k] = list(set(st.session_state.config['closures'].get(k, []) + l))
                        c += timedelta(days=1)
                st.session_state.temp_exceptions = []
                save_config(st.session_state.config)
                st.rerun()

    st.markdown("### Manuálne pridelenie izieb")
    manual_core_input = {}
    ward_docs = [d for d, p in st.session_state.config["lekari"].items() if "Oddelenie" in p.get("moze", []) and p.get("active")]
    cols = st.columns(2)
    for i, doc in enumerate(ward_docs):
        with cols[i % 2]:
            val = st.text_input(f"Dr {doc} – izby (napr. 1, 4):", key=f"core_{doc}")
            if val.strip():
                try:
                    manual_core_input[doc] = [int(p.strip()) for p in val.split(',') if p.strip().isdigit()]
                except: pass
    
    if manual_core_input:
        st.session_state.manual_core[start_d.strftime('%Y-%m-%d')] = manual_core_input

    c_btn1, c_btn2, c_btn3 = st.columns(3)
    gen_clicked = c_btn1.button("🚀 Generovať rozpis", type="primary")
    scan_clicked = c_btn2.button("🔭 Vyhliadka ďalších týždňov")
    clear_hist = c_btn3.button("🗑️ Reset histórie")
    weeks_num = st.number_input("Počet týždňov pre vyhliadku:", min_value=1, max_value=52, value=12)

    if gen_clicked:
        with st.spinner("..."):
            end_d = start_d + timedelta(days=14)
            ab = get_ical_events(datetime.combine(start_d, datetime.min.time()), datetime.combine(end_d, datetime.min.time()))
            ds, g, d, di = generate_data_structure(st.session_state.config, ab, start_d)
            st.session_state.df_display = create_display_df(ds, g, d, di, st.session_state.motto, st.session_state.config)
            st.session_state.df_display.columns = ["Sekcia / Dátum"] + ds
        st.success("Hotovo!")
    
    if scan_clicked:
        with st.spinner(f"Pozerám {weeks_num} týždňov dopredu..."):
            problems_df = scan_future_problems(st.session_state.config, weeks_ahead=weeks_num)
            if problems_df is not None and not problems_df.empty:
                st.subheader("🔭 Vyhliadka ďalších týždňov – problémové dni")
                st.dataframe(problems_df, use_container_width=True, hide_index=True)
            else:
                st.success("✅ V zadanom období nie sú žiadne neobsadené pracoviská.")

    if clear_hist:
        save_history({})
        st.success("História zmazaná")

    if 'df_display' in st.session_state:
        st.markdown("---")
        df = st.session_state.df_display.copy()
        df.iloc[0, 1:] = df.columns[1:]
        xlsx = create_excel_report(df)
        pdf = create_pdf_report(df, st.session_state.motto)
        fn = f"Rozpis_{df.columns[1]}_{df.columns[-1]}"
        c1, c2 = st.columns(2)
        c1.download_button("⬇️ XLSX", xlsx, f"{fn}.xlsx")
        c2.download_button("⬇️ PDF", pdf, f"{fn}.pdf", mime="application/pdf")
        
        with st.expander("📧 Email"):
            to = st.text_input("Komu:", st.session_state.config['email_settings']['default_to'])
            if st.button("Odoslať"):
                if send_email_with_pdf(pdf, f"{fn}.pdf", to, st.session_state.config['email_settings']['default_subject'], st.session_state.config['email_settings']['default_body']):
                    st.success("Odoslané")
        
        st.dataframe(st.session_state.df_display, use_container_width=True, hide_index=True)

elif mode == "⚙️ Nastavenia lekárov":
    st.header("Lekári")
    c1, c2 = st.columns([3, 1])
    n = c1.text_input("Meno:")
    if c2.button("Pridať") and n:
        st.session_state.config['lekari'][n] = {"moze": ["Oddelenie"], "active": True}
        save_config(st.session_state.config)
        st.rerun()
    
    for d, p in st.session_state.config['lekari'].items():
        with st.expander(d):
            a = st.checkbox("Aktívny", p.get('active', True), key=f"a_{d}")
            m = st.multiselect("Môže:", list(st.session_state.config['ambulancie'].keys())+["Oddelenie"], p.get('moze', []), key=f"m_{d}")
            if a!=p.get('active', True) or m!=p.get('moze', []):
                p['active'], p['moze'] = a, m
                save_config(st.session_state.config)

elif mode == "🏥 Nastavenia ambulancií":
    st.header("Ambulancie")
    sel = st.selectbox("Vyber:", list(st.session_state.config['ambulancie'].keys()))
    curr = st.session_state.config['ambulancie'][sel]
    if isinstance(curr['priority'], list):
        txt = st.text_area("Priority:", ", ".join(curr['priority']))
        if st.button("Uložiť"):
            curr['priority'] = [x.strip() for x in txt.split(',')]
            save_config(st.session_state.config)

elif mode == "📧 Nastavenia Emailu":
    st.header("Email")
    c = st.session_state.config['email_settings']
    t = st.text_input("To:", c.get('default_to', ''))
    s = st.text_input("Subject:", c.get('default_subject', ''))
    b = st.text_area("Body:", c.get('default_body', ''))
    if st.button("Uložiť"):
        st.session_state.config['email_settings'] = {"default_to": t, "default_subject": s, "default_body": b}
        save_config(st.session_state.config)
