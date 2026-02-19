import pandas as pd
import requests
import os
import time
import re
import argparse

# --- NEW: ARGPARSE SETUP ---
parser = argparse.ArgumentParser()
parser.add_argument("--in_csv", required=True)
parser.add_argument("--out_csv", required=True)
parser.add_argument("--report", required=True)
parser.add_argument("--pdf_dir", required=True)
parser.add_argument("--email", required=True)
args = parser.parse_args()

# --- CONFIGURATION (UPDATED TO USE ARGS) ---
INPUT_CSV = args.in_csv
OUTPUT_CSV = args.out_csv
DOWNLOAD_FOLDER = args.pdf_dir
EMAIL = args.email 

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

def sanitize_filename(citation):
    if pd.isna(citation): return "Unknown_File"
    clean = str(citation)
    
    # NEW: Force characters to standard ASCII English letters (fixes Unicode crashes)
    clean = clean.encode('ascii', errors='ignore').decode('ascii')
    
    # Original logic
    clean = re.sub(r'[\\/*?:"<>|]', "", clean)
    clean = clean.replace("\n", " ").replace("\r", "")
    return clean[:200].strip()

def check_unpaywall(doi):
    if pd.isna(doi) or not doi: return None
    url = f"https://api.unpaywall.org/v2/{doi}?email={EMAIL}"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            best_loc = data.get('best_oa_location', {})
            if best_loc: return best_loc.get('url_for_pdf')
    except: pass
    return None

# --- UPGRADED: CATCHES SPECIFIC HTTP ERROR CODES ---
def download_pdf(url, filename):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, stream=True, timeout=10)
        if resp.status_code == 200:
            ctype = resp.headers.get('Content-Type', '').lower()
            if 'pdf' in ctype or url.endswith('.pdf'):
                with open(filename, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True, "Success"
            else:
                return False, f"Wrong Content-Type (HTML/Login Page?): {ctype}"
        elif resp.status_code in [401, 403]:
            return False, f"HTTP {resp.status_code}: Paywall or Automation Blocked"
        elif resp.status_code == 404:
            return False, "HTTP 404: Dead Link"
        else:
            return False, f"HTTP Error {resp.status_code}"
    except requests.exceptions.Timeout:
        return False, "Server Timeout"
    except Exception as e:
        return False, f"Connection Error: {type(e).__name__}"

print("--- STARTING PRODUCTION DOWNLOAD ---")
df = pd.read_csv(INPUT_CSV)
df["Local_PDF_Path"] = "Not Downloaded"
df["Download_Status"] = "Pending"
df["Error_Reason"] = "" # New column to track exact failure cause

# Track which rows to keep
valid_indices = []

for index, row in df.iterrows():
    citation_key = row.get('Generated_Citation')
    if pd.isna(citation_key): citation_key = row.get('Title', 'Untitled')
    
    pdf_url = row.get('PDF_Link')
    doi = row.get('DOI')
    
    # 1. SCAVENGE IF NEEDED
    if pd.isna(pdf_url) or str(pdf_url) == "nan":
        if pd.notna(doi):
            print(f"   [Scavenging] Checking Unpaywall for DOI...")
            found_link = check_unpaywall(doi)
            if found_link:
                pdf_url = found_link
                df.at[index, "PDF_Link"] = found_link # Save retrieved link
    
    # 2. FILTER: If we still have no link and no DOI, mark for deletion
    if (pd.isna(pdf_url) or str(pdf_url) == "nan") and (pd.isna(doi) or str(doi) == "nan"):
        print(f"   [Dropping] No Link/DOI for: {citation_key[:30]}...")
        df.at[index, "Download_Status"] = "Dropped (No Access)"
        df.at[index, "Error_Reason"] = "No Link or DOI Available"
        continue # Skip download, will be filtered out later

    valid_indices.append(index)

    # 3. DOWNLOAD (If link exists)
    if pdf_url and str(pdf_url) != "nan":
        safe_name = sanitize_filename(citation_key) + ".pdf"
        file_path = os.path.join(DOWNLOAD_FOLDER, safe_name)
        
        print(f"[{index+1}] Downloading: {safe_name[:40]}...")
        
        # Capture the success boolean AND the specific error reason
        success, reason = download_pdf(pdf_url, file_path)
        
        if success:
            df.at[index, "Local_PDF_Path"] = file_path
            df.at[index, "Download_Status"] = "Success"
        else:
            df.at[index, "Download_Status"] = "Failed (Link Exists)"
            df.at[index, "Error_Reason"] = reason
    else:
        df.at[index, "Download_Status"] = "Link Only (No PDF URL)"
        df.at[index, "Error_Reason"] = "URL Missing entirely"
        
    time.sleep(1)

# --- CLEANUP & SAVE ---
# Only keep rows that are "Success", "Failed (Link Exists)", or "Link Only"
# Drop rows that had absolutely nothing.
final_df = df.loc[valid_indices].copy()
final_df.to_csv(OUTPUT_CSV, index=False)

print(f"Done. Processed {len(final_df)} valid papers.")
print(f"Dropped {len(df) - len(final_df)} dead ends.")

# ==========================================
#        NEW: PROGRESS REPORT GENERATION
# ==========================================
print("--- GENERATING STEP 3 REPORT ---")
stats = final_df["Download_Status"].value_counts().to_dict()
failed_df = final_df[final_df["Download_Status"] != "Success"]

# Tally up the specific error reasons
error_counts = failed_df["Error_Reason"].value_counts().to_dict()

report_data = [
    {"File/Title": "Input File", "Status": args.in_csv, "Reason": "SUMMARY STATS"},
    {"File/Title": "Output File", "Status": args.out_csv, "Reason": ""},
    {"File/Title": "Total Attempted", "Status": len(final_df), "Reason": ""},
    {"File/Title": "Successfully Downloaded", "Status": stats.get("Success", 0), "Reason": ""},
    {"File/Title": "Total Failed / Blocked", "Status": len(failed_df), "Reason": ""},
    {"File/Title": "---", "Status": "---", "Reason": "---"},
    {"File/Title": "ERROR BREAKDOWN", "Status": "COUNT", "Reason": ""}
]

# Dynamically add each error type and how many times it happened
for err_reason, count in error_counts.items():
    if str(err_reason).strip() != "":
        report_data.append({"File/Title": str(err_reason), "Status": count, "Reason": ""})

# Add the detailed line-by-line breakdown below the summary
report_data.extend([
    {"File/Title": "---", "Status": "---", "Reason": "---"},
    {"File/Title": "FAILED FILE TITLE", "Status": "DOWNLOAD STATUS", "Reason": "SPECIFIC ERROR CAUSE"}
])

for _, row in failed_df.iterrows():
    report_data.append({
        "File/Title": str(row.get("Title", "Untitled"))[:80], 
        "Status": row.get("Download_Status", "Unknown"), 
        "Reason": row.get("Error_Reason", "Unknown")
    })

pd.DataFrame(report_data).to_csv(args.report, index=False)
print(f"Report saved to '{args.report}'.")