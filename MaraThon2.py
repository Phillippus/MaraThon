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

# --- REPORTLAB PRE PDF + UNICODE ---
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import urllib.request

# --- KONFIGURÁCIA ---
CONFIG_FILE = 'hospital_config.json'
HISTORY_FILE = 'room_history.json'
PRIVATE_CALENDAR_URL = "https://calendar.google.com/calendar/ical/fntnonk%40gmail.com/private-e8ce4e0639a626387fff827edd26b87f/basic.ics"
GIST_FILENAME_CONFIG = "hospital_config_v10.json"
GIST_FILENAME_HISTORY = "room_history_v10.json"

ROOMS_LIST = [
    (1, 3), (2, 3), (3, 3), (4, 3), (5, 3),
    (7, 1), (8, 3), (9, 3), (10, 1), (11, 1),
    (12, 2), (13, 2), (14, 2), (15, 2), (16, 2), (17, 2),
    (18, 3), (19, 3)
]

SENIOR_DOCTORS = ["Kurisova", "Vidulin", "Miklatkova"]

# --- REGISTER UNICODE FONT PRE PDF ---
def setup_pdf_fonts():
    """Stiahne a zaregistruje DejaVu font pre PDF s unicode support"""
    font_dir = "/tmp"
    font_name = "DejaVuSans"
    font_path = os.path.join(font_dir, f"{font_name}.ttf")
    
    try:
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            return font_name
    except:
        pass
    
    if not os.path.exists(font_path):
        try:
            font_url = "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/ttf/DejaVuSans.ttf"
            urllib.request.urlretrieve(font_url, font_path)
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            return font_name
        except:
            pass
    
    return "Helvetica"

# --- GIST ULOŽISKO ---
def get_gist_id(filename):
    if "github" not in st.secrets:
        return None
    try:
        token = st.secrets["github"]["token"]
        headers = {"Authorization": f"token {token}"}
        resp = requests.get("https://api.github.com/gists", headers=headers)
        resp.raise_for_status()
        for gist in resp.json():
            if filename in gist['files']:
                return gist['id']
    except:
        pass
    return None

def load_data_from_gist(filename):
    if "github" not in st.secrets:
        return None
    gist_id = get_gist_id(filename)
    if not gist_id:
        return None
    try:
        token = st.secrets["github"]["token"]
        headers = {"Authorization": f"token {token}"}
        resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=headers)
        resp.raise_for_status()
        content = resp.json()['files'][filename]['content']
        return json.loads(content)
    except:
        return None

def save_data_to_gist(filename, data):
    if "github" not in st.secrets:
        return
    try:
        token = st.secrets["github"]["token"]
        headers = {"Authorization": f"token {token}"}
        gist_id = get_gist_id(filename)
        payload = {
            "description": f"Storage for {filename}",
            "public": False,
            "files": {
                filename: {"content": json.dumps(data, ensure_ascii=False, indent=2)}
            }
        }
        if gist_id:
            requests.patch(f"https://api.github.com/gists/{gist_id}", json=payload, headers=headers)
        else:
            requests.post("https://api.github.com/gists", json=payload, headers=headers)
    except:
        pass

