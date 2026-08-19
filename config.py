"""
APOFIS Dashboard - Configuration Module

This module manages all configuration settings for the APOFIS dashboard.
It reads from environment variables (.env file) to allow easy customization
without modifying code.

For IT: Modify .env file to change paths, server settings, etc.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directory (where this config.py file lives)
BASE_DIR = Path(__file__).parent.resolve()

# Data directory - configurable via .env file
DATA_DIR = Path(os.getenv('DATA_DIRECTORY', BASE_DIR / 'DATA'))

# File paths - easily updatable by IT
DATA_FILES = {
    'core_actuals': DATA_DIR / 'CORE_Actuals.xlsx',
    'core_forecast': DATA_DIR / 'CORE_Forecast.xlsx',
    'full_map': DATA_DIR / 'FULL_MAP.xlsx',
    'bsb_data': DATA_DIR / 'BSB_Data.xlsx',
    'po_data': DATA_DIR / 'PO_Data.xlsx',
    'study_daily_report': DATA_DIR / 'Study Daily Report.xlsx'}

# Server configuration
SERVER_CONFIG = {
    'host': os.getenv('SERVER_HOST', '127.0.0.1'),
    'port': int(os.getenv('SERVER_PORT', 8888)),
    'debug': os.getenv('DEBUG_MODE', 'False').lower() == 'true'}

# Logging configuration
LOG_CONFIG = {
    'level': os.getenv('LOG_LEVEL', 'INFO'),
    'file': os.getenv('LOG_FILE', 'apofis.log'),
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'date_format': '%Y-%m-%d %H:%M:%S'}

# Color schemes for dashboard
COLORS_DARK = {
    'regn-blue': '#065baa',
    'surface-0': '#0d1117',
    'surface-2': '#21262d',
    'line-soft': 'rgba(48, 54, 61, 0.8)',
    'ink-strong': '#e6edf3',
    'ink-body': '#cdd9e5',
    'ink-soft': '#8b949e',
    'brand-cyan': '#00e5ff',
    'brand-green': '#00ff9c',
    'shadow-soft': '0 18px 48px rgba(0, 0, 0, 0.5)'}

COLORS_LIGHT = {
    'regn-blue': '#065baa',
    'surface-0': '#ffffff',
    'surface-2': '#f6f8fa',
    'line-soft': 'rgba(208, 215, 222, 0.8)',
    'ink-strong': '#1f2328',
    'ink-body': '#424a53',  # Darker gray for better tab contrast
    'ink-soft': '#6e7781',
    'brand-cyan': '#0969da',
    'brand-green': '#1a7f37',
    'shadow-soft': '0 18px 48px rgba(0, 0, 0, 0.1)'}

# Default to dark theme for backward compatibility
COLORS = COLORS_DARK


def get_colors(theme='dark'):
    if theme == 'light':
        return COLORS_LIGHT
    return COLORS_DARK

# account lists
PROGRAM_FINANCE_ACCOUNTS = [
    'A80020',  # Investigator Grants
    'A80022',  # Contract Lab
    'A80023',  # Contract Lab Pass Thru Fees
    'A80028',  # Clinical - Data Imaging
    'A80031',  # Drug Filling
    'A80032',  # Drug Packaging & Label
    'A80037',  # Clinical Drug Supply-Combo Study
    'A80038',  # Clinical Drug Supply-Single Inv
    'A80039',  # Clinical Drug Supply-Clinical Mfg
    'A80060',  # Combo Prod Dev
    'A80070',  # CRO - Services
    'A80075',  # CRO - Pass Thrus
    'A80076',  # Clinical - IVRS
    'A80077',  # Clinical - FSP Allocations
    'A81000',  # HEOR Costs
    'A81020',  # Clinical Other Medical Costs
    'A81999',  # P-CLINICAL EXPENSES - PLAN
    'A80008',  # Clinical – Enterprise Allocations
    'A80072',  # CRO Fsp Costs
    'A80027',  # Clinical Services
    'P-A81999',  # ALL OTHER CLINICAL EXPENSES
    'P1-A81999',  # ALL CLINICAL TRIAL INSURANCE
    'P2-A81999',  # ALL DRUG LOGISTICS
    'P3-A81999',  # ALL CLINICAL ASSAY
    'A80065']  # Clinical Comparators

FLAT_FORECAST_ACCOUNTS = [
    'A80020',]  # Investigator Grants - typically paid out evenly

def is_program_finance_account(account_clean):
    if not account_clean or str(account_clean) == 'nan':
        return False
    account_code = str(account_clean).split(' - ')[0].strip() # get just A0000 part
    return account_code in PROGRAM_FINANCE_ACCOUNTS


def extract_account_code(account_str): # get "A80000" only
    if not account_str or str(account_str) == 'nan':
        return None
    account_str = str(account_str).strip()

    # try A00000 or P0-A00000 pattern
    import re
    match = re.search(r'([AP]\d{5}|P\d-[AP]\d{5})', account_str)
    if match:
        return match.group(1)
    # if not, take code before the dash
    for separator in ['-', ' ']:
        if separator in account_str:
            return account_str.split(separator)[0].strip()
    return account_str

def is_flat_forecast_account(account_clean):
    if not account_clean or str(account_clean) == 'nan':
        return False
    # Extract just the account code
    account_code = extract_account_code(account_clean)
    return account_code in FLAT_FORECAST_ACCOUNTS


# validate configuration on start
def validate_config():
    issues = []
    # check if DATA directory exists
    if not DATA_DIR.exists():
        issues.append(f"DATA directory not found: {DATA_DIR}")
    # check if data files exist
    for file_key, file_path in DATA_FILES.items():
        if not file_path.exists():
            issues.append(f"Data file not found: {file_path}")
    return issues


if __name__ == "__main__":
    print("="*60)
    print("APOFIS Configuration")
    print("="*60)
    print(f"Base Directory: {BASE_DIR}")
    print(f"Data Directory: {DATA_DIR}")
    print(f"Server: {SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}")
    print(f"Debug Mode: {SERVER_CONFIG['debug']}")
    print(f"Log Level: {LOG_CONFIG['level']}")
    print(f"Log File: {LOG_CONFIG['file']}")
    print("="*60)

    issues = validate_config()
    if issues:
        print("\nConfiguration Issues Found:")
        for issue in issues:
            print(f"  ❌ {issue}")
    else:
        print("\n✅ Configuration validated successfully!")
