import pandas as pd
import re
import argparse

# --- NEW: ARGPARSE SETUP ---
parser = argparse.ArgumentParser()
parser.add_argument("--in_csv", required=True)
parser.add_argument("--out_csv", required=True)
parser.add_argument("--report", required=True)
args = parser.parse_args()

# --- CONFIGURATION (UPDATED TO USE ARGS) ---
INPUT_CSV = args.in_csv
OUTPUT_CSV = args.out_csv

def extract_auth_from_citation(citation):
    """
    Extracts the author block from the citation string.
    Expects format: "Author, A. (Year). Title..."
    Returns: "Author, A."
    """
    if pd.isna(citation): return "Unknown"
    
    # Regex: Capture everything before the first "(Year)"
    match = re.search(r'^(.*?)\s*\((\d{4}|n\.d\.)\)', str(citation))
    if match:
        return match.group(1).strip()
    return "Unknown"

print("--- STARTING FINAL EXPORT WITH SEPARATOR ---")

try:
    df = pd.read_csv(INPUT_CSV)
    
    # 1. Define Columns
    # Map the raw data to your requested headers
    df["Full Citation"] = df["Generated_Citation"]
    df["Link"] = df["PDF_Link"]
    df["Auth"] = df["Generated_Citation"].apply(extract_auth_from_citation)
    df["Year"] = df["Year"]
    df["Full Abstract"] = df["Abstract"]
    df["Method"] = ""  # Empty for Step 5
    
    # Select only the columns we need
    cols = ["Full Citation", "Link", "Auth", "Year", "Full Abstract", "Method"]
    df = df[cols].copy()
    
    # 2. Split into Two Groups
    # Group A: Successfully Downloaded (The ones Step 5 can analyze automatically)
    raw_df = pd.read_csv(INPUT_CSV) # Need to read raw again to get Download_Status
    df_downloaded = df[raw_df["Download_Status"] == "Success"].copy()
    
    # Group B: Failed Download but has Link (The ones for manual review)
    # Logic: Status is NOT success, but PDF_Link is NOT empty
    mask_links_only = (raw_df["Download_Status"] != "Success") & (raw_df["PDF_Link"].notna())
    df_links_only = df[mask_links_only].copy()
    
    print(f"   Group A (Downloaded): {len(df_downloaded)} papers")
    print(f"   Group B (Links Only): {len(df_links_only)} papers")

    # 3. Create the Separator Row
    separator_row = pd.DataFrame([{
        "Full Citation": "--- END OF DOWNLOADED FILES --- (Manual Review Below)",
        "Link": "---",
        "Auth": "---",
        "Year": "---",
        "Full Abstract": "---",
        "Method": "---"
    }])
    
    # 4. Combine: A -> Separator -> B
    final_df = pd.concat([df_downloaded, separator_row, df_links_only], ignore_index=True)
    
    # 5. Save
    final_df.to_csv(OUTPUT_CSV, index=False)
    
    print(f"\nSUCCESS! Saved to '{OUTPUT_CSV}'.")
    print("Open this file in Excel/Google Sheets to see the separation.")

    # ==========================================
    #        NEW: PROGRESS REPORT GENERATION
    # ==========================================
    print("--- GENERATING STEP 4 REPORT ---")
    report_data = [
        {"Metric": "Input File Used", "Value": args.in_csv},
        {"Metric": "Output File Generated", "Value": args.out_csv},
        {"Metric": "Group A (Downloaded - AI Ready)", "Value": len(df_downloaded)},
        {"Metric": "Group B (Links Only - Manual Review)", "Value": len(df_links_only)},
        {"Metric": "Total Rows in Final Sheet", "Value": len(final_df)}
    ]
    pd.DataFrame(report_data).to_csv(args.report, index=False)
    print(f"Report saved to '{args.report}'.")

except Exception as e:
    print(f"Error: {e}")