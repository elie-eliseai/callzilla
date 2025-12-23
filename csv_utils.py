"""
CSV Utilities Module - All CSV loading and phone number handling functions.

This module contains:
- Column detection functions for flexible CSV parsing
- Phone number cleaning/formatting
- Property loading with optional phone scraping
- Completed property tracking
"""

import os
import pandas as pd
from config import Config

# Import phone scraper from local scraper package
try:
    from scraper import get_phone_sync
    SCRAPER_AVAILABLE = True
except ImportError:
    SCRAPER_AVAILABLE = False
    print("⚠️  Phone scraper not available - scraper package not found")


def find_phone_column(df):
    """Find phone number column, returns None if not found"""
    for col in df.columns:
        if any(kw in col.lower() for kw in ['phone', 'number', 'tel', 'mobile']):
            return col
    # Check if second column looks like phone numbers
    if len(df.columns) > 1:
        sample = str(df.iloc[0][df.columns[1]]) if len(df) > 0 else ""
        digits = ''.join(filter(str.isdigit, sample))
        if len(digits) >= 10:
            return df.columns[1]
    return None  # Return None if no phone column found


def find_name_column(df):
    """Find property name column"""
    for col in df.columns:
        if any(kw in col.lower() for kw in ['name', 'property', 'company', 'building']):
            return col
    return df.columns[0]


def find_address_column(df):
    """Find address/location column for phone scraping"""
    for col in df.columns:
        if any(kw in col.lower() for kw in ['address', 'location', 'city', 'full_address']):
            return col
    return None


def clean_phone_number(phone):
    """Clean and format phone number to E.164 format"""
    phone = str(phone).strip()
    phone = ''.join(filter(str.isdigit, phone))
    if not phone:
        return None
    if not phone.startswith('+'):
        if len(phone) == 10:
            phone = '+1' + phone
        elif len(phone) == 11 and phone.startswith('1'):
            phone = '+' + phone
        else:
            phone = '+1' + phone
    return phone


def get_completed_properties():
    """Get set of property names that already have completed calls (exclude failed/timeout)"""
    completed = set()
    try:
        if os.path.exists(Config.RESULTS_FILE):
            results_df = pd.read_csv(Config.RESULTS_FILE)
            # Only consider truly completed calls, not failed or initiated (timeout)
            completed_calls = results_df[results_df['Status'] == 'completed']
            if len(completed_calls) > 0:
                # Get the last status for each property
                last_status = results_df.groupby('Property Name').last().reset_index()
                # Only skip if the LAST status is completed (not failed/initiated)
                truly_completed = last_status[last_status['Status'] == 'completed']
                completed = set(truly_completed['Property Name'].unique())
    except Exception as e:
        print(f"   ⚠️  Could not check completed properties: {str(e)}")
    return completed