def _load_data(gist_filename, local_filename, default_factory):
    data = load_data_from_gist(gist_filename)
    if data is not None:
        return data
    if os.path.exists(local_filename):
        try:
            with open(local_filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return default_factory()

def load_config():
    config = _load_data(GIST_FILENAME_CONFIG, CONFIG_FILE, get_default_config)
    config, changed = migrate_homolova_to_vidulin(config)
    if 'closures' not in config:
        config['closures'] = {}
        changed = True
    if 'email_settings' not in config:
        config['email_settings'] = {
            "default_to": "",
            "default_subject": "Rozpis služieb",
            "default_body": "Dobrý deň,\nv prílohe rozpis.\nS pozdravom"
        }
        changed = True
    
    if "Prijmova" in config.get("ambulancie", {}):
        config["ambulancie"]["Konziliarna"] = config["ambulancie"].pop("Prijmova")
        for doc, props in config.get("lekari", {}).items():
            if "moze" in props:
                props["moze"] = ["Konziliarna" if x == "Prijmova" else x for x in props["moze"]]
            if "pevne_dni" in props:
                for day, amb in props["pevne_dni"].items():
                    if amb == "Prijmova":
                        props["pevne_dni"][day] = "Konziliarna"
        changed = True

    if "Chemo 8B" in config.get("ambulancie", {}):
        prio = config["ambulancie"]["Chemo 8B"].get("priority")
        if isinstance(prio, dict):
             config["ambulancie"]["Chemo 8B"]["priority"] = prio.get("default", ["Riedlova", "Kohutek", "Stratena", "Bystricky", "Vidulin", "Blahova"])
             changed = True

    if changed:
        save_config(config)
    return config

def load_history():
    return _load_data(GIST_FILENAME_HISTORY, HISTORY_FILE, lambda: {})

def save_config(config):
    try: 
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except:
        pass
    save_data_to_gist(GIST_FILENAME_CONFIG, config)

def save_history(history):
    try: 
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except:
        pass
    save_data_to_gist(GIST_FILENAME_HISTORY, history)

def get_default_config():
    return {
        "total_beds": 42,
        "closures": {}, 
        "email_settings": {
            "default_to": "",
            "default_subject": "Rozpis služieb",
            "default_body": "Dobrý deň,\nv prílohe rozpis.\nS pozdravom"
        },
        "ambulancie": {
            "Konziliarna": { 
                "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"],
                "priority": ["Kohutekova", "Kohutek", "Bystricky", "Zavrelova"]
            },
            "Velka dispenzarna": {
                "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"],
                "priority": ["Bocak", "Stratena", "Vidulin", "Kurisova", "Blahova", "Hrabosova", "Miklatkova", "Martinka"]
            },
            "Mala dispenzarna": {
                "dni": ["Pondelok", "Piatok"],
                "priority": ["Spanik", "Stratena", "Vidulin", "Kurisova", "Blahova", "Hrabosova", "Miklatkova"]
            },
            "Radio 2A": {
                "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"],
                "priority": ["Zavrelova", "Kohutek", "Kurisova", "Miklatkova", "Bystricky"],
                "check_presence": ["Zavrelova", "Martinka"]
            },
            "Radio 2B": {
                "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"],
                "priority": ["Martinka"],
                "conditional_owner": "Martinka"
            },
            "Chemo 8A": {
                "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"],
                "priority": ["Hatalova", "Kohutek", "Stratena", "Bystricky"]
            },
            "Chemo 8B": {
                "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"],
                "priority": ["Riedlova", "Kohutek", "Stratena", "Bystricky", "Vidulin", "Blahova"]
            },
            "Chemo 8C": {
                "dni": ["Utorok", "Streda", "Stvrtok"],
                "priority": ["Stratena", "Kohutek", "Bystricky", "Vidulin", "Blahova"]
            },
            "Wolf": {
                "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"],
                "priority": ["Spanik", "Miklatkova", "Kurisova", "Kohutek"]
            }
        },
        "lekari": {
            "Bystricky": {
                "moze": ["Konziliarna", "Velka dispenzarna", "Mala dispenzarna", "Radio 2A", "Chemo 8A", "Chemo 8B", "Chemo 8C", "Wolf"],
                "active": True
            },
            "Kohutek": {
                "moze": ["Oddelenie", "Konziliarna", "Velka dispenzarna", "Mala dispenzarna", "Radio 2A", "Chemo 8A", "Chemo 8B", "Chemo 8C", "Wolf"],
                "pevne_dni": {"Pondelok": "Chemo 8B", "Utorok": "Chemo 8B"},
                "active": True
            },
            "Kohutekova": {
                "moze": ["Konziliarna"],
                "pevne_dni": {"Pondelok": "Konziliarna", "Utorok": "Konziliarna", "Streda": "Konziliarna", "Stvrtok": "Konziliarna"},
                "nepracuje": ["Piatok"],
                "active": True
            },
            "Riedlova": {
                "moze": ["Chemo 8B"],
                "pevne_dni": {"Streda": "Chemo 8B", "Stvrtok": "Chemo 8B"},
                "nepracuje": ["Pondelok", "Utorok"],
                "active": True
            },
            "Zavrelova": {
                "moze": ["Radio 2A", "Konziliarna"],
                "pevne_dni": {"Pondelok": "Radio 2A", "Utorok": "Radio 2A", "Streda": "Radio 2A", "Stvrtok": "Radio 2A", "Piatok": "Radio 2A"},
                "active": True
            },
            "Martinka": {
                "moze": ["Radio 2B", "Oddelenie", "Velka dispenzarna"],
                "pevne_dni": {"Pondelok": "Radio 2B", "Utorok": "Radio 2B", "Streda": "Radio 2B", "Stvrtok": "Radio 2B", "Piatok": "Radio 2B"},
                "active": True
            },
            "Hatalova": {
                "moze": ["Chemo 8A"],
                "pevne_dni": {"Pondelok": "Chemo 8A", "Utorok": "Chemo 8A", "Streda": "Chemo 8A", "Stvrtok": "Chemo 8A", "Piatok": "Chemo 8A"},
                "active": True
            },
            "Stratena": {
                "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna", "Chemo 8A", "Chemo 8B", "Chemo 8C"],
                "pevne_dni": {"Utorok": "Chemo 8C", "Streda": "Chemo 8C", "Stvrtok": "Chemo 8C"},
                "active": True
            },
            "Vidulin": {
                "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna", "Chemo 8A", "Chemo 8B", "Chemo 8C"],
                "active": True
            },
            "Miklatkova": {
                "moze": ["Oddelenie", "Wolf"],
                "active": True
            },
            "Kurisova": {
                "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna", "Radio 2A", "Wolf"],
                "special": "veduca",
                "active": True
            },
            "Blahova": {
                "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna", "Chemo 8B", "Chemo 8C"],
                "active": False
            },
            "Hrabosova": {
                "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna"],
                "active": False,
                "extra_dni": []
            },
            "Bocak": {
                "moze": ["Velka dispenzarna"],
                "pevne_dni": {"Pondelok": "Velka dispenzarna", "Utorok": "Velka dispenzarna", "Streda": "Velka dispenzarna", "Stvrtok": "Velka dispenzarna", "Piatok": "Velka dispenzarna"},
                "active": True
            },
            "Spanik": {
                "moze": ["Wolf", "Mala dispenzarna"],
                "pevne_dni": {"Pondelok": "Mala dispenzarna", "Utorok": "Wolf", "Streda": "Wolf", "Stvrtok": "Wolf", "Piatok": "Mala dispenzarna"},
                "active": True
            },
            "Kacurova": {
                "moze": ["Oddelenie"],
                "active": True
            },
            "Hunakova": {
                "moze": ["Oddelenie"],
                "active": True
            }
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

