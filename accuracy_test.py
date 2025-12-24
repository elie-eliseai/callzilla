"""
Accuracy Testing Framework for EliseAI Detection System
========================================================

Measures accuracy at each stage of the pipeline:
1. Phone Scraping - Do we get the correct phone number?
2. Website Fetch - Can we successfully render property websites?
3. Call Placement - Do calls connect?
4. Call Tree Navigation - Do we press the right buttons?
5. EliseAI Detection - Do we correctly identify EliseAI?

Usage:
    # Test phone scraping only
    python accuracy_test.py --stage scraping --dataset test_dataset.csv
    
    # Analyze existing call results
    python accuracy_test.py --stage calls --results call_results.csv
    
    # Full report
    python accuracy_test.py --full-report
"""

import os
import sys
import csv
import json
import argparse
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

# Add scraper to path
sys.path.insert(0, str(Path(__file__).parent))

from scraper import PropertyPhoneScraper
from scraper.scraper_config import Config


@dataclass
class StageMetrics:
    """Metrics for a single pipeline stage."""
    stage_name: str
    total_tested: int
    successes: int
    failures: int
    accuracy: float
    failure_breakdown: dict
    examples: list


@dataclass 
class AccuracyReport:
    """Full accuracy report across all stages."""
    timestamp: str
    dataset_file: str
    stages: list
    overall_accuracy: float
    notes: str = ""


def normalize_phone(phone: str) -> str:
    """Normalize phone number to digits only for comparison."""
    if not phone:
        return ""
    return ''.join(c for c in str(phone) if c.isdigit())[-10:]  # Last 10 digits


def phones_match(phone1: str, phone2: str) -> bool:
    """Check if two phone numbers match (fuzzy)."""
    n1 = normalize_phone(phone1)
    n2 = normalize_phone(phone2)
    if not n1 or not n2:
        return False
    return n1 == n2


async def test_phone_scraping(dataset_path: str, sources: list = None) -> StageMetrics:
    """
    Test phone scraping accuracy against ground truth.
    
    Args:
        dataset_path: Path to CSV with columns: property_name, location, expected_phone
        sources: Which sources to test (default: all)
    """
    sources = sources or ['google', 'apartments.com', 'property_website']
    
    config = Config.from_env()
    scraper = PropertyPhoneScraper(config)
    
    results = {
        'correct': [],
        'wrong_phone': [],
        'not_found': [],
        'error': []
    }
    
    # Load dataset
    with open(dataset_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if not r.get('property_name', '').startswith('#')]
    
    print(f"\n📊 Testing phone scraping on {len(rows)} properties...")
    print(f"   Sources: {sources}")
    
    for i, row in enumerate(rows, 1):
        name = row.get('property_name', '').strip()
        location = row.get('location', '').strip()
        expected = row.get('expected_phone', '').strip()
        
        if not name or not location:
            continue
            
        print(f"   [{i}/{len(rows)}] {name}...", end=' ', flush=True)
        
        try:
            # Scrape all sources
            scraped_phones = {}
            for source in sources:
                if source == 'google':
                    result = await scraper.scrape_google(name, location)
                elif source == 'apartments.com':
                    result = await scraper.scrape_apartments(name, location)
                elif source == 'property_website':
                    result = await scraper.scrape_property_website(name, location)
                else:
                    continue
                
                if result.phone:
                    scraped_phones[source] = result.phone
            
            # Check if any scraped phone matches expected
            any_match = False
            for source, phone in scraped_phones.items():
                if phones_match(phone, expected):
                    any_match = True
                    break
            
            if any_match:
                results['correct'].append({
                    'name': name,
                    'expected': expected,
                    'scraped': scraped_phones
                })
                print("✅")
            elif scraped_phones:
                results['wrong_phone'].append({
                    'name': name,
                    'expected': expected,
                    'scraped': scraped_phones
                })
                print(f"❌ (got {list(scraped_phones.values())[0]})")
            else:
                results['not_found'].append({
                    'name': name,
                    'expected': expected,
                    'scraped': {}
                })
                print("❓ (not found)")
                
        except Exception as e:
            results['error'].append({
                'name': name,
                'error': str(e)
            })
            print(f"⚠️ ({str(e)[:30]})")
    
    # Calculate metrics
    total = len(rows)
    successes = len(results['correct'])
    accuracy = (successes / total * 100) if total > 0 else 0
    
    return StageMetrics(
        stage_name="Phone Scraping",
        total_tested=total,
        successes=successes,
        failures=total - successes,
        accuracy=accuracy,
        failure_breakdown={
            'wrong_phone': len(results['wrong_phone']),
            'not_found': len(results['not_found']),
            'error': len(results['error'])
        },
        examples=results['wrong_phone'][:5] + results['not_found'][:5]
    )


