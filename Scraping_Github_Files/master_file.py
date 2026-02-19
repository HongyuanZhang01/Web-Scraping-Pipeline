import os
import sys
import subprocess
from datetime import datetime

# ==========================================
#        MASTER CONFIGURATION
# ==========================================
KEYWORD = "YOUR_PROJECT_NAME_HERE"
SEARCH_QUERY = '(("your" AND "keywords") OR ("here" AND ":)")'
MAX_RESULTS = 1000 # Set to your preference
EMAIL = "yourgmail@gmail.com"
API_KEY = "YOUR_GEMINI_API_KEY_HERE"

# ==========================================
#        WORKSPACE SETUP
# ==========================================
# Generate dynamic folder name based on keyword and current time
timestamp = datetime.now().strftime("%Y%m%d_%H%M")
safe_keyword = "".join([c if c.isalnum() else "" for c in KEYWORD])
RUN_DIR = f"Run_{safe_keyword}_{timestamp}"

# Exact folder names requested
DIR_DATA = os.path.join(RUN_DIR, "step_result_csvs")
DIR_REPORTS = os.path.join(RUN_DIR, "Progress_Report")
DIR_PDFS = os.path.join(RUN_DIR, "Downloaded_PDFs")

# Create the folders
for d in [DIR_DATA, DIR_REPORTS, DIR_PDFS]:
    os.makedirs(d, exist_ok=True)

# Master Log File
LOG_FILE = os.path.join(DIR_REPORTS, "master_log.txt")

def log_and_print(msg):
    """Prints to terminal AND saves to master_log.txt simultaneously."""
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def run_step(step_name, script_name, args_list):
    """Runs a python script, captures its output, and halts if it fails."""
    log_and_print(f"\n{'='*50}\n🚀 STARTING {step_name}\n{'='*50}")
    
    cmd = [sys.executable, script_name] + args_list
    
    # --- NEW: Force Windows to use UTF-8 so emojis don't crash the script ---
    custom_env = os.environ.copy()
    custom_env["PYTHONIOENCODING"] = "utf-8"
    
    # Run process and capture output line by line
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True, 
        encoding='utf-8', 
        errors='replace',
        env=custom_env # Applies the UTF-8 rule
    )
    
    for line in process.stdout:
        clean_line = line.strip()
        print(clean_line)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(clean_line + "\n")
            
    process.wait()
    
    # Halt completely if the step crashed
    if process.returncode != 0:
        log_and_print(f"\n❌ FATAL ERROR: {step_name} failed with exit code {process.returncode}.")
        log_and_print("🛑 HALTING PIPELINE to prevent data corruption. Check the log and report files for details.")
        sys.exit(1)
    
    log_and_print(f"✅ {step_name} COMPLETED SUCCESSFULLY.")

# ==========================================
#        PIPELINE EXECUTION
# ==========================================
if __name__ == "__main__":
    log_and_print(f"INITIALIZING RESEARCH PIPELINE: {KEYWORD}")
    log_and_print(f"Workspace generated at: {RUN_DIR}")

    # Define exact file paths for this specific run
    csv_1 = os.path.join(DIR_DATA, "1_keyword_match_results.csv")
    csv_2 = os.path.join(DIR_DATA, "2_relevancy_filtered.csv")
    csv_3 = os.path.join(DIR_DATA, "3_download_status.csv")
    csv_4 = os.path.join(DIR_DATA, "4_formatted_import.csv")
    csv_5 = os.path.join(DIR_DATA, "5_final_analysis.csv")

    rep_1 = os.path.join(DIR_REPORTS, "step1_report.csv")
    rep_2 = os.path.join(DIR_REPORTS, "step2_report.csv")
    rep_3 = os.path.join(DIR_REPORTS, "step3_report.csv")
    rep_4 = os.path.join(DIR_REPORTS, "step4_report.csv")
    rep_5 = os.path.join(DIR_REPORTS, "step5_report.csv")

    # STEP 1
    run_step("STEP 1 (Search)", "step1_keyword_match.py", [
        "--query", SEARCH_QUERY, 
        "--max", str(MAX_RESULTS), 
        "--email", EMAIL,
        "--out", csv_1, 
        "--report", rep_1
    ])

# STEP 2
    run_step("STEP 2 (Relevancy Filter)", "step2_relevancy_filter.py", [
        "--in_csv", csv_1, "--out_csv", csv_2, "--report", rep_2, "--api", API_KEY
    ])

    # STEP 3
    run_step("STEP 3 (Download PDFs)", "step3_download_pdfs.py", [
        "--in_csv", csv_2, "--out_csv", csv_3, "--report", rep_3, 
        "--pdf_dir", DIR_PDFS, "--email", EMAIL
    ])

    # STEP 4
    run_step("STEP 4 (Formatting)", "step4_formatting.py", [
        "--in_csv", csv_3, "--out_csv", csv_4, "--report", rep_4
    ])

    # STEP 5
    run_step("STEP 5 (Analysis)", "step5_analysis.py", [
        "--in_csv", csv_4, "--out_csv", csv_5, "--report", rep_5, 
        "--pdf_dir", DIR_PDFS, "--api", API_KEY
    ])


    log_and_print(f"\n🎉 PIPELINE FINISHED COMPLETELY! Data saved in {RUN_DIR}/")