def distribute_rooms(doctors_list, wolf_doc_name, previous_assignments=None, manual_core=None):
    """
    Spravodlivá distribúcia izieb s obmedzenou kontinuitou.
    Cieľ: Aby sa izby rozdelili rovnomerne aj keď niekto príde z dovolenky.
    Mechanizmus: Kontinuita je povolená len do výšky priemerného počtu lôžok.
    Zvyšok sa rozdelí tým, čo majú najmenej.
    """
    if not doctors_list:
        return {}, {}
    if manual_core is None:
        manual_core = {}
    if previous_assignments is None:
        previous_assignments = {}
    
    # Identifikácia rolí
    head_doc = "Kurisova" if "Kurisova" in doctors_list else ("Miklatkova" if "Miklatkova" in doctors_list else None)
    rt_help_doc = "Miklatkova" if "Miklatkova" in doctors_list else None
    
    assignment = {d: [] for d in doctors_list}
    current_beds = {d: 0 for d in doctors_list}
    available_rooms = sorted(ROOMS_LIST, key=lambda x: x[0]) 
    
    # --- 1. Manuálne pridelenie (Core) ---
    for doc, nums in manual_core.items():
        if doc not in doctors_list: continue
        for num in nums:
            r_obj = next((r for r in available_rooms if r[0] == num), None)
            if not r_obj: continue
            assignment[doc].append(r_obj)
            current_beds[doc] += r_obj[1]
            available_rooms.remove(r_obj)
    
    # Definícia aktívnych prijímateľov izieb
    active_assignees = [d for d in doctors_list]
    pure_workers = [d for d in doctors_list if d not in ["Kurisova", "Kohutek"]]
    num_workers = len(pure_workers)
    
    if num_workers >= 2 and head_doc in active_assignees and head_doc != rt_help_doc:
        active_assignees.remove(head_doc)
    
    if not active_assignees: 
        active_assignees = doctors_list

    # --- DEFINÍCIA LIMITOV (CAPS) ---
    caps = {}
    for d in active_assignees:
        if d == rt_help_doc or d == wolf_doc_name:
            caps[d] = 12
        else:
            caps[d] = 100 

    # --- VÝPOČET PRIEMERNÉHO ZAŤAŽENIA (FAIR SHARE) ---
    full_time_docs = [d for d in active_assignees if caps[d] > 12]
    active_full_time_count = len(full_time_docs)
    if active_full_time_count == 0: active_full_time_count = 1
    
    total_beds_total = sum(r[1] for r in ROOMS_LIST)
    
    # Priemerný počet lôžok na jedného "plného" lekára
    # Ak je 42 lôžok a 3 lekári, average_load = 14.
    average_load = total_beds_total / active_full_time_count
    
    # Soft limit pre kontinuitu = priemer + malá tolerancia (napr. 1 lôžko)
    # Ak má lekár z minulosti 20 lôžok, algoritmus mu dovolí nechať si len cca 15.
    # Zvyšných 5 mu vezme, aby ich mohol dať tomu, čo prišiel z dovolenky.
    soft_continuity_limit = average_load + 1.0

    # --- 2. Kontinuita (zachovanie izieb z minulosti) s OBMEDZENÍM ---
    if previous_assignments:
        for doc in active_assignees:
            if doc in previous_assignments:
                my_prev_rooms = []
                for r_num in previous_assignments[doc]:
                    r_obj = next((r for r in available_rooms if r[0] == r_num), None)
                    if r_obj:
                        my_prev_rooms.append(r_obj)
                
                my_prev_rooms.sort(key=lambda x: x[0])
                
                for r_obj in my_prev_rooms:
                    hard_limit = caps.get(doc, 100)
                    
                    # KĽÚČOVÁ ZMENA:
                    # Izbu priradíme, len ak tým neprekročíme ani Hard Limit, ani Soft Continuity Limit.
                    if (current_beds[doc] + r_obj[1] <= hard_limit) and \
                       (current_beds[doc] + r_obj[1] <= soft_continuity_limit):
                        assignment[doc].append(r_obj)
                        current_beds[doc] += r_obj[1]
                        available_rooms.remove(r_obj)
                    else:
                        # Izba sa uvoľní do obehu pre tých, čo majú málo (napr. po dovolenke)
                        pass 

    # --- 3. Rozdelenie zvyšných izieb (Fair Share) ---
    while available_rooms:
        # Kandidáti sú tí, ktorí nemajú plno
        candidates = [d for d in active_assignees if current_beds[d] < caps.get(d, 100)]
        
        if not candidates:
             candidates = active_assignees

        # VYLEPŠENÝ SORT PRE SPRAVODLIVOSŤ:
        # 1. Priorita: Kto má najmenej lôžok (current_beds)
        # 2. Priorita: Abecedne (len aby to bolo deterministické)
        # Týmto sa zabezpečí, že ten, kto prišiel z dovolenky (má 0), bude dostávať izby ako prvý,
        # až kým nedobehne ostatných.
        candidates.sort(key=lambda d: (current_beds[d], d))
        
        target_doc = candidates[0]
        
        best_room = None
        beds_left = caps.get(target_doc, 100) - current_beds[target_doc]
        fitting_rooms = [r for r in available_rooms if r[1] <= beds_left]
        
        # Ak sa nezmestí žiadna izba pod limit
        if not fitting_rooms and caps.get(target_doc, 100) < 100:
             # Skúsime druhého v poradí
             if len(candidates) > 1:
                 target_doc = candidates[1]
                 beds_left = caps.get(target_doc, 100) - current_beds[target_doc]
                 fitting_rooms = [r for r in available_rooms if r[1] <= beds_left]
             
             # Ak stále nič a limit je mäkký (100), vezmeme hocičo
             if not fitting_rooms and caps.get(target_doc, 100) == 100:
                 fitting_rooms = available_rooms

        if not fitting_rooms:
            # Ak sa už nikomu nič nezmestí pod limity (RT/Wolf), musíme to niekomu dať "nasilu"
            # alebo to ostane neobsadené (čo nechceme). Dáme to tomu s najväčšou kapacitou.
            fitting_rooms = available_rooms
            # Preistotu preusporiadame kandidátov na tých s full kapacitou
            full_cap_candidates = [d for d in candidates if caps[d] >= 100]
            if full_cap_candidates:
                target_doc = min(full_cap_candidates, key=lambda d: current_beds[d])

        if assignment[target_doc]:
            my_room_nums = [r[0] for r in assignment[target_doc]]
            avg_pos = sum(my_room_nums) / len(my_room_nums)
            best_room = min(fitting_rooms, key=lambda r: abs(r[0] - avg_pos))
        else:
            best_room = fitting_rooms[0]

        assignment[target_doc].append(best_room)
        current_beds[target_doc] += best_room[1]
        available_rooms.remove(best_room)

    # --- Generovanie výstupu ---
    result_text, result_raw = {}, {}
    for doc in doctors_list:
        rooms = sorted(assignment[doc], key=lambda x: x[0])
        result_raw[doc] = [r[0] for r in rooms]
        
        room_str = ", ".join([str(r[0]) for r in rooms])
        
        suffix = ""
        if doc == wolf_doc_name:
             suffix = " + Wolf"
        elif doc == head_doc:
             suffix = " + RT oddelenie"
        elif doc == rt_help_doc: 
             suffix = " + RT oddelenie"
             
        if not rooms:
             if doc == wolf_doc_name: result_text[doc] = "Wolf (0L)"
             elif doc == head_doc and num_workers >= 3: result_text[doc] = "RT oddelenie"
             elif doc == rt_help_doc: result_text[doc] = "RT oddelenie (0L)"
             else: result_text[doc] = ""
        else:
             result_text[doc] = f"{room_str}{suffix}"
             
    return result_text, result_raw

