import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import requests
from ics import Calendar
import io
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

# --- KONFIGURÁCIA ---
CONFIG_FILE = 'hospital_config.json'
HISTORY_FILE = 'room_history.json'
PRIVATE_CALENDAR_URL = "https://calendar.google.com/calendar/ical/fntnonk%40gmail.com/private-e8ce4e0639a626387fff827edd26b87f/basic.ics"

# Názvy súborov pre Gist úložisko
GIST_FILENAME_CONFIG = "hospital_config_v2.json"
GIST_FILENAME_HISTORY = "room_history_v2.json"

# Definícia izieb (Číslo, Počet lôžok)
ROOMS_LIST = [
    (1, 3), (2, 3), (3, 3), (4, 3), (5, 3),
    (7, 1), (8, 3), (9, 3), (10, 1), (11, 1),
    (12, 2), (13, 2), (14, 2), (15, 2), (16, 2), (17, 2),
    (18, 3), (19, 3)
]

# Skúsenejšie lekárky – smer plnenia izieb od 1 nahor
SENIOR_DOCTORS = ["Kurisova", "Vidulin", "Miklatkova"]

# --- GITHUB GIST STORAGE (ZADARMO) ---

def get_gist_id(filename):
    """Nájde existujúci Gist s daným súborom."""
    if "github" not in st.secrets:
        return None
    
    token = st.secrets["github"]["token"]
    headers = {"Authorization": f"token {token}"}
    try:
        resp = requests.get("https://api.github.com/gists", headers=headers)
        if resp.status_code == 200:
            for gist in resp.json():
                if filename in gist['files']:
                    return gist['id']
    except Exception:
        pass
    return None

def load_data_from_gist(filename):
    """Načíta JSON dáta z Gistu."""
    if "github" not in st.secrets:
        return None
        
    try:
        gist_id = get_gist_id(filename)
        if not gist_id:
            return None
        
        token = st.secrets["github"]["token"]
        headers = {"Authorization": f"token {token}"}
        resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=headers)
        if resp.status_code == 200:
            content = resp.json()['files'][filename]['content']
            return json.loads(content)
    except Exception as e:
        print(f"Gist load error: {e}")
    return None

def save_data_to_gist(filename, data):
    """Uloží/Aktualizuje JSON dáta v Giste."""
    if "github" not in st.secrets:
        return

    try:
        token = st.secrets["github"]["token"]
        headers = {"Authorization": f"token {token}"}
        gist_id = get_gist_id(filename)
        
        payload = {
            "description": f"Storage for {filename} (Streamlit App)",
            "public": False,
            "files": {
                filename: {
                    "content": json.dumps(data, ensure_ascii=False, indent=2)
                }
            }
        }

        if gist_id:
            requests.patch(f"https://api.github.com/gists/{gist_id}", json=payload, headers=headers)
        else:
            requests.post("https://api.github.com/gists", json=payload, headers=headers)
            
    except Exception as e:
        st.error(f"Chyba pri ukladaní do Gist ({filename}): {e}")

# --- PÔVODNÉ FUNKCIE + OBALENIE GISTOM ---

