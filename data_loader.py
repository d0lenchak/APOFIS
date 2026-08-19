import pandas as pd
import numpy as np
import re
from config import DATA_FILES, is_program_finance_account, extract_account_code

# data loader

# MATCHING FUNCTIONS

# =============================================
def get_pcode(project_str): # bsb, PO, process df
    if pd.isna(project_str):
        return None
    match = re.match(r'(P\d+)', str(project_str))
    return match.group(1) if match else None

# =============================================
def get_studyid(project_str): # bsb, process df
    if pd.isna(project_str):
        return None
    project_str = str(project_str)
    # YYYY-ZZZZ
    match = re.search(r'\.(\d{4}-\d{4})', project_str)
    if match:
        return match.group(1)
    # YYYY.ZZZ
    match = re.search(r'\.(\d{4}\.\d{3})', project_str)
    if match:
        return match.group(1)
    # YYYY.ZZZZ
    match = re.search(r'\.(\d{4}\.\d{4})', project_str)
    if match:
        return match.group(1)
    # if not, find Gen...
    parts = project_str.split('.')
    if len(parts) >= 2:
        identifier = '.'.join(parts[-3:]) if len(parts) >= 3 else '.'.join(parts[-2:])
        identifier = identifier.strip()
        return identifier if identifier else 'Other'
    return 'Other'

# =============================================
def get_studyid_sdr(study_number_str):
    if pd.isna(study_number_str):
        return None
    study_number_str = str(study_number_str).strip()
    # get anything after the '-'
    if '-' in study_number_str:
        parts = study_number_str.split('-')
        last_part = parts[-1].strip()
        match = re.search(r'(\d{3,4})', last_part) # get 3 or 4 digit compact study ID
        if match:
            return match.group(1)
    return None

# =============================================
def clean_account(account_str):
    if pd.isna(account_str):
        return None
    account_str = str(account_str).strip()
    # A0000 or P2-A0000
    match = re.search(r'([AP]\d{5}|P2-[AP]\d{5})', account_str)
    if match:
        code = match.group(1)
        # get description
        desc_match = re.search(r'(?:P2-)?[AP]\d{5}-(.+)', account_str)
        if desc_match:
            description = desc_match.group(1).strip()
            # limit str length
            if len(description) > 50:
                description = description[:47] + '...'
            return f"{code} - {description}"
        else:
            return code
    # default if not ^
    parts = account_str.split('-', 1)
    if len(parts) >= 2:
        code = parts[0].strip()
        desc = parts[1].strip()
        if len(desc) > 50:
            desc = desc[:47] + '...'
        return f"{code} - {desc}"
    return account_str[:60]  # last resort: use truncated string

# =============================================================================================
# LOAD DATA
# =============================================================================================

def load_core_actuals():
    file_path = DATA_FILES['core_actuals']
    df = pd.read_excel(file_path, header=6)
    return df
 
def load_core_forecast():
    file_path = DATA_FILES['core_forecast']
    df = pd.read_excel(file_path, header=6)
    return df

def load_full_map():
    file_path = DATA_FILES['full_map']
    df = pd.read_excel(file_path, header=0)
    df.columns = ['P_Code', 'Molecule_Code', 'Primary', 'Secondary', 'Market_Name', 'Scientific_Name', 'REGN_Number', 'Program', 'Sub_Program'] + list(df.columns[9:])
    df = df[1:]  # skip blank row
    return df

def load_bsb_data():
    file_path = DATA_FILES['bsb_data']
    df = pd.read_excel(file_path, header=1)

    # rename cols
    df = df.rename(columns={'Project Code - Desc': 'Project_Code_Desc',
                            'GL Account': 'GL_Account',
                            'FY08': 'Budget'})
    # get p-code
    df['P_Code'] = df['Project_Code_Desc'].apply(get_pcode)
    # get study ID/number
    df['Study_ID'] = df['Project_Code_Desc'].apply(get_studyid)
    # get accounts
    # Get full account string (e.g., "A80070 - CRO Services")
    df['Account_Clean'] = df['GL_Account'].apply(clean_account)
    # Extract just the account code (e.g., "A80070") for matching
    df['Account_Code'] = df['Account_Clean'].apply(extract_account_code)
    # cleanup
    df['Budget'] = pd.to_numeric(df['Budget'], errors='coerce').fillna(0)
    df_clean = df[['P_Code', 'Study_ID', 'Account_Code', 'Account_Clean', 'GL_Account', 'Budget', 'Project_Code_Desc']].copy()
    df_clean = df_clean[df_clean['Budget'] > 0]
    return df_clean