def get_ical_events(start_date, end_date):
    try:
        response = requests.get(PRIVATE_CALENDAR_URL)
        response.raise_for_status()
        c = Calendar(response.text)
        absences = {}
        for event in c.events:
            ev_start, ev_end = event.begin.date(), event.end.date()
            if ev_end < start_date.date() or ev_start > end_date.date():
                continue
            
            raw = event.name.strip()
            name, typ = raw, "Dovolenka"
            
            if raw.upper().endswith('PN'):
                typ, name = "PN", raw[:-2].rstrip(' -')
            elif raw.upper().endswith('VZ'):
                typ, name = "Vzdelávanie", raw[:-2].rstrip(' -')
            elif raw.upper().endswith('S') and not raw.upper().endswith('OS'):
                typ, name = "Stáž", raw[:-1].rstrip(' -')
            elif '-' in raw and typ == "Dovolenka":
                parts = raw.split('-')
                name = parts[0].strip()
                suffix = parts[1].strip().upper() if len(parts) > 1 else ""
                if suffix == 'S': typ = "Stáž"
                elif suffix == 'PN': typ = "PN"
                elif suffix == 'VZ': typ = "Vzdelávanie"
            
            curr, limit = max(ev_start, start_date.date()), min(ev_end, end_date.date())
            while curr < limit:
                absences.setdefault(curr.strftime('%Y-%m-%d'), {})[name] = typ
                curr += timedelta(days=1)
        return absences
    except:
        return {}

def generate_data_structure(config, absences, start_date, save_hist=True):
    days_map = {0: "Pondelok", 1: "Utorok", 2: "Streda", 3: "Stvrtok", 4: "Piatok"}
    weekday = start_date.weekday()
    thursday = start_date + timedelta(days=(3 - weekday) % 7)
    
    dates, data_grid = [], {}
    
    all_doctors = []
    doctors_info = {}

    week_dates_str = []
    for i in range(7):
        d = thursday + timedelta(days=i)
        if d.weekday() < 5:
            week_dates_str.append(d.strftime('%Y-%m-%d'))

    for d_name, props in config['lekari'].items():
        is_active = props.get('active', True)
        extra_days = props.get('extra_dni', [])
        has_extra_in_week = any(ed in week_dates_str for ed in extra_days)
        
        if is_active or has_extra_in_week:
            all_doctors.append(d_name)
            if not is_active and has_extra_in_week:
                readable_days = []
                for ed in extra_days:
                    if ed in week_dates_str:
                        dt = datetime.strptime(ed, '%Y-%m-%d')
                        readable_days.append(dt.strftime('%d.%m.'))
                doctors_info[d_name] = f"⚠️ len {', '.join(readable_days)}"

    all_doctors = sorted(all_doctors)
    history = load_history()
    day_before_str = (thursday - timedelta(days=1)).strftime('%Y-%m-%d')
    last_day_assignments = history.get(day_before_str, {})
    manual_all = st.session_state.get("manual_core", {})
    closures = config.get('closures', {})
    
    for i in range(7):
        curr_date = thursday + timedelta(days=i)
        day_name = days_map.get(curr_date.weekday())
        if not day_name:
            continue
        
        date_str = curr_date.strftime('%d.%m.%Y')
        date_key = curr_date.strftime('%Y-%m-%d')
        dates.append(date_str)
        day_absences = absences.get(date_key, {})
        closed_today = closures.get(date_key, [])
        data_grid[date_str] = {}
        
        available = []
        for d in all_doctors:
            props = config['lekari'][d]
            is_normally_active = props.get('active', True)
            has_extra_today = date_key in props.get('extra_dni', [])
            
            if not is_normally_active and not has_extra_today: continue
            if d in day_absences: continue
            if day_name in props.get('nepracuje', []): continue
            available.append(d)

        assigned_amb = {}
        
        for doc in list(available):
            if fixed := config['lekari'][doc].get('pevne_dni', {}).get(day_name):
                for t in [t.strip() for t in fixed.split(',')]:
                    if t in closed_today:
                        assigned_amb[t] = "ZATVORENÉ"
                    else:
                        assigned_amb[t] = doc
                available.remove(doc)
        
        ambs_to_process = ["Radio 2A", "Radio 2B", "Chemo 8B", "Chemo 8A", "Chemo 8C", "Wolf", "Konziliarna", "Velka dispenzarna", "Mala dispenzarna"]
        amb_scarcity = []

        for amb_name in ambs_to_process:
            if amb_name in assigned_amb: continue
            if amb_name in closed_today:
                assigned_amb[amb_name] = "ZATVORENÉ"
                continue
            
            amb_info = config['ambulancie'][amb_name]
            if day_name not in amb_info['dni']:
                assigned_amb[amb_name] = "---"
                continue

            if amb_name == "Radio 2B" and "Martinka" not in available:
                assigned_amb[amb_name] = "ZATVORENÉ"
                continue

            prio_list = amb_info['priority']
            if isinstance(prio_list, dict):
                prio_list = prio_list.get(str(curr_date.weekday()), prio_list.get('default', []))
            
            candidates = [doc for doc in prio_list if doc in available and amb_name in config['lekari'][doc].get('moze', [])]
            amb_scarcity.append({
                "name": amb_name,
                "candidates": candidates,
                "count": len(candidates),
                "original_index": ambs_to_process.index(amb_name)
            })
        
        amb_scarcity.sort(key=lambda x: (x['count'], x['original_index']))
        
        for item in amb_scarcity:
            amb_name = item['name']
            current_candidates = [c for c in item['candidates'] if c in available]
            
            if amb_name == "Wolf":
                if "Spanik" in all_doctors and "Spanik" not in day_absences:
                     if assigned_amb.get("Mala dispenzarna") == "Spanik":
                        assigned_amb["Wolf"] = "Spanik"
                        continue

            if not current_candidates:
                assigned_amb[amb_name] = "NEOBSADENÉ"
                continue
            
            chosen_doc = current_candidates[0]
            assigned_amb[amb_name] = chosen_doc
            available.remove(chosen_doc)

        for amb, val in assigned_amb.items():
            data_grid[date_str][amb] = val
        
        wolf_doc = assigned_amb.get("Wolf")
        
        if "ODDELENIE (Celé)" in closed_today:
            room_text_map, room_raw_map = {}, {}
            for doc in all_doctors:
                if doc in day_absences: continue
                if doc in assigned_amb.values(): continue
                if "Oddelenie" in config['lekari'][doc].get('moze', []):
                    room_text_map[doc] = "ZATVORENÉ"
        else:
            ward_candidates = [d for d in available if "Oddelenie" in config['lekari'][d].get('moze', [])]
            if wolf_doc and wolf_doc not in ward_candidates and "Oddelenie" in config['lekari'].get(wolf_doc, {}).get('moze', []):
                ward_candidates.append(wolf_doc)
            
            manual_for_day = manual_all.get(start_date.strftime('%Y-%m-%d'), {})
            room_text_map, room_raw_map = distribute_rooms(ward_candidates, wolf_doc, last_day_assignments, manual_for_day)
            last_day_assignments = room_raw_map
            if save_hist:
                history[date_key] = room_raw_map
        
        for doc in all_doctors:
            props = config['lekari'][doc]
            is_active = props.get('active', True)
            has_extra = date_key in props.get('extra_dni', [])
            
            if not is_active and not has_extra:
                data_grid[date_str][doc] = ""
                continue

            if doc in day_absences:
                data_grid[date_str][doc] = day_absences[doc]
            elif doc in room_text_map:
                data_grid[date_str][doc] = room_text_map[doc]
            else:
                my_ambs = [a for a, d in assigned_amb.items() if d == doc]
                data_grid[date_str][doc] = " + ".join(my_ambs) if my_ambs else ""
        
        if save_hist:
            save_history(history)
    
    return dates, data_grid, all_doctors, doctors_info

