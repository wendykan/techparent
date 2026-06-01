import os
import io
import json
import requests
import pdfplumber
from bs4 import BeautifulSoup
from datetime import datetime

# Updated to the exact 2026 schedule page
RESULTS_PAGE_URL = "https://www.gomotionapp.com/team/recmrssca/page/2026-springmsl/2026-msl-meet-schedule"
ATHLETE_NAME = "Benko, Remy"

def login_and_get_session():
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    
    username = os.environ.get('SWIM_USERNAME')
    password = os.environ.get('SWIM_PASSWORD')
    
    if username and password:
        print("Logging in...")
        # Add specific login POST request here if needed
        
    return session

def get_all_pdf_urls(session):
    print(f"Searching for meet results at {RESULTS_PAGE_URL}...")
    response = session.get(RESULTS_PAGE_URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    pdf_urls = []
    # Find all links on the page that end with .pdf
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.lower().endswith('.pdf'):
            if not href.startswith('http'):
                href = f"https://www.gomotionapp.com{href}"
            if href not in pdf_urls:
                pdf_urls.append(href)
                print(f"Found PDF: {href}")
            
    return pdf_urls

def parse_swim_pdf(session, pdf_url):
    print(f"Downloading and parsing {pdf_url}...")
    response = session.get(pdf_url)
    
    new_races = []
    current_event = "Unknown Event"
    current_date = datetime.now().strftime("%Y-%m-%d")

    with pdfplumber.open(io.BytesIO(response.content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
                
            lines = text.split('\n')
            for line in lines:
                if "2026" in line and "/" in line:
                    parts = line.split()
                    for p in parts:
                        if p.count('/') == 2:
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
                        "meet": "Weekly Meet",
                        "event": current_event,
                        "time": final_time,
                        "improvement": "0.00", 
                        "video_url": ""
                    })

    return new_races

def update_dashboard(all_new_races):
    if not all_new_races:
        print("No races to update.")
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
        data['races'] = sorted(data['races'], key=lambda x: x['date'], reverse=True)
        
        with open(data_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Successfully added {added_count} new races to the dashboard.")
    else:
        print("Data is already up to date. No new races added.")

if __name__ == "__main__":
    session = login_and_get_session()
    pdf_urls = get_all_pdf_urls(session)
    
    all_extracted_races = []
    for pdf_url in pdf_urls:
        extracted_races = parse_swim_pdf(session, pdf_url)
        all_extracted_races.extend(extracted_races)
        
    update_dashboard(all_extracted_races)