def test_call_results(results_path: str) -> StageMetrics:
    """
    Analyze existing call results for accuracy metrics.
    
    Expects CSV with columns: property_name, call_status, call_result, 
                              tree_detected, button_pressed, elise_detected
    """
    results = {
        'connected': 0,
        'failed': 0,
        'busy': 0,
        'no_answer': 0
    }
    
    tree_nav = {
        'correct': 0,
        'wrong': 0,
        'unknown': 0
    }
    
    elise = {
        'correct': 0,
        'wrong': 0,
        'unknown': 0
    }
    
    with open(results_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"\n📊 Analyzing {len(rows)} call results...")
    
    for row in rows:
        status = row.get('call_status', '').lower()
        
        # Call connection
        if status == 'completed':
            results['connected'] += 1
        elif status == 'busy':
            results['busy'] += 1
        elif status == 'no-answer':
            results['no_answer'] += 1
        else:
            results['failed'] += 1
        
        # Tree navigation (if we have ground truth)
        if row.get('tree_button_correct'):
            if row['tree_button_correct'].lower() == 'yes':
                tree_nav['correct'] += 1
            elif row['tree_button_correct'].lower() == 'no':
                tree_nav['wrong'] += 1
            else:
                tree_nav['unknown'] += 1
        
        # EliseAI detection (if we have ground truth)
        if row.get('elise_correct'):
            if row['elise_correct'].lower() == 'yes':
                elise['correct'] += 1
            elif row['elise_correct'].lower() == 'no':
                elise['wrong'] += 1
            else:
                elise['unknown'] += 1
    
    total = len(rows)
    call_success = results['connected']
    accuracy = (call_success / total * 100) if total > 0 else 0
    
    return StageMetrics(
        stage_name="Call Placement",
        total_tested=total,
        successes=call_success,
        failures=total - call_success,
        accuracy=accuracy,
        failure_breakdown={
            'failed': results['failed'],
            'busy': results['busy'],
            'no_answer': results['no_answer']
        },
        examples=[]
    )


def analyze_call_logs(log_dir: str = ".") -> dict:
    """
    Analyze call log files to extract metrics.
    """
    metrics = {
        'total_calls': 0,
        'completed': 0,
        'voicemail_reached': 0,
        'human_answered': 0,
        'call_tree_navigated': 0,
        'elise_detected': 0,
        'errors': 0
    }
    
    log_files = Path(log_dir).glob("call_log_*.txt")
    
    for log_file in log_files:
        content = log_file.read_text()
        
        # Count outcomes
        metrics['total_calls'] += content.count('📞 Calling:')
        metrics['completed'] += content.count('✅ VOICEMAIL')
        metrics['voicemail_reached'] += content.count('voicemail')
        metrics['human_answered'] += content.count('HUMAN')
        metrics['call_tree_navigated'] += content.count('Call tree navigation')
        metrics['elise_detected'] += content.lower().count('elise')
        metrics['errors'] += content.count('❌')
    
    return metrics