def create_display_df(dates, data_grid, all_doctors, doctors_info, motto, config):
    rows = []
    ward_doctors = [d for d in all_doctors if "Oddelenie" in config['lekari'][d].get('moze', [])]
    
    display_map = {
        "Radio 2A": "Radio 2A",
        "Konziliarna": "Konziliárna amb.", 
        "Velka dispenzarna": "veľký dispenzár",
        "Mala dispenzarna": "malý dispenzár"
    }
    
    rows.append(["Oddelenie"] + dates)
    for doc in ward_doctors:
        vals = []
        for date in dates:
            val = data_grid[date].get(doc, "")
            for old, new in display_map.items():
                val = val.replace(old, new)
            vals.append(val)
        
        doc_label = f"Dr {doc}"
        if doc in doctors_info:
            doc_label += f" {doctors_info[doc]}"
        
        rows.append([doc_label] + vals)
    
    rows.append([motto or "Motto"] + [""] * len(dates))
    
    sections = [
        ("Konziliárna amb", ["Konziliarna"]), 
        ("RT ambulancie", ["Radio 2A", "Radio 2B"]),
        ("Chemo amb", ["Chemo 8A", "Chemo 8B", "Chemo 8C"]),
        ("Disp. Ambulancia", ["Velka dispenzarna", "Mala dispenzarna"]),
        ("RTG Terapia", ["Wolf"])
    ]
    
    for title, amb_list in sections:
        rows.append([title] + dates)
        for amb in amb_list:
            display_name = display_map.get(amb, amb)
            vals = []
            for date in dates:
                val = data_grid[date].get(amb, "")
                val = val.replace("---", "").replace("NEOBSADENÉ", "???")
                vals.append(val)
            rows.append([display_name] + vals)
        rows.append([""] * (len(dates) + 1))
    
    return pd.DataFrame(rows)

def create_excel_report(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="Rozpis")
        ws = writer.sheets['Rozpis']
        bold_font = Font(bold=True)
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        
        ws.cell(row=1, column=1, value=f"Rozpis prác Onkologická klinika {df.columns[1]} - {df.columns[-1]}").font = bold_font
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(df.columns))
        ws['A1'].alignment = center_align
        
        for r_idx, row in enumerate(df.iterrows(), 2):
            is_header = row[1][0] in ["Oddelenie", "Konziliárna amb", "RT ambulancie", "Chemo amb", "Disp. Ambulancia", "RTG Terapia"]
            is_motto = (row[1][0] == st.session_state.get('motto', 'Motto'))
            
            for c_idx, value in enumerate(row[1], 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=value)
                cell.border = thin_border
                cell.alignment = center_align
                if is_header or (c_idx==1 and not is_motto):
                    cell.font = bold_font
                if is_motto:
                    ws.merge_cells(start_row=r_idx, start_column=1, end_row=r_idx, end_column=len(df.columns))
                    cell.font = Font(bold=True, italic=True)
                    cell.fill = PatternFill(start_color="EEEEEE", end_color="EEEEEE", fill_type="solid")
                    break
        
        ws.column_dimensions['A'].width = 25
        for i in range(2, len(df.columns) + 1):
            ws.column_dimensions[get_column_letter(i)].width = 18
    
    return output.getvalue()

