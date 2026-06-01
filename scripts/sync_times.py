import os
import io
import json
import requests
import pdfplumber
from bs4 import BeautifulSoup
from datetime import datetime

RESULTS_PAGE_URL = "https://www.gomotionapp.com/team/recmrssca/page/2026-springmsl/2026-msl-meet-schedule"
ATHLETE_NAME_1 = "Benko, Remy"
ATHLETE_NAME_2 = "Remy Benko" # Some meets format it differently

def login_and_get_session():
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    username = os.environ.get('SWIM_USERNAME')
    password = os.environ.get('SWIM_PASSWORD')
    if username and password:
        print("Logging in...")
    return session

def get_all_pdf_urls(session):
    print(f"Searching for meet results at {RESULTS_PAGE_URL}...")
    response = session.get(RESULTS_PAGE_URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    pdf_urls = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.lower().endswith('.pdf'):
            if not href.startswith('http'):
                href = f"https://www.gomotionapp.com{href}"
            if href not in pdf_urls:
                pdf_urls.append(href)
    return pdf_urls

def time_to_seconds(time_str):
    """Converts MM:SS.ms or SS.ms to raw seconds for sorting."""
    time_str = time_str.replace(':', '.')
    parts = time_str.split('.')
    if len(parts) == 3: # MM:SS.ms
        return int(parts[0]) * 60 + int(parts[1]) + float(f"0.{parts[2]}")
    elif len(parts) == 2: # SS.ms
        return int(parts[0]) + float(f"0.{parts[1]}")
    return 9999.99

def parse_swim_pdf(session, pdf_url):
    print(f"Parsing {pdf_url}...")
    response = session.get(pdf_url)
    
    new_races = []
    event_times = {} # Stores all times for each event to calculate overall place
    current_event = "Unknown Event"
    current_date = datetime.now().strftime("%Y-%m-%d")

    with pdfplumber.open(io.BytesIO(response.content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
                
            lines = text.split('\n')
            for line in lines:
                # 1. Parse Meet Date
                if "2026" in line and "/" in line:
                    for p in line.split():
                        if p.count('/') == 2:
                            try:
                                current_date = datetime.strptime(p, "%m/%d/%Y").strftime("%Y-%m-%d")
                            except ValueError: pass

                # 2. Track Current Event
                if "Event" in line and "Boys" in line:
                    current_event = line.strip()
                    if current_event not in event_times:
                        event_times[current_event] = []
                
                # 3. Collect ALL valid times in the event for overall ranking
                tokens = line.split()
                if tokens and tokens[0].isdigit():
                    final_time = tokens[-1]
                    # Check if it's a valid time (contains a dot, not NS/DQ)
                    if '.' in final_time and not final_time.isalpha():
                        event_times[current_event].append(time_to_seconds(final_time))
                
                # 4. Extract Remy's specific data
                if ATHLETE_NAME_1 in line or ATHLETE_NAME_2 in line:
                    final_time = tokens[-1]
                    heat_place = tokens[0] # The first number on his line
                    
                    if '.' in final_time:
                        new_races.append({
                            "date": current_date,
                            "meet": "Weekly Meet",
                            "event": current_event,
                            "time": final_time,
                            "time_sec": time_to_seconds(final_time),
                            "heat_place": heat_place,
                            "overall_place": "TBD", # Will calculate below
                            "improvement": "0.00", 
                            "video_url": ""
                        })

    # 5. Calculate Overall Place by comparing Remy's time to all times in that event
    for race in new_races:
        all_times = sorted(event_times.get(race["event"], []))
        # Find his rank (index + 1)
        if race["time_sec"] in all_times:
            race["overall_place"] = str(all_times.index(race["time_sec"]) + 1)
        
        # Clean up temporary sorting key
        del race["time_sec"]

    return new_races

def update_dashboard(all_new_races):
    if not all_new_races: return
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
        data['races'] = sorted(data['races'], key=lambda x: x['date'], reverse=True)
        with open(data_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Added {added_count} new races.")

if __name__ == "__main__":
    session = login_and_get_session()
    pdf_urls = get_all_pdf_urls(session)
    
    all_extracted_races = []
    for pdf_url in pdf_urls:
        all_extracted_races.extend(parse_swim_pdf(session, pdf_url))
        
    update_dashboard(all_extracted_races)
