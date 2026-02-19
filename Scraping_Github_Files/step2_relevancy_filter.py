import pandas as pd
from google import genai
import time
import json
import math
import argparse

# --- NEW: ARGPARSE SETUP ---
parser = argparse.ArgumentParser()
parser.add_argument("--in_csv", required=True)
parser.add_argument("--out_csv", required=True)
parser.add_argument("--report", required=True)
parser.add_argument("--api", required=True)
args = parser.parse_args()

# --- CONFIGURATION (UPDATED TO USE ARGS) ---
INPUT_CSV = args.in_csv
OUTPUT_CSV = args.out_csv
BATCH_SIZE = 20
API_KEY = args.api

# Quality Settings
MIN_ABSTRACT_LENGTH = 50
REQUIRE_DOI = False

# --- NEW GENAI CLIENT SETUP ---
client = genai.Client(api_key=API_KEY)

SYSTEM_PROMPT = """
You are a strict research assistant conducting a systematic review.
We are looking for papers on [YOUR TOPIC HERE].

INCLUSION CRITERIA (Must meet ALL):
1. Topic: Explicitly discusses [CRITERIA 1].
2. Mechanism: Discusses [CRITERIA 2].
3. Subject: Involves [CRITERIA 3].

TASK:
I will provide a list of papers.
Return a raw JSON list of objects. One object for each paper.
Format:
[
  {"ID": 123, "Included": true, "Reason": "..."},
  {"ID": 124, "Included": false, "Reason": "..."}
]
"""

def pre_flight_check(paper):
    abstract = str(paper.get('Abstract', ''))
    if len(abstract) < MIN_ABSTRACT_LENGTH:
        return False, "Abstract too short"
    
    bad_phrases = ["no abstract", "abstract available", "see full text"]
    if any(phrase in abstract.lower() for phrase in bad_phrases):
        return False, "Placeholder text"

    if REQUIRE_DOI and pd.isna(paper.get('DOI')):
        return False, "Missing DOI"

    return True, "Passed"

def screen_batch(papers_batch):
    batch_text = ""
    for p in papers_batch:
        batch_text += f"--- PAPER ID: {p['ID']} ---\nTitle: {p['Title']}\nAbstract: {str(p['Abstract'])[:2000]}\n\n"

    full_prompt = f"{SYSTEM_PROMPT}\n\nDATA TO ANALYZE:\n{batch_text}"

    # Try up to 3 times if Google is busy
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=full_prompt
            )
            clean_json = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
            
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                print(f"   [API Busy] Google Rate Limit hit. Waiting 10 seconds before retry {attempt+1}/3...")
                time.sleep(10) # Pause to let the API cool down
            else:
                print(f"   Batch AI Error: {error_msg}")
                return []
                
    print("   Failed after 3 attempts. Skipping batch.")
    return []

print("--- STARTING BATCH SCREENING ---")
df = pd.read_csv(INPUT_CSV)
df['Temp_ID'] = range(len(df))
df["Included"] = False
df["Rejection_Reason"] = ""

valid_papers_for_ai = []

# Phase 1: Pre-Flight
for index, row in df.iterrows():
    p_dict = row.to_dict()
    is_valid, reason = pre_flight_check(p_dict)
    if is_valid:
        valid_papers_for_ai.append(p_dict)
    else:
        df.at[index, "Included"] = False
        df.at[index, "Rejection_Reason"] = f"Auto-Reject: {reason}"

print(f"   Queued {len(valid_papers_for_ai)} papers for AI.")

# Phase 2: AI Batching
if valid_papers_for_ai:
    results_map = {}
    total_batches = math.ceil(len(valid_papers_for_ai) / BATCH_SIZE)
    
    for i in range(0, len(valid_papers_for_ai), BATCH_SIZE):
        batch = valid_papers_for_ai[i : i + BATCH_SIZE]
        print(f"   Batch {(i // BATCH_SIZE) + 1}/{total_batches}...")
        
        mini_batch = [{"ID": p['Temp_ID'], "Title": p['Title'], "Abstract": p['Abstract']} for p in batch]
        
        batch_decisions = screen_batch(mini_batch)
        
        for decision in batch_decisions:
            results_map[decision.get("ID")] = decision
        time.sleep(1)

    # Phase 3: Merge
    for index, row in df.iterrows():
        temp_id = row['Temp_ID']
        if temp_id in results_map:
            res = results_map[temp_id]
            df.at[index, "Included"] = res.get("Included", False)
            df.at[index, "Rejection_Reason"] = res.get("Reason", "Unknown")

# Save
filtered_df = df[df["Included"] == True]
filtered_df.to_csv(OUTPUT_CSV, index=False)
print(f"DONE. Included: {len(filtered_df)}")

# ==========================================
#        NEW: PROGRESS REPORT GENERATION
# ==========================================
print("--- GENERATING STEP 2 REPORT ---")
report_data = [
    {"Input File": args.in_csv, "Output File": args.out_csv, "Status/Reason": "SUMMARY STATS"},
    {"Input File": "Total Evaluated", "Output File": len(df), "Status/Reason": ""},
    {"Input File": "Total Relevant (Kept)", "Output File": len(filtered_df), "Status/Reason": ""},
    {"Input File": "Total Irrelevant (Rejected)", "Output File": len(df) - len(filtered_df), "Status/Reason": ""},
    {"Input File": "---", "Output File": "---", "Status/Reason": "---"},
    {"Input File": "PAPER ID", "Output File": "TITLE", "Status/Reason": "REJECTION REASON"}
]

# Append the detailed list of rejected papers
rejected_df = df[df["Included"] == False]
for _, row in rejected_df.iterrows():
    report_data.append({
        "Input File": row.get("ID", "Unknown"), 
        "Output File": str(row.get("Title", "Untitled"))[:80], 
        "Status/Reason": row.get("Rejection_Reason", "Unknown")
    })

pd.DataFrame(report_data).to_csv(args.report, index=False)

print(f"Report saved to '{args.report}'.")

