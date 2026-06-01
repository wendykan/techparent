import os
import json
import requests
import base64
from bs4 import BeautifulSoup
import google.generativeai as genai

# Configuration
RESULTS_PAGE_URL = "https://www.gomotionapp.com/team/recmrssca/page/2026-springmsl/2026-msl-meet-schedule"
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

def get_all_pdf_urls():
    print(f"Searching for meet results at {RESULTS_PAGE_URL}...")
    response = requests.get(RESULTS_PAGE_URL, headers={'User-Agent': 'Mozilla/5.0'})
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

def extract_with_gemini(pdf_content):
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = """
    You are a data extraction assistant analyzing swimming meet results.
    Extract all race results (both individual and relay) for the athlete "Remy Benko" or "Benko, Remy".
    For each race he participated in, output a JSON object with these exact keys:
    - "date": YYYY-MM-DD format (infer from the PDF header).
    - "meet": Name of the meet (infer from the header).
    - "event": Full event name (e.g., "Event #7 Boys 8&UN 25Y Free").
    - "time": Final time recorded.
    - "heat_place": His place in his specific heat (the first number on his line, or "-" for relays).
    - "overall_place": Calculate his overall place by comparing his time to ALL other valid times in that specific event across all heats.
    - "improvement": Calculate time difference from his seed time to final time. Format as "-1.23" or "+0.50". If no seed time, output "0.00".
    - "video_url": Leave as an empty string "".

    Return ONLY a raw JSON list of these objects. Do not include markdown formatting like ```json.
    """
    
    response = model.generate_content([
        {'mime_type': 'application/pdf', 'data': base64.b64encode(pdf_content).decode('utf-8')},
        prompt
    ], generation_config={"response_mime_type": "application/json"})
    
    return json.loads(response.text)

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
        print(f"Added {added_count} new races via Gemini.")
    else:
        print("Dashboard is already up to date.")

if __name__ == "__main__":
    pdf_urls = get_all_pdf_urls()
    all_extracted_races = []
    
    for pdf_url in pdf_urls:
        print(f"Downloading and processing {pdf_url}...")
        pdf_response = requests.get(pdf_url, headers={'User-Agent': 'Mozilla/5.0'})
        
        try:
            races = extract_with_gemini(pdf_response.content)
            all_extracted_races.extend(races)
        except Exception as e:
            print(f"Error parsing {pdf_url} with Gemini: {e}")
            
    update_dashboard(all_extracted_races)