def load_po_data():
    file_path = DATA_FILES['po_data']
    df = pd.read_excel(file_path, header=0)

    # add P to get PXXX
    def get_pcode_po(project_str):
        if pd.isna(project_str):
            return None
        project_str = str(project_str).strip()
        if len(project_str) >= 3 and project_str[:3].isdigit(): # add P before digits
            return f"P{project_str[:3]}"
        return None
    df['P_Code'] = df['Project Code'].apply(get_pcode_po)

    # add P to get full PXXX-YYYY-ZZZZ
    def add_p_prefix(project_str):
        if pd.isna(project_str):
            return None
        project_str = str(project_str).strip()
        if len(project_str) >= 3 and project_str[:3].isdigit():
            return f"P{project_str}"
        return None
    df['Project_Code_Full'] = df['Project Code'].apply(add_p_prefix)

    # using Project_Code_Full for matching instead of Study_ID due to formatting differences in the PO project codes
    df['Study_ID'] = None

    # get clean account name
    def add_a_prefix(account_str):
        if pd.isna(account_str):
            return None
        account_str = str(account_str).strip()

        # if doesnt start with A, add it...
        if not account_str.startswith('A'):
            if '-' in account_str:
                code, desc = account_str.split('-', 1) # get just account code
                desc = desc.strip()
                if len(desc) > 50: # limit description length
                    desc = desc[:47] + '...'
                return f"A{code.strip()} - {desc}"
            else:
                return f"A{account_str}"
        # if has A prefix... clean formatting still
        if '-' in account_str:
            parts = account_str.split('-', 1)
            code = parts[0].strip()
            desc = parts[1].strip()
            # Limit description length to match clean_account()
            if len(desc) > 50:
                desc = desc[:47] + '...'
            return f"{code} - {desc}"

        return account_str
    df['Account_Clean'] = df['GL Acct Code-Desc'].apply(add_a_prefix)

    # clean numeric columns
    df['Commitment'] = pd.to_numeric(df['PO Line Open Commitment Entered USD'], errors='coerce').fillna(0)
    df['Billed'] = pd.to_numeric(df['PO Line Amount Billed Entered USD'], errors='coerce').fillna(0)
    df['Total_Line'] = pd.to_numeric(df['PO Line Amount Entered USD'], errors='coerce').fillna(0)

    # remove unecessary cols
    df_clean = df[['P_Code', 'Project_Code_Full', 'Account_Clean', 'Commitment', 'Billed', 'Total_Line', 'PO Creation Date', 'Project Code']].copy()
    df_clean = df_clean[df_clean['Commitment'] > 0]  # Only keep POs with open commitments
    df_clean = df_clean[df_clean['P_Code'].notna()]  # Only keep rows where we successfully extracted P_Code
    return df_clean