def print_report(metrics: list, report_name: str = "Accuracy Report"):
    """Print formatted accuracy report."""
    print("\n" + "=" * 70)
    print(f"   {report_name}")
    print("=" * 70)
    print(f"   Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    overall_accuracy = []
    
    for m in metrics:
        print(f"\n{'─' * 70}")
        print(f"📊 {m.stage_name}")
        print(f"{'─' * 70}")
        print(f"   Total tested:  {m.total_tested}")
        print(f"   Successes:     {m.successes}")
        print(f"   Failures:      {m.failures}")
        print(f"   ✨ ACCURACY:   {m.accuracy:.1f}%")
        
        if m.failure_breakdown:
            print(f"\n   Failure breakdown:")
            for reason, count in m.failure_breakdown.items():
                pct = (count / m.total_tested * 100) if m.total_tested > 0 else 0
                print(f"     • {reason}: {count} ({pct:.1f}%)")
        
        if m.examples:
            print(f"\n   Example failures (up to 5):")
            for ex in m.examples[:5]:
                print(f"     • {ex.get('name', 'Unknown')}")
                if ex.get('expected'):
                    print(f"       Expected: {ex['expected']}")
                if ex.get('scraped'):
                    print(f"       Got: {ex['scraped']}")
        
        if m.total_tested > 0:
            overall_accuracy.append(m.accuracy)
    
    # Overall
    if overall_accuracy:
        combined = sum(overall_accuracy) / len(overall_accuracy)
        print(f"\n{'=' * 70}")
        print(f"   🎯 COMBINED ACCURACY: {combined:.1f}%")
        print(f"{'=' * 70}")


def save_report(metrics: list, output_path: str, dataset_path: str = ""):
    """Save report to JSON file."""
    report = AccuracyReport(
        timestamp=datetime.now().isoformat(),
        dataset_file=dataset_path,
        stages=[asdict(m) for m in metrics],
        overall_accuracy=sum(m.accuracy for m in metrics) / len(metrics) if metrics else 0
    )
    
    with open(output_path, 'w') as f:
        json.dump(asdict(report), f, indent=2)
    
    print(f"\n📁 Report saved to: {output_path}")


async def main():
    parser = argparse.ArgumentParser(description='EliseAI Detection Accuracy Testing')
    parser.add_argument('--stage', choices=['scraping', 'calls', 'all'], 
                       default='all', help='Which stage to test')
    parser.add_argument('--dataset', '-d', help='Test dataset CSV file')
    parser.add_argument('--results', '-r', help='Call results CSV to analyze')
    parser.add_argument('--sources', nargs='+', 
                       choices=['google', 'apartments.com', 'property_website'],
                       help='Sources to test for scraping')
    parser.add_argument('--output', '-o', help='Output JSON file for report')
    parser.add_argument('--full-report', action='store_true', 
                       help='Generate full report analyzing all available data')
    
    args = parser.parse_args()
    
    metrics = []
    
    # Test phone scraping
    if args.stage in ['scraping', 'all']:
        dataset = args.dataset or 'test_dataset.csv'
        if Path(dataset).exists():
            m = await test_phone_scraping(dataset, args.sources)
            metrics.append(m)
        else:
            print(f"⚠️  Dataset not found: {dataset}")
            print("   Create test_dataset.csv with columns: property_name, location, expected_phone")
    
    # Analyze call results
    if args.stage in ['calls', 'all']:
        results_file = args.results
        if not results_file:
            # Find most recent call results
            results_files = list(Path('.').glob('*_call_results*.csv'))
            if results_files:
                results_file = str(max(results_files, key=lambda p: p.stat().st_mtime))
        
        if results_file and Path(results_file).exists():
            m = test_call_results(results_file)
            metrics.append(m)
        elif args.stage == 'calls':
            print(f"⚠️  No call results file found")
    
    # Print report
    if metrics:
        print_report(metrics)
        
        # Save if requested
        output = args.output or f"accuracy_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        save_report(metrics, output, args.dataset or "")
    else:
        print("\n⚠️  No tests were run. Check your input files.")
        print("\nUsage examples:")
        print("  python accuracy_test.py --stage scraping --dataset test_dataset.csv")
        print("  python accuracy_test.py --stage calls --results call_results.csv")


if __name__ == "__main__":
    asyncio.run(main())

