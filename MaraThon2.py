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

# --- REPORTLAB PRE PDF ---
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# --- KONFIGURÁCIA ---
CONFIG_FILE = 'hospital_config.json'
HISTORY_FILE = 'room_history.json'
PRIVATE_CALENDAR_URL = "https://calendar.google.com/calendar/ical/fntnonk%40gmail.com/private-e8ce4e0639a626387fff827edd26b87f/basic.ics"

GIST_FILENAME_CONFIG = "hospital_config_v9.json"
GIST_FILENAME_HISTORY = "room_history_v9.json"

ROOMS_LIST = [
    (1, 3), (2, 3), (3, 3), (4, 3), (5, 3),
    (7, 1), (8, 3), (9, 3), (10, 1), (11, 1),
    (12, 2), (13, 2), (14, 2), (15, 2), (16, 2), (17, 2),
    (18, 3), (19, 3)
]

SENIOR_DOCTORS = ["Kurisova", "Vidulin", "Miklatkova"]

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
            "Prijmova": {
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
                "priority": {
                    "0": ["Kohutek", "Stratena", "Bystricky", "Vidulin", "Blahova"],
                    "1": ["Kohutek", "Stratena", "Bystricky", "Vidulin", "Blahova"],
                    "default": ["Riedlova", "Kohutek", "Stratena", "Bystricky", "Vidulin", "Blahova"]
                }
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
                "moze": ["Prijmova", "Velka dispenzarna", "Mala dispenzarna", "Radio 2A", "Chemo 8A", "Chemo 8B", "Chemo 8C", "Wolf"],
                "active": True
            },
            "Kohutek": {
                "moze": ["Oddelenie", "Prijmova", "Velka dispenzarna", "Mala dispenzarna", "Radio 2A", "Chemo 8A", "Chemo 8B", "Chemo 8C", "Wolf"],
                "pevne_dni": {"Pondelok": "Chemo 8B", "Utorok": "Chemo 8B"},
                "active": True
            },
            "Kohutekova": {
                "moze": ["Prijmova"],
                "pevne_dni": {"Pondelok": "Prijmova", "Utorok": "Prijmova", "Streda": "Prijmova", "Stvrtok": "Prijmova"},
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
                "moze": ["Radio 2A", "Prijmova"],
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
    if not doctors_list:
        return {}, {}
    if manual_core is None:
        manual_core = {}
    if previous_assignments is None:
        previous_assignments = {}
        
    head_doc = "Kurisova" if "Kurisova" in doctors_list else ("Miklatkova" if "Miklatkova" in doctors_list else None)
    deputy_doc = "Kohutek" if "Kohutek" in doctors_list else None
    rt_help_doc = "Miklatkova" if "Miklatkova" in doctors_list else None
    
    pure_workers = [d for d in doctors_list if d not in ["Kurisova", "Kohutek"]]
    if rt_help_doc and head_doc != rt_help_doc and rt_help_doc not in pure_workers:
        pure_workers.append(rt_help_doc)
        
    num_workers = len(pure_workers)
    
    caps = {d: 12 if d == wolf_doc_name else 15 for d in doctors_list}
    if deputy_doc:
        caps[deputy_doc] = 6
    if rt_help_doc:
        if num_workers >= 4:
            caps[rt_help_doc] = 9
        elif num_workers == 3:
            caps[rt_help_doc] = 12
        else:
            caps[rt_help_doc] = 15
            
    if num_workers < 2:
        for d in doctors_list:
            caps[d] = 15
            
    assignment = {d: [] for d in doctors_list}
    current_beds = {d: 0 for d in doctors_list}
    available_rooms = sorted(ROOMS_LIST, key=lambda x: x[0])
    
    for doc, nums in manual_core.items():
        if doc not in doctors_list:
            continue
        for num in nums:
            r_obj = next((r for r in available_rooms if r[0] == num), None)
            if not r_obj:
                continue
            assignment[doc].append(r_obj)
            current_beds[doc] += r_obj[1]
            available_rooms.remove(r_obj)
            
    active_assignees = [d for d in doctors_list]
    if num_workers >= 2 and head_doc in active_assignees and head_doc != rt_help_doc:
        active_assignees.remove(head_doc)
        
    if previous_assignments:
        divisors = len(active_assignees) if active_assignees else 1
        total_system_beds = sum(r[1] for r in ROOMS_LIST)
        ideal_load = total_system_beds / divisors
        threshold_base = ideal_load * 1.1
        
        for doc in active_assignees:
            if doc in previous_assignments and doc not in manual_core:
                my_hist_rooms = [r for r_num in previous_assignments[doc] if (r := next((room for room in ROOMS_LIST if room[0] == r_num), None)) and r in available_rooms]
                my_hist_rooms.sort(key=lambda x: x[0])
                is_senior = (doc in SENIOR_DOCTORS) or (doc == deputy_doc)
                temp_beds = sum(r[1] for r in my_hist_rooms)
                my_limit = caps.get(doc, 15)
                eff_limit = min(threshold_base, my_limit)
                
                while temp_beds > eff_limit and my_hist_rooms:
                    if is_senior:
                        my_hist_rooms.pop()
                    else:
                        my_hist_rooms.pop(0)
                    temp_beds = sum(r[1] for r in my_hist_rooms)
                    
                for r_obj in my_hist_rooms:
                    if current_beds[doc] + r_obj[1] <= caps.get(doc, 15):
                        assignment[doc].append(r_obj)
                        current_beds[doc] += r_obj[1]
                        available_rooms.remove(r_obj)
                        
    while available_rooms:
        candidates = [d for d in active_assignees if current_beds[d] < caps.get(d, 15)]
        if not candidates:
            target_doc = head_doc if (head_doc and head_doc not in active_assignees) else (active_assignees[0] if active_assignees else None)
            if not target_doc:
                break
            candidates = [target_doc]
            
        candidates.sort(key=lambda w: current_beds[w])
        target_doc = candidates[0]
        
        doc_cap = caps.get(target_doc, 15)
        is_senior = (target_doc in SENIOR_DOCTORS)
        
        def room_score(r):
            deficit = doc_cap - current_beds[target_doc]
            fits = 1 if r[1] <= deficit else 0
            size_diff = abs(deficit - r[1])
            my_rooms = [x[0] for x in assignment[target_doc]]
            avg_pos = sum(my_rooms) / len(my_rooms) if my_rooms else 0
            dist = abs(r[0] - avg_pos) if my_rooms else (r[0] if is_senior else 20 - r[0])
            return (fits, -size_diff, -dist)
            
        available_rooms.sort(key=room_score, reverse=True)
        best_room = available_rooms.pop(0)
        assignment[target_doc].append(best_room)
        current_beds[target_doc] += best_room[1]
        
    result_text, result_raw = {}, {}
    for doc in doctors_list:
        rooms = sorted(assignment[doc], key=lambda x: x[0])
        result_raw[doc] = [r[0] for r in rooms]
        if not rooms:
            if doc == head_doc and num_workers >= 3:
                result_text[doc] = "RT oddelenie"
            else:
                result_text[doc] = "Wolf (0L)" if doc == wolf_doc_name else ""
        else:
            room_str = ", ".join([str(r[0]) for r in rooms])
            suffix = " + Wolf" if doc == wolf_doc_name else (" + RT oddelenie" if doc == head_doc else "")
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
    
    # NOVÁ LOGIKA PRE ZBER LEKÁROV
    # Zbierame aktívnych + tých, čo majú extra dni v tomto týždni
    all_doctors = []
    doctors_info = {} # Pre ukladanie poznámok (napr. "len 30.12.")

    # Generovanie dátumov týždňa pre kontrolu extra dní
    week_dates_str = []
    for i in range(7):
        d = thursday + timedelta(days=i)
        if d.weekday() < 5: # Len pracovne dni Po-Pi
            week_dates_str.append(d.strftime('%Y-%m-%d'))

    for d_name, props in config['lekari'].items():
        is_active = props.get('active', True)
        extra_days = props.get('extra_dni', [])
        
        # Má v tomto týždni extra deň?
        has_extra_in_week = any(ed in week_dates_str for ed in extra_days)
        
        if is_active or has_extra_in_week:
            all_doctors.append(d_name)
            if not is_active and has_extra_in_week:
                # Formátovanie dátumu pre zobrazenie (napr. 2025-12-30 -> 30.12.)
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
        
        # Filtrovanie dostupných lekárov pre KONKRÉTNY DEŇ
        # Musí byť aktívny ALEBO mať extra deň práve dnes
        available = []
        for d in all_doctors:
            props = config['lekari'][d]
            is_normally_active = props.get('active', True)
            has_extra_today = date_key in props.get('extra_dni', [])
            
            # Ak je neaktívny a nemá extra deň dnes -> preskočiť
            if not is_normally_active and not has_extra_today:
                continue
                
            # Ak je na dovolenke -> preskočiť (už riešené inde, ale pre istotu)
            if d in day_absences:
                continue
                
            # Ak má deň voľna (nepracuje) -> preskočiť
            if day_name in props.get('nepracuje', []):
                continue
                
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
                
        processing_order = ["Radio 2A", "Radio 2B", "Chemo 8B", "Chemo 8A", "Chemo 8C", "Wolf", "Prijmova", "Velka dispenzarna", "Mala dispenzarna"]
        
        for amb_name in processing_order:
            if amb_name == "Wolf":
                if "Spanik" in all_doctors and "Spanik" not in day_absences:
                    if assigned_amb.get("Mala dispenzarna") == "Spanik":
                        assigned_amb["Wolf"] = "Spanik"
                        continue
                        
            if amb_name in assigned_amb:
                continue
                
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
                
            for doc in prio_list:
                if doc in available and amb_name in config['lekari'][doc].get('moze', []):
                    assigned_amb[amb_name] = doc
                    available.remove(doc)
                    break
            if amb_name not in assigned_amb:
                assigned_amb[amb_name] = "NEOBSADENÉ"
                
        for amb, val in assigned_amb.items():
            data_grid[date_str][amb] = val
            
        wolf_doc = assigned_amb.get("Wolf")
        
        if "ODDELENIE (Celé)" in closed_today:
            room_text_map, room_raw_map = {}, {}
            for doc in all_doctors:
                if doc in day_absences:
                    continue
                if doc in assigned_amb.values():
                    continue
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
            # Ak lekár v tento deň vôbec nie je "available" (ani aktívny, ani extra deň),
            # mal by mať prázdne políčko alebo poznámku
            props = config['lekari'][doc]
            is_active = props.get('active', True)
            has_extra = date_key in props.get('extra_dni', [])
            
            if not is_active and not has_extra:
                data_grid[date_str][doc] = "" # Neaktívny v tento deň
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
            
            for amb_name in ["Prijmova", "Velka dispenzarna", "Mala dispenzarna", "Radio 2A", "Radio 2B", "Chemo 8A", "Chemo 8B", "Chemo 8C", "Wolf"]:
                val = grid[date_str].get(amb_name, "")
                if val in ["NEOBSADENÉ", "???", ""] and amb_name not in closed_today and "ODDELENIE (Celé)" not in closed_today:
                    display_map = {
                        "Radio 2A": "RT ambulancia",
                        "Velka dispenzarna": "veľký dispenzár",
                        "Mala dispenzarna": "malý dispenzár"
                    }
                    display_name = display_map.get(amb_name, amb_name)
                    problems.append({"Dátum": date_str, "Pracovisko": display_name})
                    
        current += timedelta(weeks=1)
        
    return pd.DataFrame(problems) if problems else None

def create_display_df(dates, data_grid, all_doctors, doctors_info, motto, config):
    rows = []
    ward_doctors = [d for d in all_doctors if "Oddelenie" in config['lekari'][d].get('moze', [])]
    display_map = {
        "Radio 2A": "RT ambulancia",
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
        
        # Pridanie info k menu lekára
        doc_label = f"Dr {doc}"
        if doc in doctors_info:
            doc_label += f" {doctors_info[doc]}"
            
        rows.append([doc_label] + vals)
        
    rows.append([motto or "Motto"] + [""] * len(dates))
    
    sections = [
        ("Konziliárna amb", ["Prijmova"]),
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
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    title = f"Rozpis prác Onkologická klinika {df.columns[1]} - {df.columns[-1]}"
    elements.append(Paragraph(title, styles['Title']))
    elements.append(Spacer(1, 12))
    data = [df.columns.tolist()] + df.values.tolist()
    col_widths = [100] + [90] * (len(df.columns) - 1)
    t = Table(data, colWidths=col_widths)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ])
    
    for i, row in enumerate(data):
        if row[0] in ["Oddelenie", "Konziliárna amb", "RT ambulancie", "Chemo amb", "Disp. Ambulancia", "RTG Terapia"]:
             style.add('BACKGROUND', (0, i), (-1, i), colors.lightgrey)
             style.add('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold')
        if row[0] == (motto or "Motto"):
             style.add('SPAN', (0, i), (-1, i))
             style.add('BACKGROUND', (0, i), (-1, i), colors.whitesmoke)
             style.add('FONTNAME', (0, i), (-1, i), 'Helvetica-Oblique')
             
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
    attachment = MIMEBase('application', 'pdf')
    attachment.set_payload(pdf_bytes)
    encoders.encode_base64(attachment)
    attachment.add_header('Content-Disposition', f'attachment; filename={filename}')
    msg.attach(attachment)
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_email, password)
        server.sendmail(from_email, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"Chyba: {e}")
        return False