def load_properties_from_csv(csv_path, start_from_property=None):
    """
    Load properties from CSV, skipping already completed ones and optionally starting from a specific property.
    
    If phone numbers are missing, attempts to scrape them using the phone scraper.
    Supports CSVs with just name+address columns (no phone column).
    
    Returns: List of dicts with 'name' and 'phone' keys, or None on error.
    """
    global SCRAPER_AVAILABLE
    
    try:
        df = pd.read_csv(csv_path, encoding='utf-8')
        
        if df.empty:
            raise ValueError("CSV file is empty")
        
        phone_col = find_phone_column(df)
        name_col = find_name_column(df)
        address_col = find_address_column(df)
        
        print(f"\n📋 CSV Analysis:")
        print(f"   Total rows: {len(df)}")
        print(f"   Name column: '{name_col}'")
        print(f"   Phone column: '{phone_col}'" if phone_col else "   Phone column: NOT FOUND (will scrape)")
        print(f"   Address column: '{address_col}'" if address_col else "   Address column: NOT FOUND")
        
        # Check if we need to scrape phones
        needs_scraping = phone_col is None
        if not needs_scraping and phone_col:
            # Check if any phones are actually missing
            missing_phones = df[phone_col].isna().sum() + (df[phone_col].astype(str).str.strip() == '').sum()
            if missing_phones > 0:
                needs_scraping = True
                print(f"   📞 {missing_phones} rows have missing phone numbers")
        
        if needs_scraping:
            if not SCRAPER_AVAILABLE:
                print(f"   ❌ Phone scraper not available!")
                print(f"   Install dependencies: cd ../Scraper && pip install -r requirements.txt")
                if not phone_col:
                    print(f"   Cannot proceed without phone numbers.")
                    return None
            elif not address_col:
                print(f"   ⚠️  No address column found - cannot scrape phone numbers")
                if not phone_col:
                    print(f"   Cannot proceed without phone numbers or addresses.")
                    return None
            else:
                print(f"   🔍 Will scrape missing phone numbers using Google/SerpAPI")
        
        # Don't skip any properties - process everything in the CSV
        completed = set()
        
        # Find start position if specified
        start_idx = 0
        if start_from_property:
            for idx, row in df.iterrows():
                name = str(row[name_col]).strip()
                if start_from_property.lower() in name.lower() or name.lower() in start_from_property.lower():
                    start_idx = idx
                    print(f"   🎯 Starting from property: {name} (row {idx + 2})")
                    break
        
        properties = []
        skipped = 0
        scraped = 0
        scrape_failed = 0
        started = False if start_from_property else True
        
        for idx, row in df.iterrows():
            # Skip until we reach the start property
            if start_from_property and not started:
                name = str(row[name_col]).strip()
                if start_from_property.lower() in name.lower() or name.lower() in start_from_property.lower():
                    started = True
                else:
                    continue
            
            name = str(row[name_col]).strip()
            
            # Skip empty rows
            if not name or name.lower() == 'nan':
                continue
            
            # Get phone number
            phone = None
            if phone_col:
                raw_phone = row[phone_col]
                if pd.notna(raw_phone) and str(raw_phone).strip():
                    phone = clean_phone_number(raw_phone)
            
            # If no phone, scrape from ALL sources and create separate entries
            if not phone and SCRAPER_AVAILABLE and address_col:
                address = str(row[address_col]).strip() if pd.notna(row[address_col]) else ""
                if address and address.lower() != 'nan':
                    print(f"   🔍 Scraping phones for: {name} ({address})")
                    
                    # Scrape from all sources
                    source_configs = [
                        ("Google", ["google"], "🔎"),
                        ("Apartments.com", ["apartments.com"], "🏠"),
                        ("Website", ["property_website"], "🌐")
                    ]
                    
                    for suffix, sources_list, icon in source_configs:
                        entry_name = f"{name} {suffix}"
                        if entry_name in completed:
                            skipped += 1
                            continue
                        
                        print(f"      {icon} {suffix}...", end=" ", flush=True)
                        try:
                            phone_result = get_phone_sync(name, address, sources=sources_list)
                            if phone_result:
                                print(f"✅ {phone_result}")
                                properties.append({'name': entry_name, 'phone': clean_phone_number(phone_result)})
                                scraped += 1
                            else:
                                print(f"❌ Not found")
                                scrape_failed += 1
                        except Exception as e:
                            print(f"❌ {str(e)[:40]}")
                            scrape_failed += 1
                    
                    continue  # Already added entries above
            
            if phone and name:
                # Skip if already completed
                if name in completed:
                    skipped += 1
                    continue
                properties.append({'name': name, 'phone': phone})
            else:
                if name and not (SCRAPER_AVAILABLE and address_col):
                    print(f"   ⚠️  Skipping row {idx + 2} ({name}): no phone number")
        
        if skipped > 0:
            print(f"   ⏭️  Skipped {skipped} already completed properties")
        if scraped > 0:
            print(f"   📞 Scraped {scraped} phone numbers successfully")
        if scrape_failed > 0:
            print(f"   ⚠️  Failed to scrape {scrape_failed} phone numbers")
        print(f"✅ Loaded {len(properties)} properties to process\n")
        return properties
        
    except Exception as e:
        print(f"❌ Error loading CSV: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def save_scraped_phones(properties, output_file="scraped_phones.csv"):
    """
    Save scraped phone numbers to a CSV file for review.
    
    Args:
        properties: List of dicts with 'name' and 'phone' keys
        output_file: Output CSV path
    """
    import csv
    
    print(f"\n📋 Saving {len(properties)} properties to: {output_file}")
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Property Name', 'Phone Number', 'Source'])
        writer.writeheader()
        for prop in properties:
            name = prop['name']
            # Extract source from name if present
            source = "manual"
            if name.endswith(" Google"):
                source = "google"
            elif name.endswith(" Apartments.com"):
                source = "apartments.com"
            elif name.endswith(" Website"):
                source = "property_website"
            
            writer.writerow({
                'Property Name': name,
                'Phone Number': prop['phone'],
                'Source': source
            })
    
    print(f"✅ Saved! Review the file, then run with --call-only:")
    print(f"   python3 simple_production_caller.py {output_file} --call-only")

