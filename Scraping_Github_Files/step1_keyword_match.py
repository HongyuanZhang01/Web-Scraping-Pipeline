import pyalex
from pyalex import Works
import pandas as pd
import time
import argparse

# --- NEW: ARGPARSE SETUP ---
parser = argparse.ArgumentParser()
parser.add_argument("--query", required=True)
parser.add_argument("--max", type=int, required=True)
parser.add_argument("--email", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--report", required=True)
args = parser.parse_args()

# --- CONFIGURATION (UPDATED TO USE ARGS) ---
pyalex.config.email = args.email

# The 3-Pronged Query
SEARCH_QUERY = args.query
MAX_RESULTS = args.max 

def format_citation(paper):
    """
    Constructs an APA-style citation. This string is the PERMANENT ID.
    """
    try:
        authorships = paper.get('authorships', [])
        if not authorships:
            auth_str = "Unknown Author"
        else:
            names = [a.get('author', {}).get('display_name', 'Unknown') for a in authorships]
            if len(names) > 3:
                auth_str = f"{names[0]} et al."
            elif len(names) > 1:
                auth_str = " & ".join(names)
            else:
                auth_str = names[0]
        
        year = paper.get('publication_year', 'n.d.')
        title = paper.get('title', 'Untitled')
        
        source = paper.get('primary_location', {}).get('source', {})
        journal = source.get('display_name', '') if source else ""
        
        # Format: Smith, J. (2020). The Title. Journal.
        citation = f"{auth_str} ({year}). {title}."
        if journal:
            citation += f" {journal}."
            
        return citation
    except Exception:
        return f"Unknown Paper ({paper.get('id')})"

def reconstruct_abstract(inverted_index):
    if not inverted_index: return None
    word_list = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_list.append((pos, word))
    word_list.sort()
    return " ".join([w[1] for w in word_list])

print(f"--- STARTING SEARCH (WITH CITATION GENERATION) ---")

try:
    pager = Works().search(SEARCH_QUERY).filter(has_abstract=True)
    results = []
    count = 0
    
    for page in pager.paginate(per_page=100):
        for paper in page:
            if count >= MAX_RESULTS: break
            
            abstract = reconstruct_abstract(paper.get('abstract_inverted_index'))
            pdf_link = paper.get('open_access', {}).get('oa_url') if paper.get('open_access') else None
            
            full_citation = format_citation(paper)
            
            item = {
                "ID": paper.get('id'),
                "Generated_Citation": full_citation, 
                "Title": paper.get('title'),
                "Year": paper.get('publication_year'),
                "DOI": paper.get('doi'),
                "Abstract": abstract,
                "PDF_Link": pdf_link,
                "Source": "OpenAlex"
            }
            results.append(item)
            count += 1
        
        print(f"   Collected {count} papers...")
        if count >= MAX_RESULTS: break

except Exception as e:
    print(f"Error: {e}")

df = pd.DataFrame(results)
df.to_csv(args.out, index=False)
print(f"Saved to '{args.out}'.")

# ==========================================
#        NEW: PROGRESS REPORT GENERATION
# ==========================================
print("--- GENERATING STEP 1 REPORT ---")
year_counts = df['Year'].value_counts().to_dict() if not df.empty else {}

report_data = [
    {"Metric": "Input Source", "Value": "OpenAlex API"},
    {"Metric": "Output File Generated", "Value": args.out},
    {"Metric": "Search Query Used", "Value": args.query},
    {"Metric": "Total Papers Found & Extracted", "Value": len(df)},
    {"Metric": "---", "Value": "---"},
    {"Metric": "YEAR BREAKDOWN", "Value": ""}
]

# Add the breakdown of years to the report
for y, c in sorted(year_counts.items(), reverse=True):
    report_data.append({"Metric": f"Year {y}", "Value": c})

pd.DataFrame(report_data).to_csv(args.report, index=False)
print(f"Report saved to '{args.report}'.")