def load_sdr():
    file_path = DATA_FILES['study_daily_report']
    df = pd.read_excel(file_path, sheet_name='REGN Lead Study Daily Report', header=3)

    # get study ID
    df['Study_Number_Short'] = df['Study Number'].apply(get_studyid_sdr)
    df_clean = df[df['Study_Number_Short'].notna()].copy() # only keep rows with a study name

    # define important cols
    milestone_cols = ['FPFV', 'FPFD', 'LPFD', 'LPLV', 'DBL']
    enrollment_cols = ['# Enrollment (Planned)', '# Enrollment (Actual)']
    site_cols = ['# Sites (Planned)', '# Sites Activated']

    # cols to keep
    cols_to_keep = ['Study Number', 'Study_Number_Short', 'CDU', 'Therapeutic Area  ', 'Indication', 'Phase']
    for col in milestone_cols:
        if col in df_clean.columns:
            cols_to_keep.append(col)
    for col in enrollment_cols + site_cols:
        if col in df_clean.columns:
            cols_to_keep.append(col)
            
    available_cols = [col for col in cols_to_keep if col in df_clean.columns]
    df_clean = df_clean[available_cols].copy()

    # cleanup/rename
    df_clean = df_clean.rename(columns={'Therapeutic Area  ': 'Therapeutic_Area'})
    for col in milestone_cols:
        if col in df_clean.columns:
            df_clean[col] = pd.to_datetime(df_clean[col], errors='coerce')
    for col in enrollment_cols + site_cols:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
    df_clean = df_clean.drop_duplicates(subset=['Study_Number_Short'])

    # calculate milestone coverage
    if 'FPFV' in df_clean.columns:
        milestone_coverage = {}
        for col in milestone_cols:
            if col in df_clean.columns:
                milestone_coverage[col] = df_clean[col].notna().sum()

    return df_clean

# get program name from FULL_MAP based on p-code
def get_program(pcode, map_df):
    if pd.isna(pcode):
        return None
    match = map_df[map_df['P_Code'] == pcode]
    
    if len(match) == 0:
        return f"[{pcode}] - Unknown Program"
    row = match.iloc[0]

    # naming priority: Primary > Secondary > REGN_Number
    if pd.notna(row['Primary']) and row['Primary'] != '':
        return row['Primary']
    elif pd.notna(row['Secondary']) and row['Secondary'] != '':
        return row['Secondary']
    elif pd.notna(row['REGN_Number']) and row['REGN_Number'] != '':
        return row['REGN_Number']

    return f"[{pcode}] - Unmapped Program"

# check if the project code is actually a study (vs Gen...)
def is_actual_study(study_id):
    if pd.isna(study_id):
        return False
    study_id_str = str(study_id).strip()

    # regex: digits-dash-digits
    match = re.match(r'^\d{4}-\d{3,4}$', study_id_str)
    return match is not None


def get_display_name(study_id, study_daily_df, pcode=None, map_df=None):
    if pd.isna(study_id) or study_daily_df.empty:
        return study_id
    study_id_str = str(study_id).strip()

    # try YYYY-ZZZZ
    match = re.match(r'(\d{4})-(\d{3,4})$', study_id_str)
    if not match:
        return study_id_str  # otherwise just put whatever you find

    first_part = match.group(1)  # YYYY (e.g., "3931")
    last_part = match.group(2)   # ZZZZ or ZZZ (e.g., "2036")

    # ATTEMPT 1: Match full Study_ID (YYYY-ZZZZ) anywhere in Study Number
    for idx, row in study_daily_df.iterrows():
        study_num = str(row['Study Number'])
        if study_id_str in study_num:
            return study_num

    # ATTEMPT 2: Match R#### (from REGN_Number) with beginning of Study Number AND last digits
    # Do this EARLY when P_Code is available to prevent cross-program contamination
    if pcode and map_df is not None:
        regn_match = map_df[map_df['P_Code'] == pcode]
        if not regn_match.empty:
            regn_full = str(regn_match.iloc[0]['REGN_Number'])

            # Extract R#### format from various patterns
            # REGN3 -> R3, REGN20934 -> R20934, ALN-APOC3 -> ALN-APOC3, ADI-002 -> ADI-002
            if 'REGN' in regn_full:
                regn_code = regn_full.replace('REGN', 'R')
            else:
                regn_code = regn_full  # Keep as-is for ALN-, ADI-, etc.

            # Match REGN code at beginning of Study Number AND last digits match
            for idx, row in study_daily_df.iterrows():
                study_num = str(row['Study Number'])
                if study_num.startswith(regn_code) and study_num.endswith(last_part):
                    return study_num

            # If REGN# was available but didn't match, DON'T fall back to loose matching
            # This prevents cross-program contamination (e.g., P715/R7508 matching P672/R3767)
            
            return study_id_str

    # ATTEMPT 3: Match YYYY with last chunk after final "-" (ONLY if no P_Code/REGN#)
    for idx, row in study_daily_df.iterrows():
        study_num = str(row['Study Number'])
        if '-' in study_num:
            last_chunk = study_num.split('-')[-1]
            if last_chunk == first_part:
                return study_num

    # ATTEMPT 4: Match ZZZZ/ZZZ with last chunk after final "-" (ONLY if no P_Code/REGN#)
    for idx, row in study_daily_df.iterrows():
        study_num = str(row['Study Number'])
        if '-' in study_num:
            last_chunk = study_num.split('-')[-1]
            if last_chunk == last_part:
                return study_num

    # No match found - return original Study_ID
    return study_id_str