def get_default_config():
    return {
        "total_beds": 42,
        "ambulancie": {
            "Prijmova": {
                "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"],
                "priority": ["Kohutekova", "Kohutek", "Bystricky", "Zavrelova"]
            },
            "Velka dispenzarna": {
                "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"],
                "priority": ["Bocak", "Stratena", "Vidulin", "Kurisova",
                             "Blahova", "Hrabosova", "Miklatkova", "Martinka"]
            },
            "Mala dispenzarna": {
                "dni": ["Pondelok", "Piatok"],
                "priority": ["Spanik", "Stratena", "Vidulin", "Kurisova",
                             "Blahova", "Hrabosova", "Miklatkova"]
            },
            "Radio 2A": {
                "dni": ["Pondelok", "Utorok", "Streda", "Stvrtok", "Piatok"],
                "priority": ["Zavrelova", "Kohutek", "Kurisova",
                             "Miklatkova", "Bystricky"],
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
                    "default": ["Riedlova", "Kohutek", "Stratena",
                                "Bystricky", "Vidulin", "Blahova"]
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
                "moze": ["Prijmova", "Velka dispenzarna", "Mala dispenzarna",
                         "Radio 2A", "Chemo 8A", "Chemo 8B", "Chemo 8C", "Wolf"],
                "active": True
            },
            "Kohutek": {
                "moze": ["Oddelenie", "Prijmova", "Velka dispenzarna",
                         "Mala dispenzarna", "Radio 2A", "Chemo 8A",
                         "Chemo 8B", "Chemo 8C", "Wolf"],
                "pevne_dni": {"Pondelok": "Chemo 8B", "Utorok": "Chemo 8B"},
                "active": True
            },
            "Kohutekova": {
                "moze": ["Prijmova"],
                "pevne_dni": {
                    "Pondelok": "Prijmova",
                    "Utorok": "Prijmova",
                    "Streda": "Prijmova",
                    "Stvrtok": "Prijmova"
                },
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
                "pevne_dni": {
                    "Pondelok": "Radio 2A",
                    "Utorok": "Radio 2A",
                    "Streda": "Radio 2A",
                    "Stvrtok": "Radio 2A",
                    "Piatok": "Radio 2A"
                },
                "active": True
            },
            "Martinka": {
                "moze": ["Radio 2B", "Oddelenie", "Velka dispenzarna"],
                "pevne_dni": {
                    "Pondelok": "Radio 2B",
                    "Utorok": "Radio 2B",
                    "Streda": "Radio 2B",
                    "Stvrtok": "Radio 2B",
                    "Piatok": "Radio 2B"
                },
                "active": True
            },
            "Hatalova": {
                "moze": ["Chemo 8A"],
                "pevne_dni": {
                    "Pondelok": "Chemo 8A",
                    "Utorok": "Chemo 8A",
                    "Streda": "Chemo 8A",
                    "Stvrtok": "Chemo 8A",
                    "Piatok": "Chemo 8A"
                },
                "active": True
            },
            "Stratena": {
                "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna",
                         "Chemo 8A", "Chemo 8B", "Chemo 8C"],
                "pevne_dni": {
                    "Utorok": "Chemo 8C",
                    "Streda": "Chemo 8C",
                    "Stvrtok": "Chemo 8C"
                },
                "active": True
            },
            "Vidulin": {
                "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna",
                         "Chemo 8A", "Chemo 8B", "Chemo 8C"],
                "active": True
            },
            "Miklatkova": {
                "moze": ["Oddelenie", "Wolf"],
                "active": True
            },
            "Kurisova": {
                "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna",
                         "Radio 2A", "Wolf"],
                "special": "veduca",
                "active": True
            },
            "Blahova": {
                "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna",
                         "Chemo 8B", "Chemo 8C"],
                "active": False
            },
            "Hrabosova": {
                "moze": ["Oddelenie", "Velka dispenzarna", "Mala dispenzarna"],
                "active": False
            },
            "Bocak": {
                "moze": ["Velka dispenzarna"],
                "pevne_dni": {
                    "Pondelok": "Velka dispenzarna",
                    "Utorok": "Velka dispenzarna",
                    "Streda": "Velka dispenzarna",
                    "Stvrtok": "Velka dispenzarna",
                    "Piatok": "Velka dispenzarna"
                },
                "active": True
            },
            "Spanik": {
                "moze": ["Wolf", "Mala dispenzarna"],
                "pevne_dni": {
                    "Pondelok": "Mala dispenzarna",
                    "Piatok": "Mala dispenzarna",
                    "Utorok": "Wolf",
                    "Streda": "Wolf",
                    "Stvrtok": "Wolf"
                },
                "active": True
            },
            "Kacurova": {"moze": ["Oddelenie"], "active": True},
            "Hunakova": {"moze": ["Oddelenie"], "active": True}
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
                amb_data["priority"] = [
                    "Vidulin" if x == "Homolova" else x
                    for x in amb_data["priority"]
                ]
                changed = True
        elif isinstance(amb_data["priority"], dict):
            for day_key, day_list in amb_data["priority"].items():
                if "Homolova" in day_list:
                    amb_data["priority"][day_key] = [
                        "Vidulin" if x == "Homolova" else x
                        for x in day_list
                    ]
                    changed = True
    return config, changed