def create_pdf_report(df, motto):
    """Generuje PDF s unicode podporou pre slovenčinu, zalomením textu a tesnejším rozložením"""
    buffer = io.BytesIO()
    
    font_name = setup_pdf_fonts()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=10, 
        leftMargin=10, 
        topMargin=10, 
        bottomMargin=10
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontName=font_name,
        fontSize=12,
        alignment=1, # Center
        spaceAfter=10
    )
    
    cell_style = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=7,        # Zmenšené písmo
        leading=8,         # Menší riadkovanie
        alignment=1        # Center
    )
    
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=8,
        leading=9,
        alignment=1,
        textColor=colors.whitesmoke
    )

    section_style = ParagraphStyle(
        'SectionStyle',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=8,
        leading=9,
        alignment=1,
        textColor=colors.black
    )
    
    title_text = f"Rozpis prác Onkologická klinika {df.columns[1]} - {df.columns[-1]}"
    elements.append(Paragraph(title_text, title_style))
    
    data = []
    header_row = [Paragraph(str(col), section_style) for col in df.columns]
    data.append(header_row)
    
    for idx, row in df.iterrows():
        row_data = []
        row_label = str(row[0])
        is_section_header = row_label in ["Oddelenie", "Konziliárna amb", "RT ambulancie", "Chemo amb", "Disp. Ambulancia", "RTG Terapia"]
        is_motto = (row_label == (motto or "Motto"))
        
        for i, val in enumerate(row.values):
            txt = str(val) if val is not None else ""
            
            if is_section_header:
                p = Paragraph(txt, section_style)
            elif is_motto:
                if i == 0:
                     p = Paragraph(txt, ParagraphStyle('Motto', parent=cell_style, fontName=font_name, fontSize=8, padding=5))
                else:
                     p = "" 
            elif i == 0:
                 p = Paragraph(f"<b>{txt}</b>", cell_style)
            else:
                 p = Paragraph(txt, cell_style)
                 
            row_data.append(p)
        data.append(row_data)
    
    available_width = 820
    col_widths = [available_width * 0.16] + [available_width * 0.168] * (len(df.columns) - 1)
    
    t = Table(data, colWidths=col_widths)
    
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ])
    
    for i, row in enumerate(df.iterrows()):
        table_row_idx = i + 1
        row_val = row[1][0]
        
        if row_val in ["Oddelenie", "Konziliárna amb", "RT ambulancie", "Chemo amb", "Disp. Ambulancia", "RTG Terapia"]:
            style.add('BACKGROUND', (0, table_row_idx), (-1, table_row_idx), colors.lightgrey)
        
        if row_val == (motto or "Motto"):
            style.add('SPAN', (0, table_row_idx), (-1, table_row_idx))
            style.add('BACKGROUND', (0, table_row_idx), (-1, table_row_idx), colors.whitesmoke)

    t.setStyle(style)
    elements.append(t)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

def send_email_with_pdf(pdf_bytes, filename, to_email, subject, body):
    if "email" not in st.secrets:
        st.error("Chýbajú nastavenia emailu")
        return False
    
    from_email = st.secrets["email"]["username"]
    password = st.secrets["email"]["password"]
    
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    part = MIMEBase('application', 'octet-stream')
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename={filename}')
    msg.attach(part)
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_email, password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Chyba: {e}")
        return False

# Pomocná funkcia na zoskupenie dátumov do intervalov
def group_closures_to_intervals(closures_dict):
    """
    Vstup: {'2025-12-24': ['A', 'B'], '2025-12-25': ['A', 'B'], '2025-12-26': ['A', 'C']}
    Výstup: [
       (start, end, ['A', 'B']),
       (start, end, ['A', 'C'])
    ]
    """
    sorted_dates = sorted(closures_dict.keys())
    if not sorted_dates:
        return []
        
    intervals = []
    current_start = sorted_dates[0]
    current_end = sorted_dates[0]
    current_val = sorted(closures_dict[sorted_dates[0]])
    
    for date_str in sorted_dates[1:]:
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
        prev_d = datetime.strptime(current_end, '%Y-%m-%d').date()
        val = sorted(closures_dict[date_str])
        
        # Ak je deň nasledujúci a hodnota je rovnaká -> predĺž interval
        if (d - prev_d).days == 1 and val == current_val:
            current_end = date_str
        else:
            intervals.append((current_start, current_end, current_val))
            current_start = date_str
            current_end = date_str
            current_val = val
            
    intervals.append((current_start, current_end, current_val))
    return intervals

st.set_page_config(page_title="Rozpis FN Trenčín", layout="wide")
st.title("🏥 Rozpis prác - Onkologická klinika FN Trenčín")

if 'config' not in st.session_state:
    st.session_state.config = load_config()

if 'manual_core' not in st.session_state:
    st.session_state.manual_core = {}

# Inicializácia session state pre dynamické formuláre
if 'temp_exceptions' not in st.session_state:
    st.session_state.temp_exceptions = []

mode = st.sidebar.radio("Navigácia", ["🚀 Generovať rozpis", "⚙️ Nastavenia lekárov", "🏥 Nastavenia ambulancií", "📧 Nastavenia Emailu"])

