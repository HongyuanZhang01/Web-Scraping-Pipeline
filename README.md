# Autonomous Research Pipeline

An end-to-end, fully automated Python pipeline for gathering and analyzing online research papers under a certain topic. This architecture searches academic databases, filters abstracts using Google's Gemini AI, automatically downloads Open Access PDFs, and runs parallel AI analysis on the downloaded PDFs.


## Features
* **Dynamic Orchestration:** A master script which connects the 5 distinct processing steps.
* **AI Abstract Filtering (Gemini 2.0 Flash):** Evaluates hundreds of papers against your custom inclusion/exclusion criteria for relevancy. This filters out all irrelevant results before attempting to download any PDFs. 
* **Smart PDF Scavenging:** Uses Unpaywall to track down open-access links and downloads them.
* **Parallel Processing:** Analyzes up to 10 full-text PDFs simultaneously to bypass long batch-processing queues; uses the PDFs to record methodology in the general analysis.
* **Robust Checkpointing:** Generates timestamped workspace folders for every run. Auto-saves progress in real time to prevent data loss.
* **Comprehensive Reporting:** Generates .CSV file reports detailing API rate limits, HTTP download errors (403, 404), and exact relevancy rejection reasons.

## Prerequisites
Python 3.9+ and a valid Google Gemini API Key. Gemini Pro is recommended for large scraping sizes.

Install the required packages:
```bash
pip install pyalex pandas requests thefuzz google-genai
```
## Configuration
Before running the pipeline, you must configure your specific research parameters.

1. **master_file.py**

Open the orchestrator file and fill out the MASTER CONFIGURATION section at the top:
* **KEYWORD:** The name of your run (e.g., "Machine_Learning_Bias").
* **SEARCH_QUERY:** Your boolean search string for OpenAlex.
* **MAX_RESULTS:** The maximum number of papers to fetch.
* **EMAIL:** Required by OpenAlex and Unpaywall for polite API usage.
* **API_KEY:** Your Google Gemini API Key.

2. **step2_relevancy_filter.py**

Locate the *SYSTEM_PROMPT* variable and update the INCLUSION CRITERIA to match the specific rules you want the AI to use when screening abstracts.

3. **step5_analysis.py**

Locate the *ANALYSIS_PROMPT* variable and update the instructions. Tell the AI exactly what data points you want extracted from the full-text PDFs.

## Usage
Activate your virtual environment and run the master file:

```bash
python master_file.py
```
## Output Architecture
The script will generate a dynamically named folder (e.g., Run_ProjectName_[year][mo][day]_[time]) containing:

* **📁 step_result_csvs/ -** The machine-used handoff files between steps. The final result of articles' dataset is titled *5_final_analysis.csv*.

* **📁 Progress_Report/ -** The CSVs files detailing what happened at each step, including failure logs and summary statistics. This leaves a paper trail easy to use to find roots of discrepancies.

* **📁 Downloaded_PDFs/ -** The full-text PDF files successfully retrieved from the web.