def load_config():
    # 1. Skúsime Gist (Iba ak máme kľúče - na webe)
    gist_data = load_data_from_gist(GIST_FILENAME_CONFIG)
    
    # --- OPRAVA ---
    if gist_
        data, changed = migrate_homolova_to_vidulin(gist_data)
        if changed: 
            save_config(data)
        return data
    
    # 2. Lokálny súbor (Fallback pre lokálny beh)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            config, changed = migrate_homolova_to_vidulin(config)
            if changed: 
                save_config(config)
            return config
        except: 
            pass
        
    # 3. Default
    return get_default_config()

def save_config(config):
    # Lokálne
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    # Gist
    save_data_to_gist(GIST_FILENAME_CONFIG, config)

def load_history():
    # 1. Gist
    gist_data = load_data_from_gist(GIST_FILENAME_HISTORY)
    if gist_
        return gist_data
    
    # 2. Lokálne
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_history(history):
    # Lokálne
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    # Gist
    save_data_to_gist(GIST_FILENAME_HISTORY, history)

# --- HIERARCHICKÉ ROZDEĽOVANIE IZIEB (UPDATED) ---

def distribute_rooms(doctors_list, wolf_doc_name,
                     previous_assignments=None, manual_core=None):
    """
    Priorita SPRAVODLIVOSŤ (Fairness) pred GEOGRAFIOU.
    Snaží sa nájsť izbu, ktorá najlepšie doplní lekára do ideálneho počtu lôžok.
    """
    if not doctors_list:
        return {}, {}
    if manual_core is None:
        manual_core = {}
    if previous_assignments is None:
        previous_assignments = {}

    # --- 1. NASTAVENIE ROLÍ A LIMITOV ---
    head_doc = "Kurisova" if "Kurisova" in doctors_list else (
        "Miklatkova" if "Miklatkova" in doctors_list else None
    )
    deputy_doc = "Kohutek" if "Kohutek" in doctors_list else None
    rt_help_doc = "Miklatkova" if "Miklatkova" in doctors_list else None

    pure_workers = [
        d for d in doctors_list if d != "Kurisova" and d != "Kohutek"
    ]
    if rt_help_doc and head_doc != rt_help_doc and rt_help_doc not in pure_workers:
        pure_workers.append(rt_help_doc)
    num_workers = len(pure_workers)

    # Základné limity
    caps = {}
    for d in doctors_list:
        caps[d] = 12 if d == wolf_doc_name else 15
    if deputy_doc:
        caps[deputy_doc] = 6
    if rt_help_doc:
        if num_workers >= 4: caps[rt_help_doc] = 9
        elif num_workers == 3: caps[rt_help_doc] = 12
        else: caps[rt_help_doc] = 15
    if num_workers < 2:
        for d in doctors_list: caps[d] = 15

    assignment = {d: [] for d in doctors_list}
    current_beds = {d: 0 for d in doctors_list}
    available_rooms = sorted(ROOMS_LIST, key=lambda x: x[0])

    # --- 2. MANUÁLNE JADRO ---
    for doc, nums in manual_core.items():
        if doc not in doctors_list: continue
        for num in nums:
            r_obj = next((r for r in available_rooms if r[0] == num), None)
            if not r_obj: continue
            assignment[doc].append(r_obj)
            current_beds[doc] += r_obj[1]
            available_rooms.remove(r_obj)

    active_assignees = [d for d in doctors_list]
    if num_workers >= 2 and head_doc in active_assignees and head_doc != rt_help_doc:
        active_assignees.remove(head_doc)

    # --- 3. ROBIN HOOD HISTÓRIA (Orezaná) ---
    if previous_assignments:
        divisors = len(active_assignees) if active_assignees else 1
        total_system_beds = sum(r[1] for r in ROOMS_LIST)
        ideal_load = total_system_beds / divisors 
        threshold_base = ideal_load * 1.1 

        for doc in active_assignees:
            if doc in previous_assignments and doc not in manual_core:
                my_hist_rooms = []
                for r_num in previous_assignments[doc]:
                    r_obj = next((r for r in ROOMS_LIST if r[0] == r_num), None)
                    if r_obj and r_obj in available_rooms:
                        my_hist_rooms.append(r_obj)
                
                my_hist_rooms.sort(key=lambda x: x[0])
                is_senior = (doc in SENIOR_DOCTORS) or (doc == deputy_doc)
                
                temp_beds = sum(r[1] for r in my_hist_rooms)
                my_limit = caps.get(doc, 15)
                eff_limit = min(threshold_base, my_limit)

                while temp_beds > eff_limit and my_hist_rooms:
                    if is_senior: my_hist_rooms.pop()
                    else: my_hist_rooms.pop(0)
                    temp_beds = sum(r[1] for r in my_hist_rooms)

                for r_obj in my_hist_rooms:
                    if current_beds[doc] + r_obj[1] <= caps.get(doc, 15):
                        assignment[doc].append(r_obj)
                        current_beds[doc] += r_obj[1]
                        available_rooms.remove(r_obj)

    # --- 4. DOPLNENIE "BEST FIT" (Spravodlivosť) ---
    while available_rooms:
        candidates = [d for d in active_assignees if current_beds[d] < caps.get(d, 15)]
        if not candidates:
            target_doc = head_doc if (head_doc and head_doc not in active_assignees) else active_assignees[0]
            candidates = [target_doc]

        # Vyberieme toho, kto má najmenej lôžok
        candidates.sort(key=lambda w: current_beds[w])
        target_doc = candidates[0]
        
        doc_cap = caps.get(target_doc, 15)
        deficit = doc_cap - current_beds[target_doc]
        is_senior = (target_doc in SENIOR_DOCTORS)
        
        # Skórovacia funkcia izby
        def room_score(r):
            fits = 1 if r[1] <= deficit else 0 
            size_diff = abs(deficit - r[1])
            
            my_rooms = [x[0] for x in assignment[target_doc]]
            if my_rooms:
                avg_pos = sum(my_rooms) / len(my_rooms)
                dist = abs(r[0] - avg_pos)
            else:
                dist = r[0] if is_senior else (20 - r[0])
            
            # Priority: 1. Zmestí sa do limitu, 2. Veľkosť (čo najblizsie deficitu), 3. Geografia
            return (fits, -size_diff, -dist)
        
        available_rooms.sort(key=room_score, reverse=True)
        best_room = available_rooms[0]

        assignment[target_doc].append(best_room)
        current_beds[target_doc] += best_room[1]
        available_rooms.remove(best_room)

    # --- 5. FORMÁTOVANIE ---
    result_text = {}
    result_raw = {}
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
            suffix = " + Wolf" if doc == wolf_doc_name else (
                " + RT oddelenie" if doc == head_doc else ""
            )
            result_text[doc] = f"{room_str}{suffix}"

    return result_text, result_raw