def get_study_phase(study_id, study_daily_df, pcode=None, map_df=None):
    if pd.isna(study_id) or study_daily_df.empty:
        return 'Other'

    study_id_str = str(study_id).strip()

    # Only process YYYY-ZZZZ format
    match = re.match(r'(\d{4})-(\d{3,4})$', study_id_str)
    if not match:
        return 'Other'

    first_part = match.group(1)  # YYYY
    last_part = match.group(2)   # ZZZZ/ZZZ

    matched_row = None

    # ATTEMPT 1: Match full Study_ID (YYYY-ZZZZ) anywhere in Study Number
    for idx, row in study_daily_df.iterrows():
        if study_id_str in str(row['Study Number']):
            matched_row = row
            break

    # ATTEMPT 2: Match R#### (from REGN_Number) with beginning AND last digits
    # Do this EARLY when P_Code is available to prevent cross-program contamination
    regn_available = False
    if matched_row is None and pcode and map_df is not None:
        regn_match = map_df[map_df['P_Code'] == pcode]
        if not regn_match.empty:
            regn_available = True
            regn_full = str(regn_match.iloc[0]['REGN_Number'])
            regn_code = regn_full.replace('REGN', 'R') if 'REGN' in regn_full else regn_full

            for idx, row in study_daily_df.iterrows():
                study_num = str(row['Study Number'])
                if study_num.startswith(regn_code) and study_num.endswith(last_part):
                    matched_row = row
                    break

    # If REGN# was available but didn't match, DON'T fall back to loose matching
    if regn_available and matched_row is None:
        return 'Other'

    # ATTEMPT 3: Match YYYY with last chunk after final "-" (ONLY if no P_Code/REGN#)
    if matched_row is None:
        for idx, row in study_daily_df.iterrows():
            study_num = str(row['Study Number'])
            if '-' in study_num and study_num.split('-')[-1] == first_part:
                matched_row = row
                break

    # ATTEMPT 4: Match ZZZZ/ZZZ with last chunk after final "-" (ONLY if no P_Code/REGN#)
    if matched_row is None:
        for idx, row in study_daily_df.iterrows():
            study_num = str(row['Study Number'])
            if '-' in study_num and study_num.split('-')[-1] == last_part:
                matched_row = row
                break

    # Extract and normalize phase if match found
    if matched_row is not None:
        phase = matched_row['Phase']
        if pd.notna(phase):
            if 'Phase 1' in phase or phase == 'Phase 1b':
                return 'Phase 1'
            elif 'Phase 2' in phase or phase in ['Phase 2a', 'Phase 2b']:
                return 'Phase 2'
            elif 'Phase 3' in phase or phase == 'Phase 3b':
                return 'Phase 3'
            elif 'Phase 4' in phase or 'PostMarketing' in phase:
                return 'Phase 4'
            elif phase == '-':
                return 'Other'
            else:
                return phase
    # no match
    return 'Other'


def process_dataframe(df, map_df, df_name="DataFrame"):
    # cleanup
    df['Project_Hyperion'] = df['Project_Hyperion'].astype(str).str.strip()
    df['Account_Hyperion'] = df['Account_Hyperion'].astype(str).str.strip()
    # add cols
    df['P_Code'] = df['Project_Hyperion'].apply(get_pcode)
    df['Study_ID'] = df['Project_Hyperion'].apply(get_studyid)
    df['Account_Clean'] = df['Account_Hyperion'].apply(clean_account)
    df['Program_Name'] = df['P_Code'].apply(lambda x: get_program(x, map_df)) # get from FULL_MAP

    # match Project_Code_Full with PO data (P570OD00C3831-..YYYY-ZZZZ -> P570OD00C3831)
    df['Project_Code_Full'] = df['Project_Hyperion'].apply(lambda x: x.split(' ')[0] if pd.notna(x) and ' ' in str(x) else x)
    # get financial columns (FY## Q# format)
    quarter_cols = [col for col in df.columns if re.match(r'FY\d{2} Q\d', col)]

    # cleanup
    for col in quarter_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df, quarter_cols


