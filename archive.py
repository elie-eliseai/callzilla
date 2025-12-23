"""
Archive utility for preserving call results across runs.
"""
import csv
import os
import shutil


def append_to_archive(results_file: str, archive_file: str = 'call_results_archive.csv') -> str:
    """
    Append new results to the archive file.
    
    - If archive doesn't exist, creates it from results_file
    - If archive exists, appends only new rows (by Call SID)
    - Returns a status message
    
    Args:
        results_file: Path to current results CSV
        archive_file: Path to archive CSV (default: call_results_archive.csv)
    
    Returns:
        Status message string
    """
    if not os.path.exists(results_file):
        return f"⚠️  No results file to archive: {results_file}"
    
    # If archive doesn't exist, copy current results as starting point
    if not os.path.exists(archive_file):
        shutil.copy(results_file, archive_file)
        line_count = sum(1 for _ in open(archive_file)) - 1  # Exclude header
        return f"📦 Created archive with {line_count} result(s): {archive_file}"
    
    # Read new results (skip header)
    with open(results_file, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        new_rows = list(reader)
    
    if not new_rows:
        return f"📦 No results to archive"
    
    # Get existing Call SIDs from archive
    existing_sids = set()
    with open(archive_file, 'r') as f:
        archive_reader = csv.DictReader(f)
        for row in archive_reader:
            sid = row.get('Call SID', '')
            if sid:
                existing_sids.add(sid)
    
    # Append only new rows
    added = 0
    with open(archive_file, 'a', newline='') as f:
        writer = csv.writer(f)
        for row in new_rows:
            call_sid = row[2] if len(row) > 2 else ''  # Call SID is column 3
            if call_sid and call_sid not in existing_sids:
                writer.writerow(row)
                added += 1
    
    if added > 0:
        return f"📦 Appended {added} new result(s) to archive: {archive_file}"
    else:
        return f"📦 Archive up to date: {archive_file}"


if __name__ == '__main__':
    # Can be run standalone to manually archive
    from config import Config
    print(append_to_archive(Config.RESULTS_FILE))