# --- DATA PROCESSING ---

def get_ical_events(start_date, end_date):
    try:
        response = requests.get(PRIVATE_CALENDAR_URL)
        response.raise_for_status()
        c = Calendar(response.text)
        absences = {}
        for event in c.events:
            ev_start, ev_end = event.begin.date(), event.end.date()
            search_start, search_end = start_date.date(), end_date.date()
            if ev_end < search_start or ev_start > search_end:
                continue
            
            raw = event.name.strip()
            name = raw
            typ = "Dovolenka"

            # Robust suffix parsing (e.g. "MartinkaS", "HunakovaPN")
            if raw.endswith('PN'):
                typ = "PN"
                name = raw[:-2].rstrip(' -')
            elif raw.endswith('VZ'):
                typ = "Vzdelávanie"
                name = raw[:-2].rstrip(' -')
            elif raw.endswith('S') and not raw.endswith('OS'): # Check aby to nebralo mená končiace na OS
                typ = "Stáž"
                name = raw[:-1].rstrip(' -')
            elif '-' in raw and typ == "Dovolenka":
                parts = raw.split('-')
                name = parts[0].strip()
                suffix = parts[1].strip() if len(parts) > 1 else ""
                if suffix == 'S': typ = "Stáž"
                elif suffix == 'PN': typ = "PN"
                elif suffix == 'VZ': typ = "Vzdelávanie"
            
            curr, limit = max(ev_start, search_start), min(ev_end, search_end)
            while curr < limit:
                d_str = curr.strftime('%Y-%m-%d')
                if d_str not in absences:
                    absences[d_str] = {}
                absences[d_str][name] = typ
                curr += timedelta(days=1)
        return absences
    except Exception as e:
        st.error(f"Chyba kalendára: {str(e)}")
        return {}