# --- UI START ---
st.set_page_config(page_title="Rozpis FN Trenčín", layout="wide")
st.title("🏥 Rozpis prác - Onkologická klinika FN Trenčín")

if 'config' not in st.session_state:
    st.session_state.config = load_config()
if 'manual_core' not in st.session_state:
    st.session_state.manual_core = {}

mode = st.sidebar.radio("Navigácia", ["🚀 Generovať rozpis", "⚙️ Nastavenia lekárov", "🏥 Nastavenia ambulancií", "📧 Nastavenia Emailu"])

if mode == "🚀 Generovať rozpis":
    c1, c2 = st.columns([2, 2])
    st.session_state.motto = c1.text_input("📢 Motto týždňa:", placeholder="Sem napíšte motto...")
    start_d = c2.date_input("Začiatok rozpisu:", datetime.now())
    
    with st.expander("📅 Výnimky a zatváranie"):
        c_ex1, c_ex2, c_ex3 = st.columns([1, 2, 1])
        d_range = c_ex1.date_input("Rozsah dátumov:", value=[])
        amb_options = ["ODDELENIE (Celé)"] + list(st.session_state.config['ambulancie'].keys())
        selected_closures = c_ex2.multiselect("Čo má byť ZATVORENÉ?", options=amb_options)
        
        if c_ex3.button("💾 Uložiť"):
            if 'closures' not in st.session_state.config:
                st.session_state.config['closures'] = {}
            
            if len(d_range) == 2:
                curr = d_range[0]
                cnt = 0
                while curr <= d_range[1]:
                    d_key = curr.strftime('%Y-%m-%d')
                    if selected_closures:
                        st.session_state.config['closures'][d_key] = selected_closures
                    else:
                        if d_key in st.session_state.config['closures']:
                            del st.session_state.config['closures'][d_key]
                    curr += timedelta(days=1)
                    cnt += 1
                save_config(st.session_state.config)
                st.success(f"Nastavené na {cnt} dní.")
            elif len(d_range) == 1:
                d_key = d_range[0].strftime('%Y-%m-%d')
                if selected_closures:
                    st.session_state.config['closures'][d_key] = selected_closures
                else:
                    if d_key in st.session_state.config['closures']:
                        del st.session_state.config['closures'][d_key]
                save_config(st.session_state.config)
                st.success("Nastavené.")
    
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
    
    # --- HLAVNÉ TLAČIDLÁ ---
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
            problems_df = scan_future_problems(st.session_state.config, weeks_ahead=weeks_num)
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
                
                # Interface na pridanie dátumu
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