if mode == "🚀 Generovať rozpis":
    c1, c2 = st.columns([2, 2])
    st.session_state.motto = c1.text_input("📢 Motto týždňa:", placeholder="Sem napíšte motto...")
    start_d = c2.date_input("Začiatok rozpisu:", datetime.now())

    with st.expander("📅 Výnimky a zatváranie", expanded=True):
        st.info("Tu môžete nastaviť dni, kedy sú ambulancie alebo celé oddelenie zatvorené.")
        
        # --- ZOBRAZENIE ULOŽENÝCH VÝNIMIEK Z CONFIGU ---
        if 'closures' in st.session_state.config and st.session_state.config['closures']:
            st.markdown("##### 💾 Aktívne výnimky v databáze:")
            stored_intervals = group_closures_to_intervals(st.session_state.config['closures'])
            
            for start_s, end_s, closed_list in stored_intervals:
                c_s1, c_s2, c_s3 = st.columns([2, 4, 1])
                
                # Formátovanie dátumu
                d1 = datetime.strptime(start_s, '%Y-%m-%d')
                d2 = datetime.strptime(end_s, '%Y-%m-%d')
                date_label = f"{d1.strftime('%d.%m.%Y')} - {d2.strftime('%d.%m.%Y')}" if start_s != end_s else d1.strftime('%d.%m.%Y')
                
                # Formátovanie zoznamu
                all_ambs = list(st.session_state.config['ambulancie'].keys())
                all_ambs.append("ODDELENIE (Celé)")
                if len(closed_list) >= len(all_ambs):
                    closed_label = "🔴 VŠETKO ZATVORENÉ"
                elif "ODDELENIE (Celé)" in closed_list and len(closed_list) >= len(all_ambs) - 1:
                    closed_label = "🔴 ODDELENIE + VŠETKY AMB"
                else:
                    closed_label = ", ".join(closed_list)
                
                c_s1.text(f"🗓️ {date_label}")
                c_s2.markdown(f"**{closed_label}**")
                
                if c_s3.button("🗑️ Zmazať", key=f"del_stored_{start_s}_{end_s}"):
                    # Vymazať dni z configu
                    curr = d1
                    while curr <= d2:
                        k = curr.strftime('%Y-%m-%d')
                        if k in st.session_state.config['closures']:
                            del st.session_state.config['closures'][k]
                        curr += timedelta(days=1)
                    save_config(st.session_state.config)
                    st.rerun()

        # --- SEKICIA PRE NOVÉ VÝNIMKY (TEMP) ---
        st.markdown("---")
        st.markdown("##### Pridať nové výnimky:")
        
        # Zobrazenie temp výnimiek
        indices_to_remove = []
        for i, (d_range, closed_items) in enumerate(st.session_state.temp_exceptions):
            c_show1, c_show2, c_show3 = st.columns([2, 3, 1])
            d_start_s = d_range[0].strftime('%d.%m.')
            d_end_s = d_range[1].strftime('%d.%m.%Y') if len(d_range) > 1 else ""
            label_date = f"{d_start_s} - {d_end_s}" if d_end_s else d_start_s
            
            c_show1.text(f"🆕 {label_date}")
            c_show2.text(f"🔒 {', '.join(closed_items)}")
            if c_show3.button("❌", key=f"del_temp_{i}"):
                indices_to_remove.append(i)
        
        for idx in sorted(indices_to_remove, reverse=True):
            st.session_state.temp_exceptions.pop(idx)
        
        # Formulár
        c_ex1, c_ex2 = st.columns([1, 2])
        new_range = c_ex1.date_input("Nový rozsah dátumov:", value=[], key="new_ex_range")
        amb_options = ["ODDELENIE (Celé)"] + list(st.session_state.config['ambulancie'].keys())
        new_closed = c_ex2.multiselect("Čo zatvoriť v tomto termíne?", options=amb_options, key="new_ex_closed")
        
        if st.button("➕ Pridať do zoznamu"):
            if new_range and new_closed:
                r = (new_range[0], new_range[1]) if len(new_range) > 1 else (new_range[0], new_range[0])
                st.session_state.temp_exceptions.append((r, new_closed))
                st.rerun() 
            elif not new_range:
                st.warning("Vyberte dátum.")
            elif not new_closed:
                st.warning("Vyberte čo má byť zatvorené.")

        # Uloženie
        if st.session_state.temp_exceptions:
            st.markdown("---")
            if st.button("💾 Uložiť nové výnimky do databázy", type="primary"):
                if 'closures' not in st.session_state.config:
                    st.session_state.config['closures'] = {}
                
                count = 0
                for d_range, closed_items in st.session_state.temp_exceptions:
                    curr = d_range[0]
                    end = d_range[1]
                    while curr <= end:
                        d_key = curr.strftime('%Y-%m-%d')
                        if d_key in st.session_state.config['closures']:
                            existing = set(st.session_state.config['closures'][d_key])
                            new_ones = set(closed_items)
                            merged = list(existing.union(new_ones))
                            st.session_state.config['closures'][d_key] = merged
                        else:
                            st.session_state.config['closures'][d_key] = closed_items
                        curr += timedelta(days=1)
                        count += 1
                
                save_config(st.session_state.config)
                st.session_state.temp_exceptions = [] 
                st.success(f"✅ Uložené! Výnimky boli aktualizované.")
                st.rerun()

    st.markdown("### Manuálne pridelenie izieb")
    manual_core_input = {}
    ward_docs = [d for d, p in st.session_state.config["lekari"].items() if "Oddelenie" in p.get("moze", []) and p.get("active")]
    cols = st.columns(2)
    for i, doc in enumerate(ward_docs):
        txt = cols[i % 2].text_input(f"Dr {doc} – izby (čiarkou):", key=f"core_{doc}")
        if txt.strip():
            manual_core_input[doc] = [int(p.strip()) for p in txt.split(',') if p.strip().isdigit()]
    if manual_core_input:
        st.session_state.manual_core[start_d.strftime('%Y-%m-%d')] = manual_core_input

    c_btn1, c_btn2, c_btn3 = st.columns(3)
    gen_clicked = c_btn1.button("🚀 Generovať rozpis", type="primary")
    scan_clicked = c_btn2.button("🔭 Vyhliadka ďalších týždňov")
    clear_hist = c_btn3.button("🗑️ Vymazať históriu")
    weeks_num = st.number_input("Počet týždňov pre vyhliadku:", min_value=1, max_value=52, value=12)

    if gen_clicked:
        with st.spinner("Počítam..."):
            end_d = start_d + timedelta(days=14)
            absences = get_ical_events(datetime.combine(start_d, datetime.min.time()), datetime.combine(end_d, datetime.min.time()))
            dates, grid, docs, d_info = generate_data_structure(st.session_state.config, absences, start_d)
            df_display = create_display_df(dates, grid, docs, d_info, st.session_state.motto, st.session_state.config)
            df_display.columns = ["Sekcia / Dátum"] + dates
            st.session_state.df_display = df_display
        st.success("✅ Hotovo!")

    if scan_clicked:
        with st.spinner(f"Pozerám {weeks_num} týždňov dopredu..."):
            problems_df = scan_future_problems(st.session_state.config, weeks_ahead=weeks_num) if hasattr(st.session_state.config, 'get') else None
            if problems_df is not None and not problems_df.empty:
                st.subheader("🔭 Vyhliadka ďalších týždňov – problémové dni")
                st.dataframe(problems_df, use_container_width=True, hide_index=True)
            else:
                st.success("✅ V zadanom období nie sú žiadne neobsadené pracoviská.")

    if clear_hist:
        save_history({})
        st.success("História vymazaná.")

    if 'df_display' in st.session_state:
        st.markdown("---")
        df_for_excel = st.session_state.df_display.copy()
        df_for_excel.iloc[0, 1:] = df_for_excel.columns[1:]
        xlsx_data = create_excel_report(df_for_excel)
        pdf_data = create_pdf_report(df_for_excel, st.session_state.motto)
        start_date_str = df_for_excel.columns[1].replace('.', '_')
        end_date_str = df_for_excel.columns[-1].replace('.', '_')
        filename_base = f"Rozpis_{start_date_str}_az_{end_date_str}"
        
        c_dl1, c_dl2 = st.columns(2)
        c_dl1.download_button("⬇️ EXCEL", xlsx_data, f"{filename_base}.xlsx")
        c_dl2.download_button("⬇️ PDF", pdf_data, f"{filename_base}.pdf", mime="application/pdf")

        with st.expander("📧 Odoslať emailom"):
            email_conf = st.session_state.config.get('email_settings', {})
            to_email = st.text_input("Príjemca:", value=email_conf.get("default_to", ""))
            subject = st.text_input("Predmet:", value=email_conf.get("default_subject", ""))
            body = st.text_area("Text:", value=email_conf.get("default_body", ""), height=150)
            if st.button("📤 Odoslať PDF"):
                if send_email_with_pdf(pdf_data, f"{filename_base}.pdf", to_email, subject, body):
                    st.success("Email odoslaný!")

        st.subheader("📄 Náhľad")
        st.dataframe(st.session_state.df_display, use_container_width=True, hide_index=True)