def generate_data_structure(config, absences, start_date):
    days_map = {
        0: "Pondelok", 1: "Utorok", 2: "Streda",
        3: "Stvrtok", 4: "Piatok", 5: "Sobota", 6: "Nedela"
    }
    weekday = start_date.weekday()
    thursday = start_date + timedelta(days=(3 - weekday) % 7)
    dates = []
    data_grid = {}
    all_doctors = sorted(
        [d for d in config['lekari'].keys()
         if config['lekari'][d]['active']]
    )

    history = load_history()
    day_before = (thursday - timedelta(days=1)).strftime('%Y-%m-%d')
    last_day_assignments = history.get(day_before, {})

    manual_all = st.session_state.get("manual_core", {})
    cycle_start_key = start_date.strftime('%Y-%m-%d')
    manual_for_cycle = manual_all.get(cycle_start_key, {})

    for i in range(7):
        curr_date = thursday + timedelta(days=i)
        day_name = days_map[curr_date.weekday()]
        date_str = curr_date.strftime('%d.%m.%Y')
        date_key = curr_date.strftime('%Y-%m-%d')

        if day_name in ["Sobota", "Nedela"]:
            continue
        dates.append(date_str)
        day_absences = absences.get(date_key, {})
        data_grid[date_str] = {}

        available = [
            d for d in all_doctors
            if d not in day_absences and
            day_name not in config['lekari'][d].get('nepracuje', [])
        ]
        assigned_amb = {}

        to_remove = []
        for doc in available:
            fixed = config['lekari'][doc].get('pevne_dni', {}).get(day_name)
            if fixed:
                targets = [t.strip() for t in fixed.split(',')]
                for t in targets:
                    assigned_amb[t] = doc
                to_remove.append(doc)
        for d in to_remove:
            if d in available:
                available.remove(d)

        processing_order = [
            "Radio 2A", "Radio 2B",
            "Chemo 8B", "Chemo 8A", "Chemo 8C",
            "Wolf",
            "Prijmova",
            "Velka dispenzarna", "Mala dispenzarna"
        ]

        for amb_name in processing_order:
            if amb_name not in config['ambulancie']:
                continue
            amb_info = config['ambulancie'][amb_name]
            if amb_name in assigned_amb:
                continue
            if day_name not in amb_info['dni']:
                assigned_amb[amb_name] = "---"
                continue

            if amb_name == "Radio 2A" and "Zavrelova" not in available and "Martinka" not in day_absences:
                assigned_amb[amb_name] = "Amb. zatvorená"
                continue
            if amb_name == "Radio 2B" and "Martinka" not in available and assigned_amb.get(amb_name) != "Martinka":
                assigned_amb[amb_name] = "ZATVORENÉ"
                continue

            prio_list = amb_info['priority']
            if isinstance(prio_list, dict):
                prio_list = prio_list.get(str(curr_date.weekday()),
                                          prio_list.get('default', []))

            for doc in prio_list:
                if doc == "Spanik":
                    is_working = (
                        doc in all_doctors and
                        doc not in day_absences and
                        day_name not in config['lekari'][doc].get('nepracuje', [])
                    )
                    if is_working:
                        can_take = True
                        if doc not in available:
                            current_job = next(
                                (a for a, d in assigned_amb.items() if d == doc),
                                None
                            )
                            if current_job not in ["Wolf", "Mala dispenzarna"]:
                                can_take = False
                        if can_take and amb_name in config['lekari'][doc].get('moze', []):
                            assigned_amb[amb_name] = doc
                            if doc in available:
                                available.remove(doc)
                            break
                else:
                    if doc in available and amb_name in config['lekari'][doc].get('moze', []):
                        assigned_amb[amb_name] = doc
                        available.remove(doc)
                        break
            if amb_name not in assigned_amb:
                assigned_amb[amb_name] = "NEOBSADENÉ"

        for amb, val in assigned_amb.items():
            data_grid[date_str][amb] = val

        wolf_doc = assigned_amb.get("Wolf")
        ward_candidates = [
            d for d in available
            if "Oddelenie" in config['lekari'][d].get('moze', [])
        ]
        if wolf_doc and wolf_doc not in ward_candidates:
            if wolf_doc == "Spanik" and assigned_amb.get("Mala dispenzarna") == "Spanik":
                pass
            elif "Oddelenie" in config['lekari'][wolf_doc].get('moze', []):
                ward_candidates.append(wolf_doc)

        manual_core_for_day = manual_for_cycle if ward_candidates else {}

        room_text_map, room_raw_map = distribute_rooms(
            ward_candidates,
            wolf_doc,
            previous_assignments=last_day_assignments,
            manual_core=manual_core_for_day
        )

        last_day_assignments = room_raw_map
        history[date_key] = room_raw_map

        for doc in all_doctors:
            if doc in day_absences:
                data_grid[date_str][doc] = day_absences[doc]
            elif doc in room_text_map:
                data_grid[date_str][doc] = room_text_map[doc]
            else:
                jobs = [a for a, d in assigned_amb.items() if d == doc]
                if jobs:
                    data_grid[date_str][doc] = " + ".join(jobs)
                else:
                    data_grid[date_str][doc] = ""

    save_history(history)
    return dates, data_grid, all_doctors

