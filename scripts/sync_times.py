import os
import json
import re
import io
import requests
from bs4 import BeautifulSoup

# Try importing google-genai, but allow script to run without it if only local parser is used
try:
    from google import genai
    from google.genai import types
    HAS_GEMINI_SDK = True
except ImportError:
    HAS_GEMINI_SDK = False

# Configuration
RESULTS_PAGE_URL = "https://www.gomotionapp.com/team/recmrssca/page/2026-springmsl/2026-msl-meet-schedule"

def get_all_pdf_urls():
    print(f"Searching for meet results at {RESULTS_PAGE_URL}...")
    response = requests.get(RESULTS_PAGE_URL, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(response.text, 'html.parser')
    
    pdf_urls = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        # We only want results PDFs, avoiding heatsheets or handmarking sheets
        if href.lower().endswith('.pdf') and "results" in href.lower():
            if not href.startswith('http'):
                href = f"https://www.gomotionapp.com{href}"
            if href not in pdf_urls:
                pdf_urls.append(href)
    return pdf_urls

def clean_event_name(name):
    name = name.strip()
    if "100Y MED.REL." in name or "100Y MEDLEY REL" in name:
        return "Mixed 8&UN 100Y Medley Relay"
    if "100Y FREE REL" in name:
        return "Mixed 8&UN 100Y Free Relay"
    if "25Y FREE" in name:
        return "Boys 8&UN 25Y Freestyle"
    if "25Y BACK" in name:
        return "Boys 8&UN 25Y Backstroke"
    return name

def time_to_seconds(t_str):
    t_str = t_str.strip()
    if t_str in ("NT", "NS", "DQ", "SCR"):
        return None
    try:
        if ":" in t_str:
            parts = t_str.split(":")
            return int(parts[0]) * 60 + float(parts[1])
        else:
            return float(t_str)
    except ValueError:
        return None

def parse_pdf_locally(date, meet_name, pdf_content):
    """
    Attempts to parse the results PDF locally using pypdf and structured regexes.
    Returns a list of extracted races, or None if the local parsing fails or finds no results.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        print("Warning: pypdf not installed. Skipping local parser.")
        return None

    reader = PdfReader(io.BytesIO(pdf_content))
    events_data = {}
    
    event_pattern = re.compile(r"Event\s*#\s*(\d+)\s*(.*)", re.IGNORECASE)
    # Match result lines like: "Beyer, Zephyr    21.45SRBY6 :22.45" or "Remy Benko    29.68SRBY1 :31.43 1"
    result_pattern = re.compile(
        r"^\s*([^0-9]+?)\s+([\d:.]+|NS|DQ|NT)\s*([A-Z]{2,6})(\d+)(?:\s+([\d:.]+|NT))?",
        re.IGNORECASE
    )
    # Match relay headers like: "Strawberry Seals C  1:46.84SRBY4 1:50.08"
    relay_pattern = re.compile(
        r"^\s*([A-Za-z\s]+[A-D])\s+([\d:.]+)\s*([A-Z]{2,6})(\d+)\s+([\d:.]+)",
        re.IGNORECASE
    )
    
    current_event = None
    
    for page in reader.pages:
        text = page.extract_text()
        lines = text.split('\n')
        
        last_relay_header = None
        lines_since_relay = 999
        
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
                
            # 1. Event header check
            ev_match = event_pattern.match(line_str)
            if ev_match:
                current_event = clean_event_name(ev_match.group(2))
                if current_event not in events_data:
                    events_data[current_event] = {
                        "individual_times": [],
                        "relay_times": [],
                        "remy_results": []
                    }
                last_relay_header = None
                lines_since_relay = 999
                continue
                
            if not current_event:
                continue
                
            # 2. Relay header check
            rel_match = relay_pattern.match(line_str)
            if rel_match:
                relay_name = rel_match.group(1).strip()
                relay_time = rel_match.group(2)
                relay_team = rel_match.group(3)
                relay_place = rel_match.group(4)
                relay_seed = rel_match.group(5)
                
                last_relay_header = {
                    "team_name": relay_name,
                    "time": relay_time,
                    "team": relay_team,
                    "place": relay_place,
                    "seed": relay_seed
                }
                
                time_sec = time_to_seconds(relay_time)
                if time_sec:
                    events_data[current_event]["relay_times"].append((relay_name, time_sec))
                
                lines_since_relay = 0
                continue
                
            if last_relay_header is not None:
                lines_since_relay += 1
                
            # 3. Check for Remy in relay (within 3 lines of relay header)
            if last_relay_header and lines_since_relay <= 3:
                if "benko" in line_str.lower() or "remy" in line_str.lower():
                    events_data[current_event]["remy_results"].append({
                        "type": "relay",
                        "team_name": last_relay_header["team_name"],
                        "time": last_relay_header["time"],
                        "heat_place": last_relay_header["place"],
                        "seed": last_relay_header["seed"]
                    })
                    last_relay_header = None
                    lines_since_relay = 999
                    continue
            
            # 4. Individual result line check
            res_match = result_pattern.match(line_str)
            if res_match:
                name = res_match.group(1).strip()
                time_str = res_match.group(2)
                team = res_match.group(3)
                place = res_match.group(4)
                seed_str = res_match.group(5) or "NT"
                
                time_sec = time_to_seconds(time_str)
                if time_sec:
                    events_data[current_event]["individual_times"].append((name, time_sec))
                    
                if "benko" in name.lower() or "remy" in name.lower():
                    events_data[current_event]["remy_results"].append({
                        "type": "individual",
                        "name": name,
                        "time": time_str,
                        "heat_place": place,
                        "seed": seed_str
                    })
                    
    races = []
    for event_name, data in events_data.items():
        for remy_res in data["remy_results"]:
            if remy_res["type"] == "individual":
                remy_time_sec = time_to_seconds(remy_res["time"])
                overall_place = "TBD"
                if remy_time_sec:
                    sorted_times = sorted(data["individual_times"], key=lambda x: x[1])
                    rank = 1
                    for name, t_sec in sorted_times:
                        if t_sec < remy_time_sec:
                            rank += 1
                    overall_place = str(rank)
                
                seed_str = remy_res["seed"].replace(":", "")
                improvement = "0.00"
                if seed_str != "NT" and remy_time_sec:
                    seed_sec = time_to_seconds(seed_str)
                    if seed_sec:
                        diff = remy_time_sec - seed_sec
                        improvement = f"{diff:+.2f}"
                        
                races.append({
                    "date": date,
                    "meet": meet_name,
                    "event": event_name,
                    "time": remy_res["time"],
                    "heat_place": remy_res["heat_place"],
                    "overall_place": overall_place,
                    "improvement": improvement,
                    "video_url": ""
                })
            else:
                remy_time_sec = time_to_seconds(remy_res["time"])
                overall_place = remy_res["heat_place"]
                if remy_time_sec:
                    sorted_times = sorted(data["relay_times"], key=lambda x: x[1])
                    rank = 1
                    for team_name, t_sec in sorted_times:
                        if t_sec < remy_time_sec:
                            rank += 1
                    overall_place = str(rank)
                    
                races.append({
                    "date": date,
                    "meet": meet_name,
                    "event": event_name,
                    "time": remy_res["time"],
                    "heat_place": remy_res["heat_place"],
                    "overall_place": overall_place,
                    "improvement": "0.00",
                    "video_url": ""
                })
                
    return races if races else None

def extract_with_gemini(pdf_content):
    """
    Fallback parser using Gemini 2.5 Flash if local parsing is skipped or unsuccessful.
    """
    if not HAS_GEMINI_SDK:
        print("Warning: google-genai SDK not installed. Cannot use Gemini fallback.")
        return None
        
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("Warning: GEMINI_API_KEY environment variable not set. Cannot use Gemini fallback.")
        return None

    print("Falling back to Gemini 2.5 Flash for PDF extraction...")
    client = genai.Client(api_key=api_key)
    
    prompt = """
    You are a data extraction assistant analyzing swimming meet results.
    Extract all race results (both individual and relay) for the athlete "Remy Benko" or "Benko, Remy".
    For each race he participated in, output a JSON object with these exact keys:
    - "date": YYYY-MM-DD format (infer from the PDF header).
    - "meet": Name of the meet (infer from the header).
    - "event": Full event name (e.g., "Boys 8&UN 25Y Freestyle").
    - "time": Final time recorded.
    - "heat_place": His place in his specific heat (the first number on his line, or "-" for relays).
    - "overall_place": Calculate his overall place by comparing his time to ALL other valid times in that specific event across all heats.
    - "improvement": Calculate time difference from his seed time to final time. Format as "-1.23" or "+0.50". If no seed time, output "0.00".
    - "video_url": Leave as an empty string "".

    Return ONLY a raw JSON list of these objects.
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            types.Part.from_bytes(
                data=pdf_content,
                mime_type='application/pdf',
            ),
            prompt
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    
    return json.loads(response.text)

def update_dashboard(all_new_races):
    if not all_new_races: 
        print("No races found to update.")
        return
    
    data_path = 'data/swimming.json'
    
    if os.path.exists(data_path):
        with open(data_path, 'r') as f:
            data = json.load(f)
    else:
        data = {"athlete": "Remy", "ribbon_count": 0, "ribbon_goal": 1000, "races": []}
    
    existing_keys = {f"{r['date']}-{r['event']}" for r in data['races']}
    added_count = 0

    for race in all_new_races:
        key = f"{race['date']}-{race['event']}"
        if key not in existing_keys:
            data['races'].append(race)
            data['ribbon_count'] += 1  
            added_count += 1

    if added_count > 0:
        # Sort races descending by date
        data['races'] = sorted(data['races'], key=lambda x: x['date'], reverse=True)
        with open(data_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Success: Added {added_count} new races to {data_path}!")
    else:
        print("Dashboard is already fully up to date.")

if __name__ == "__main__":
    pdf_urls = get_all_pdf_urls()
    all_extracted_races = []
    
    for pdf_url in pdf_urls:
        # Infer date from filename if possible, or we will extract it in the parser
        # Example filenames:
        # 2026-strawberry-seals-time-trials-results_014221.pdf -> 2026-04-25 (Practice meet)
        # 2026-05-02---srby-orca---results---2-col---may-2-2026_080369.pdf -> 2026-05-02
        # 2026-05-09-srby-mwwd-results_067731.pdf -> 2026-05-09
        # 2026-05-15-sms-srby-results-by-heat_002190.pdf -> 2026-05-16 (Actual date from header)
        
        date_map = {
            "time-trials": ("2026-04-25", "2026 Strawberry Seals Practice Meet"),
            "2026-05-02": ("2026-05-02", "Strawberry Seals @ Terra Linda Orcas"),
            "2026-05-09": ("2026-05-09", "Strawberry Seals @ Marinwood Waterdevils"),
            "2026-05-15": ("2026-05-16", "Strawberry Seals vs Swimarin Sharks"), # meet was May 16
        }
        
        inferred_date = "2026-05-16"
        meet_name = "Strawberry Seals vs Swimarin Sharks"
        for pattern, (d, m) in date_map.items():
            if pattern in pdf_url:
                inferred_date = d
                meet_name = m
                break
                
        print(f"\nProcessing {pdf_url} (Meet Date: {inferred_date})...")
        pdf_response = requests.get(pdf_url, headers={'User-Agent': 'Mozilla/5.0'})
        
        if pdf_response.status_code != 200:
            print(f"Failed to download PDF from {pdf_url}")
            continue
            
        races = None
        # Try local parsing first
        try:
            races = parse_pdf_locally(inferred_date, meet_name, pdf_response.content)
            if races:
                print(f"Successfully parsed {len(races)} races locally.")
        except Exception as e:
            print(f"Local parser failed: {e}")
            
        # Fall back to Gemini if local parsing returned nothing
        if not races:
            try:
                races = extract_with_gemini(pdf_response.content)
                if races:
                    print(f"Successfully extracted {len(races)} races via Gemini fallback.")
            except Exception as e:
                print(f"Gemini fallback failed: {e}")
                
        if races:
            all_extracted_races.extend(races)
            
    update_dashboard(all_extracted_races)