elif mode == "📧 Nastavenia Emailu":
    st.header("Nastavenia Emailu")
    current_conf = st.session_state.config.get('email_settings', {})
    new_to = st.text_input("Predvolený príjemca:", value=current_conf.get("default_to", ""))
    new_subj = st.text_input("Predvolený predmet:", value=current_conf.get("default_subject", ""))
    new_body = st.text_area("Predvolený text:", value=current_conf.get("default_body", ""))
    if st.button("💾 Uložiť"):
        st.session_state.config['email_settings'] = {
            "default_to": new_to,
            "default_subject": new_subj,
            "default_body": new_body
        }
        save_config(st.session_state.config)
        st.success("Uložené.")

elif mode == "⚙️ Nastavenia lekárov":
    st.header("Správa lekárov")
    col_new, col_btn = st.columns([3, 1])
    new_doc = col_new.text_input("Pridať lekára:")
    if col_btn.button("➕ Pridať") and new_doc:
        if new_doc not in st.session_state.config['lekari']:
            st.session_state.config['lekari'][new_doc] = {"moze": ["Oddelenie"], "active": True}
            save_config(st.session_state.config)
            st.success(f"{new_doc} pridaný")
            st.rerun()

    for doc, data in st.session_state.config['lekari'].items():
        with st.expander(f"{doc} {'(Neaktívny)' if not data.get('active', True) else ''}"):
            c_main1, c_main2 = st.columns(2)
            act = c_main1.checkbox("Aktívny", value=data.get('active', True), key=f"act_{doc}")
            if not act:
                st.markdown("##### 📅 Extra dni (pre neaktívnych)")
                current_extras = data.get('extra_dni', [])
                c_date1, c_date2 = st.columns([2, 1])
                new_extra = c_date1.date_input(f"Pridať deň pre {doc}", key=f"date_{doc}")
                if c_date2.button("➕ Pridať deň", key=f"add_date_{doc}"):
                    d_str = new_extra.strftime('%Y-%m-%d')
                    if d_str not in current_extras:
                        current_extras.append(d_str)
                        current_extras.sort()
                        data['extra_dni'] = current_extras
                        save_config(st.session_state.config)
                        st.rerun()
                if current_extras:
                    st.write("Naplánované dni:")
                    for ed in current_extras:
                        c_ex1, c_ex2 = st.columns([3, 1])
                        c_ex1.text(ed)
                        if c_ex2.button("❌", key=f"del_{doc}_{ed}"):
                            current_extras.remove(ed)
                            data['extra_dni'] = current_extras
                            save_config(st.session_state.config)
                            st.rerun()

            all_places = list(st.session_state.config['ambulancie'].keys()) + ["Oddelenie"]
            can_do = st.multiselect("Môže pracovať:", all_places, default=[p for p in data.get('moze', []) if p in all_places], key=f"can_{doc}")
            if act != data.get('active', True) or can_do != data.get('moze', []):
                data['active'] = act
                data['moze'] = can_do
                save_config(st.session_state.config)
                st.rerun()
            if st.button(f"🗑️ Odstrániť {doc}", key=f"del_{doc}"):
                del st.session_state.config['lekari'][doc]
                save_config(st.session_state.config)
                st.rerun()

elif mode == "🏥 Nastavenia ambulancií":
    st.header("Priority ambulancií")
    ambs = st.session_state.config['ambulancie']
    sel_amb = st.selectbox("Ambulancia:", list(ambs.keys()))
    curr_amb = ambs[sel_amb]
    st.info(f"Dni: {', '.join(curr_amb['dni'])}")
    prio = curr_amb['priority']
    if isinstance(prio, list):
        new_prio_text = st.text_area(f"Priority pre {sel_amb} (čiarkou):", ", ".join(prio))
        if st.button("💾 Uložiť"):
            ambs[sel_amb]['priority'] = [x.strip() for x in new_prio_text.split(',')]
            save_config(st.session_state.config)
            st.success("Uložené")
    else:
        st.warning("Komplexné priority. Upravte v JSON.")