# --- VIZUALIZÁCIA ---

def create_display_df(dates, data_grid, all_doctors, motto, config):
    rows = []
    ward_doctors = [
        d for d in all_doctors
        if "Oddelenie" in config['lekari'][d].get('moze', [])
    ]
    rows.append(["Oddelenie"] + dates)
    for doc in ward_doctors:
        row_data = [f"Dr {doc}"]
        for date in dates:
            val = data_grid[date].get(doc, "")
            val = val.replace("Velka dispenzarna", "veľký dispenzár") \
                     .replace("Mala dispenzarna", "malý dispenzár")
            row_data.append(val)
        rows.append(row_data)
    rows.append([motto if motto else "Motto"] + [""] * len(dates))

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
            row_data = [amb]
            for date in dates:
                val = data_grid[date].get(amb, "")
                if val == "---":
                    val = ""
                if val == "NEOBSADENÉ":
                    val = "???"
                row_data.append(val)
            rows.append(row_data)
        rows.append([""] * (len(dates) + 1))
    return pd.DataFrame(rows, columns=["Sekcia / Dátum"] + dates)

def create_excel_report(dates, data_grid, all_doctors, motto, config):
    wb = Workbook()
    ws = wb.active
    ws.title = "Rozpis"

    bold_font = Font(bold=True)
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    df_preview = create_display_df(dates, data_grid, all_doctors, motto, config)

    ws.merge_cells(f'A1:{get_column_letter(len(dates)+1)}1')
    ws['A1'] = f"Rozpis prác Onkologická klinika {dates[0]} - {dates[-1]} včítane"
    ws['A1'].font = bold_font
    ws['A1'].alignment = center_align

    excel_row = 2
    for _, row_series in df_preview.iterrows():
        row_list = row_series.tolist()
        first_cell_val = str(row_list[0])

        is_header_row = first_cell_val in [
            "Oddelenie", "Konziliárna amb", "RT ambulancie",
            "Chemo amb", "Disp. Ambulancia", "RTG Terapia"
        ]
        is_motto = (first_cell_val == (motto if motto else "Motto"))
        is_empty = (first_cell_val == "") and all(x == "" for x in row_list[1:])

        if is_empty:
            excel_row += 1
            continue

        if is_motto:
            ws.merge_cells(f'A{excel_row}:{get_column_letter(len(dates)+1)}{excel_row}')
            cell = ws[f'A{excel_row}']
            cell.value = first_cell_val
            cell.font = Font(bold=True, italic=True)
            cell.alignment = center_align
            cell.fill = PatternFill(start_color="EEEEEE", end_color="EEEEEE", fill_type="solid")
            cell.border = border
        elif is_header_row:
            ws.cell(row=excel_row, column=1, value=first_cell_val).font = bold_font
            ws.cell(row=excel_row, column=1).border = border
            for c_idx, val in enumerate(row_list[1:], start=2):
                cell = ws.cell(row=excel_row, column=c_idx, value=val)
                cell.font = bold_font
                cell.alignment = center_align
                cell.border = border
        else:
            ws.cell(row=excel_row, column=1, value=first_cell_val).border = border
            for c_idx, val in enumerate(row_list[1:], start=2):
                cell = ws.cell(row=excel_row, column=c_idx, value=val)
                cell.alignment = center_align
                cell.border = border
        excel_row += 1

    ws.column_dimensions['A'].width = 25
    for col_idx in range(2, len(dates) + 2):
        ws.column_dimensions[get_column_letter(col_idx)].width = 18

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

