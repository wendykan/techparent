import os
import io
import json
import requests
import pdfplumber
from bs4 import BeautifulSoup
from datetime import datetime

# The main page where the team posts the weekly result PDFs
RESULTS_PAGE_URL = "https://www.gomotionapp.com/team/recmrssca/page/events/meet-results" # UPDATE THIS
ATHLETE_NAME = "Benko, Remy"

def login_and_get_session():
    # If the results page is public, you can skip logging in and just return requests.Session()
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    
    username = os.environ.get('SWIM_USERNAME')
    password = os.environ.get('SWIM_PASSWORD')
    
    if username and password:
        print("Logging in...")
        # TODO: Add specific login POST request if the PDFs are behind a password
        # session.post("LOGIN_URL", data={"user": username, "pass": password})
        
    return session

def get_latest_pdf_url(session):
    print("Searching for the latest meet results...")
    response = session.get(RESULTS_PAGE_URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the first link that ends with .pdf (assuming the newest is at the top)
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.lower().endswith('.pdf'):
            # Handle relative URLs natively
            if not href.startswith('http'):
                href = f"https://www.gomotionapp.com{href}"
            print(f"Found latest PDF: {href}")
            return href
            
    print("No PDF links found on the results page.")
    return None

def parse_swim_pdf(session, pdf_url):
    print(f"Downloading and parsing {pdf_url}...")
    response = session.get(pdf_url)
    
    new_races = []
    current_event = "Unknown Event"
    current_date = datetime.now().strftime("%Y-%m-%d") # Fallback date

    with pdfplumber.open(io.BytesIO(response.content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
                
            lines = text.split('\n')
            for line in lines:
                # Attempt to extract the meet date from the header (e.g., "05/16/2026")
                if "2026" in line and "/" in line:
                    parts = line.split()
                    for p in parts:
                        if p.count('/') == 2:
                            # Format mm/dd/yyyy to yyyy-mm-dd
                            try:
                                dt = datetime.strptime(p, "%m/%d/%Y")
                                current_date = dt.strftime("%Y-%m-%d")
                            except ValueError:
                                pass

                if "Event" in line and "Boys" in line:
                    current_event = line.strip()
                
                if ATHLETE_NAME in line:
                    tokens = line.split()
                    final_time = tokens[-1]
                    
                    new_races.append({
                        "date": current_date,
                        "meet": "Weekly Meet", # Could also parse the meet name from the header
                        "event": current_event,
                        "time": final_time,
                        "improvement": "0.00", # Delta logic can be added later
                        "video_url": ""
                    })
                    print(f"Parsed: {current_event} -> {final_time}s")

    return new_races

def update_dashboard(new_races):
    if not new_races:
        print("No races to update.")
        return

    data_path = 'data/swimming.json'
    
    # Load existing data
    if os.path.exists(data_path):
        with open(data_path, 'r') as f:
            data = json.load(f)
    else:
        # Fallback if file doesn't exist
        data = {"athlete": "Remy", "ribbon_count": 0, "ribbon_goal": 1000, "races": []}

    # Prevent duplicates by checking date and event
    existing_keys = {f"{r['date']}-{r['event']}" for r in data['races']}
    added_count = 0

    for race in new_races:
        key = f"{race['date']}-{race['event']}"
        if key not in existing_keys:
            data['races'].append(race)
            data['ribbon_count'] += 1  # Add a ribbon for the new race!
            added_count += 1

    if added_count > 0:
        # Sort races chronologically
        data['races'] = sorted(data['races'], key=lambda x: x['date'], reverse=True)
        
        with open(data_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Successfully added {added_count} new races to the dashboard.")
    else:
        print("Data is already up to date. No new races added.")

if __name__ == "__main__":
    session = login_and_get_session()
    latest_pdf = get_latest_pdf_url(session)
    
    if latest_pdf:
        extracted_races = parse_swim_pdf(session, latest_pdf)
        update_dashboard(extracted_races)
