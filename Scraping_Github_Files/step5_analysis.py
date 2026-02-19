import pandas as pd
import os
import time
import json
import shutil
import sys
import threading
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
# pip install thefuzz
from thefuzz import fuzz 
from google import genai
from google.genai import types

# --- NEW: ARGPARSE SETUP ---
parser = argparse.ArgumentParser()
parser.add_argument("--in_csv", required=True)
parser.add_argument("--out_csv", required=True)
parser.add_argument("--report", required=True)
parser.add_argument("--pdf_dir", required=True)
parser.add_argument("--api", required=True)
args = parser.parse_args()

# ==========================================
#              CONFIGURATION
# ==========================================
GEMINI_API_KEY = args.api
INPUT_CSV = args.in_csv          
OUTPUT_CSV = args.out_csv
LOCAL_PDF_FOLDER = args.pdf_dir 
CITATION_COL = "Full Citation"                
MODEL_NAME = "gemini-2.0-flash"

# Parallelism: 10 papers at once (Safe for standard API limits)
MAX_WORKERS = 10  

ANALYSIS_PROMPT = """
Analyze this PDF research paper. The goal is to [YOUR GOAL HERE].
1. Identify the [METRIC 1]. Choose ONE from: [Category A, Category B, Category C, Other].
2. Provide a brief "Reason" (max 1 sentence).

Return the result as a valid JSON object with these keys:
- "methodology": "The chosen category",
- "reason": "The explanation"
"""

# ==========================================
#              SETUP & UTILS
# ==========================================

if "PASTE" in GEMINI_API_KEY:
    print("❌ Error: Please update GEMINI_API_KEY inside the script!")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)
csv_lock = threading.Lock() # Prevents file corruption when saving

def normalize_text(text):
    text = str(text).lower().replace('.pdf', '')
    import re
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return " ".join(text.split())

def find_best_local_match(citation, local_files):
    clean_cit = normalize_text(citation)
    best_file = None
    best_score = -1
    for fname in local_files:
        clean_file = normalize_text(fname)
        score = fuzz.token_set_ratio(clean_cit, clean_file)
        if score > best_score:
            best_score = score
            best_file = fname
    return best_file, best_score

def analyze_single_paper(row_idx, filename):
    """
    Uploads 1 PDF, Analyzes it, and returns the result immediately.
    """
    original_path = os.path.join(LOCAL_PDF_FOLDER, filename)
    
    # Safe Temp File (Avoids Windows encoding issues)
    temp_safe_name = f"temp_fast_{row_idx}.pdf"
    temp_path = os.path.join(LOCAL_PDF_FOLDER, temp_safe_name)
    
    try:
        shutil.copy2(original_path, temp_path)
        
        # Upload using standard API (NOT Batch)
        gemini_file = client.files.upload(file=temp_path)
        
        # Wait for processing
        while gemini_file.state.name == "PROCESSING":
            time.sleep(1)
            gemini_file = client.files.get(name=gemini_file.name)
            
        if gemini_file.state.name == "FAILED":
            return row_idx, "Error", "File processing failed"

        # Generate Content
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(text=ANALYSIS_PROMPT),
                        types.Part(file_data=types.FileData(
                            mime_type=gemini_file.mime_type,
                            file_uri=gemini_file.uri
                        ))
                    ]
                )
            ]
        )

        # Cleanup Cloud File
        try:
            client.files.delete(name=gemini_file.name)
        except:
            pass
            
        # Parse Result
        text = response.text
        clean_json = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)
        
        return row_idx, data.get("methodology", "Unknown"), data.get("reason", "")

    except Exception as e:
        # print(f"   [Row {row_idx}] Failed: {e}")
        return row_idx, "Error", str(e)
    finally:
        # Cleanup Local Temp
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

def run_fast_pipeline():
    print(f"--- STARTING FAST LANE ANALYSIS ({MAX_WORKERS} threads) ---")
    
    # 1. Load Data
    try:
        # We try to load the OUTPUT file first to resume progress
        if os.path.exists(OUTPUT_CSV):
            df = pd.read_csv(OUTPUT_CSV)
            print(f"Resuming from '{OUTPUT_CSV}' ({len(df)} rows).")
        else:
            df = pd.read_csv(INPUT_CSV)
            print(f"Loaded fresh '{INPUT_CSV}' ({len(df)} rows).")
            # Create the output file immediately
            df.to_csv(OUTPUT_CSV, index=False)
            
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    # 2. Prepare File List
    if not os.path.exists(LOCAL_PDF_FOLDER):
        print("Error: PDF folder not found.")
        return
    local_pdfs = [f for f in os.listdir(LOCAL_PDF_FOLDER) if f.lower().endswith('.pdf')]
    
    tasks = []
    print("Matching files...")
    
    for index, row in df.iterrows():
        citation = str(row.get(CITATION_COL, ''))
        link_status = str(row.get("Link", ""))
        existing_method = str(row.get("Method", ""))
        
        # SKIP if already done (Resume capability)
        if existing_method not in ["nan", "", "None", "Unknown"]:
             continue

        if not citation or "---" in citation or "Online Link Only" in link_status:
            continue
            
        matched_file, score = find_best_local_match(citation, local_pdfs)
        if score > 85:
            tasks.append((index, matched_file))

    if not tasks:
        print("All papers are already analyzed! (Or none matched).")
        return

    print(f"Queueing {len(tasks)} papers for immediate analysis...")

    # 3. Parallel Execution
    completed_count = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_row = {
            executor.submit(analyze_single_paper, row_idx, fname): row_idx 
            for row_idx, fname in tasks
        }
        
        # Process as they finish
        for future in as_completed(future_to_row):
            row_idx, method, reason = future.result()
            
            # Thread-safe CSV update
            with csv_lock:
                df.at[row_idx, "Method"] = method
                # df.at[row_idx, "Reason"] = reason # Optional
                
                # Auto-save every row (Robustness!)
                df.to_csv(OUTPUT_CSV, index=False)
            
            completed_count += 1
            print(f"✅ [{completed_count}/{len(tasks)}] Row {row_idx}: {method}")

    print(f"\nSUCCESS! Processed {completed_count} papers.")
    print(f"Saved to '{OUTPUT_CSV}'.")

    # ==========================================
    #        NEW: PROGRESS REPORT GENERATION
    # ==========================================
    print("--- GENERATING STEP 5 REPORT ---")
    method_counts = df["Method"].value_counts().to_dict()
    
    report_data = [
        {"Metric": "Input File Used", "Value": args.in_csv},
        {"Metric": "Output File Generated", "Value": args.out_csv},
        {"Metric": "Total Papers Evaluated by AI", "Value": len(tasks)},
        {"Metric": "---", "Value": "---"},
        {"Metric": "METHODOLOGY DISTRIBUTION", "Value": ""}
    ]
    
    for m, c in method_counts.items():
        if str(m) not in ["nan", "---", ""]: 
            report_data.append({"Metric": str(m), "Value": c})

    pd.DataFrame(report_data).to_csv(args.report, index=False)
    print(f"Report saved to '{args.report}'.")


if __name__ == "__main__":

    run_fast_pipeline()