# --- UI ---

st.set_page_config(page_title="Rozpis FN Trenčín", layout="wide")
st.title("🏥 Rozpis prác - Onkologická klinika FN Trenčín")

if 'config' not in st.session_state:
    st.session_state.config = load_config()
if 'manual_core' not in st.session_state:
    st.session_state.manual_core = {}

mode = st.sidebar.radio("Navigácia",
                        ["🚀 Generovať rozpis",
                         "⚙️ Nastavenia lekárov",
                         "🏥 Nastavenia ambulancií"])

if mode == "🚀 Generovať rozpis":
    with st.container():
        c1, c2 = st.columns([2, 2])
        with c1:
            motto = st.text_input(
                "📢 Motto týždňa (nepovinné):",
                placeholder="Sem napíšte motto..."
            )
        with c2:
            start_d = st.date_input(
                "Začiatok rozpisu (vypočíta najbližší štvrtok):",
                datetime.now()
            )

    st.markdown("### Manuálne pridelenie izieb")
    manual_core_input = {}
    ward_doctors_cfg = [
        d for d, info in st.session_state.config["lekari"].items()
        if "Oddelenie" in info.get("moze", []) and info.get("active", True)
    ]
    cols = st.columns(2)
    for idx, doc in enumerate(ward_doctors_cfg):
        with cols[idx % 2]:
            txt = st.text_input(
                f"Dr {doc} – izby",
                key=f"core_{doc}"
            )
            if txt.strip():
                nums = []
                for part in txt.split(","):
                    part = part.strip()
                    if part.isdigit():
                        nums.append(int(part))
                if nums:
                    manual_core_input[doc] = nums

    cycle_start_key = start_d.strftime('%Y-%m-%d')
    if manual_core_input:
        st.session_state.manual_core[cycle_start_key] = manual_core_input

    c3, c4 = st.columns([1, 1])
    with c3:
        gen_btn = st.button("🚀 Generovať nový rozpis", type="primary")
    with c4:
        if st.button("🗑️ Vymazať históriu izieb"):
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)
                if "github" in st.secrets:
                     # Gist mazanie je komplikovane, radsej ulozime prazdne
                     save_data_to_gist(GIST_FILENAME_HISTORY, {})
            st.success("História vymazaná.")

    if gen_btn:
        with st.spinner("Sťahujem kalendár a počítam..."):
            absences = get_ical_events(
                datetime.combine(start_d, datetime.min.time()),
                datetime.combine(start_d + timedelta(days=14),
                                 datetime.min.time())
            )

            dates, grid, docs = generate_data_structure(
                st.session_state.config, absences, start_d
            )
            xlsx_data = create_excel_report(
                dates, grid, docs, motto, st.session_state.config
            )
            df_display = create_display_df(
                dates, grid, docs, motto, st.session_state.config
            )

            st.success("✅ Hotovo! Izby sú synchronizované s históriou.")
            st.download_button(
                label="⬇️ Stiahnuť EXCEL Rozpis (.xlsx)",
                data=xlsx_data,
                file_name=f"Rozpis_{dates[0]}_{dates[-1]}.xlsx",
                mime=("application/"
                      "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            )

            st.markdown("---")
            st.subheader("📄 Náhľad")
            st.dataframe(df_display, use_container_width=True, hide_index=True)

elif mode == "⚙️ Nastavenia lekárov":
    st.header("Správa lekárov")
    col_new, col_btn = st.columns([3, 1])
    with col_new:
        new_doc = st.text_input("Pridať nového lekára (meno)")
    with col_btn:
        st.write("")
        st.write("")
        if st.button("➕ Pridať") and new_doc:
            if new_doc not in st.session_state.config['lekari']:
                st.session_state.config['lekari'][new_doc] = {
                    "moze": ["Oddelenie"],
                    "active": True
                }
                save_config(st.session_state.config)
                st.success(f"Lekár {new_doc} pridaný")
                st.experimental_rerun()

    for doc, data in st.session_state.config['lekari'].items():
        with st.expander(f"{doc} {'(Neaktívny)' if not data.get('active', True) else ''}"):
            c1, c2 = st.columns(2)
            with c1:
                act = st.checkbox("Aktívny",
                                  value=data.get('active', True),
                                  key=f"act_{doc}")
            all_places = list(
                st.session_state.config['ambulancie'].keys()
            ) + ["Oddelenie"]
            can_do = st.multiselect(
                "Môže pracovať na:",
                all_places,
                default=[p for p in data.get('moze', [])
                         if p in all_places],
                key=f"can_{doc}"
            )
            if act != data.get('active', True) or can_do != data.get('moze', []):
                data['active'] = act
                data['moze'] = can_do
                save_config(st.session_state.config)
                st.experimental_rerun()
            if st.button(f"🗑️ Odstrániť {doc}", key=f"del_{doc}"):
                del st.session_state.config['lekari'][doc]
                save_config(st.session_state.config)
                st.experimental_rerun()

elif mode == "🏥 Nastavenia ambulancií":
    st.header("Priority ambulancií")
    ambs = st.session_state.config['ambulancie']
    sel_amb = st.selectbox("Vyberte ambulanciu na úpravu", list(ambs.keys()))
    curr_amb = ambs[sel_amb]
    st.info(f"Dni prevádzky: {', '.join(curr_amb['dni'])}")
    prio = curr_amb['priority']
    if isinstance(prio, list):
        new_prio_text = st.text_area(
            f"Zoznam priorít pre {sel_amb} (oddelené čiarkou)",
            ", ".join(prio)
        )
        if st.button("💾 Uložiť priority"):
            clean_prio = [x.strip() for x in new_prio_text.split(',')]
            ambs[sel_amb]['priority'] = clean_prio
            save_config(st.session_state.config)
            st.success("Priority aktualizované")
    else:
        st.warning(
            "Táto ambulancia má komplexné priority. "
            "Ak chceš meniť logiku, uprav JSON / kód."
        )