def merge_actuals_with_forecast(core_df, forecast_df, quarter_cols, forecast_quarter_cols):

    # SHARED QTRS
    shared_forecast_quarters = [q for q in forecast_quarter_cols if q in quarter_cols]
    # add any shared qtrs to actuals
    if len(shared_forecast_quarters) > 0:
        shared_cols_to_merge = ['Project_Hyperion', 'Account_Hyperion'] + shared_forecast_quarters
        forecast_shared = forecast_df[shared_cols_to_merge].copy()
        temp_merged = core_df.merge(forecast_shared,
                                    on=['Project_Hyperion', 'Account_Hyperion'],
                                    how='left',
                                    suffixes=('', '_forecast'))
        # cleanup the shared qtrs
        for quarter in shared_forecast_quarters:
            forecast_col = f"{quarter}_forecast"
            temp_merged[quarter] = temp_merged[forecast_col].fillna(temp_merged[quarter])
            temp_merged = temp_merged.drop(columns=[forecast_col]) # drop the originals to avoid duplicates

        core_df = temp_merged


    # UNIQUE QTRS
    unique_forecast_quarters = [q for q in forecast_quarter_cols if q not in quarter_cols]
    columns_to_merge = ['Project_Hyperion', 'Account_Hyperion'] + unique_forecast_quarters
    forecast_subset = forecast_df[columns_to_merge].copy()
    
    # append unique forecast qtrs with actuals
    merged_df = core_df.merge(
        forecast_subset,
        on=['Project_Hyperion', 'Account_Hyperion'],
        how='left') # keep ALL actuals rows, add forecast columns where matches exist
    # cleanup
    for col in unique_forecast_quarters:
        merged_df[col] = merged_df[col].fillna(0)
        
    return merged_df


def load_all_data():
    # load-in all files
    core_df = load_core_actuals()
    forecast_df = load_core_forecast()
    map_df = load_full_map()
    bsb_df = load_bsb_data()
    po_df = load_po_data()
    study_daily_df = load_sdr()
    
    # process dfs
    core_df, quarter_cols = process_dataframe(core_df, map_df, "CORE_Actuals")
    forecast_df, forecast_quarter_cols = process_dataframe(forecast_df, map_df, "CORE_Forecast")
    # merge actuals + forecast
    core_df = merge_actuals_with_forecast(core_df, forecast_df, quarter_cols, forecast_quarter_cols)

    return {'core_df': core_df,
            'forecast_df': forecast_df,
            'map_df': map_df,
            'bsb_df': bsb_df,
            'po_df': po_df,
            'study_daily_df': study_daily_df,
            'quarter_cols': quarter_cols,
            'forecast_quarter_cols': forecast_quarter_cols}

if __name__ == "__main__":
    try:
        data = load_all_data()
        print("\n[OK] Data loaded successfully!")
        print(f"   Actuals: {data['core_df'].shape[0]} rows")
        print(f"   Forecast: {data['forecast_df'].shape[0]} rows")
        print(f"   Programs: {data['map_df'].shape[0]} programs")
        print(f"   BSB Budgets: {data['bsb_df'].shape[0]} line items")
        print(f"   Total Budget: ${data['bsb_df']['Budget'].sum():,.0f}")
        print(f"   PO Commitments: {data['po_df'].shape[0]} line items")
        print(f"   Total Open POs: ${data['po_df']['Commitment'].sum():,.0f}")
        print(f"   Quarter columns: {len(data['quarter_cols'])}")
    except Exception as e:
        print(f"\n[ERROR] Error loading data: {e}")
