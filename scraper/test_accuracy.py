"""
Accuracy Testing Script for Property Website Scraper
=====================================================

Compares scraper results against ground truth and generates accuracy report.

Usage:
    python test_accuracy.py --ground-truth test_ground_truth.csv --results results_XXXX.csv
    
Or run scraper and compare in one go:
    python test_accuracy.py --ground-truth test_ground_truth.csv --run-scraper
"""

import csv
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def extract_domain(url: str) -> str:
    """Extract clean domain from URL."""
    if not url:
        return ""
    domain = url.lower()
    domain = domain.replace('https://', '').replace('http://', '')
    domain = domain.replace('www.', '')
    domain = domain.split('/')[0]
    return domain


def domain_match(scraped_url: str, expected_domain: str) -> bool:
    """Check if scraped URL matches expected domain."""
    scraped_domain = extract_domain(scraped_url)
    expected_clean = expected_domain.lower().replace('www.', '')
    return scraped_domain == expected_clean


def classify_error(expected_domain: str, result: dict) -> str:
    """Classify the type of error/success."""
    scraped_url = result.get('listing_url', '')
    scraped_domain = extract_domain(scraped_url)
    error = result.get('error', '')
    status = result.get('status', '')
    
    # Success (domain match)
    if domain_match(scraped_url, expected_domain):
        return "SUCCESS"
    
    # No URL found
    if not scraped_url:
        if 'Cloudflare' in str(error):
            return "CLOUDFLARE_BLOCKED"
        if error:
            return "ERROR"
        return "NOT_FOUND"
    
    # Wrong URL found
    aggregators = [
        'apartments.com', 'zillow.com', 'trulia.com', 'rent.com',
        'realtor.com', 'hotpads.com', 'zumper.com', 'apartmentlist.com',
        'redfin.com', 'yelp.com', 'facebook.com', 'rentcafe.com'
    ]
    
    if any(agg in scraped_domain for agg in aggregators):
        return "PICKED_AGGREGATOR"
    
    return "WRONG_WEBSITE"


def load_ground_truth(filepath: str) -> dict:
    """Load ground truth CSV into dict keyed by property_name."""
    truth = {}
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('property_name', '').strip()
            if name:
                truth[name] = {
                    'location': row.get('location', ''),
                    'expected_domain': row.get('expected_domain', '')
                }
    return truth


def load_results(filepath: str) -> list:
    """Load scraper results CSV."""
    results = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('source') == 'property_website':
                results.append(row)
    return results


def parse_candidates(candidates_str: str) -> list:
    """Parse candidates column from CSV (stored as string repr of list)."""
    if not candidates_str:
        return []
    # Handle both "['a', 'b']" format and "a,b" format
    candidates_str = candidates_str.strip()
    if candidates_str.startswith('['):
        try:
            import ast
            return ast.literal_eval(candidates_str)
        except:
            pass
    # Fallback: split by comma
    return [c.strip().strip("'\"") for c in candidates_str.split(',') if c.strip()]


def domain_in_candidates(expected_domain: str, candidates: list) -> bool:
    """Check if expected domain is in the candidates list."""
    expected_clean = expected_domain.lower().replace('www.', '')
    for candidate in candidates:
        candidate_clean = candidate.lower().replace('www.', '')
        if candidate_clean == expected_clean:
            return True
    return False


def generate_report(ground_truth: dict, results: list) -> dict:
    """Generate accuracy report comparing results to ground truth."""
    
    # Build results lookup by property name
    results_by_name = {}
    for r in results:
        name = r.get('property_name', '').strip()
        if name:
            results_by_name[name] = r
    
    # Classify each property
    classifications = {
        'SUCCESS': [],
        'WRONG_WEBSITE': [],
        'PICKED_AGGREGATOR': [],
        'NOT_FOUND': [],
        'CLOUDFLARE_BLOCKED': [],
        'ERROR': [],
        'NOT_SCRAPED': []  # In ground truth but not in results
    }
    
    # Track candidate and prompt accuracy
    candidate_stats = {
        'correct_in_candidates': 0,
        'correct_not_in_candidates': 0,
        'total_with_candidates': 0
    }
    prompt_stats = {
        'picked_correct': 0,
        'picked_wrong': 0
    }
    
    for name, truth in ground_truth.items():
        expected_domain = truth['expected_domain']
        
        if name not in results_by_name:
            classifications['NOT_SCRAPED'].append({
                'name': name,
                'expected': expected_domain,
                'scraped': None,
                'candidates': [],
                'correct_in_candidates': None
            })
            continue
        
        result = results_by_name[name]
        category = classify_error(expected_domain, result)
        
        # Parse candidates
        candidates = parse_candidates(result.get('candidates', ''))
        correct_in_candidates = domain_in_candidates(expected_domain, candidates) if candidates else None
        
        # Track candidate accuracy
        if candidates:
            candidate_stats['total_with_candidates'] += 1
            if correct_in_candidates:
                candidate_stats['correct_in_candidates'] += 1
                # Track prompt accuracy (only when correct was available)
                if category == 'SUCCESS':
                    prompt_stats['picked_correct'] += 1
                else:
                    prompt_stats['picked_wrong'] += 1
            else:
                candidate_stats['correct_not_in_candidates'] += 1
        
        classifications[category].append({
            'name': name,
            'expected': expected_domain,
            'scraped': extract_domain(result.get('listing_url', '')),
            'scraped_url': result.get('listing_url', ''),
            'error': result.get('error', ''),
            'candidates': candidates,
            'correct_in_candidates': correct_in_candidates
        })
    
    return classifications, candidate_stats, prompt_stats


def print_report(classifications: dict, ground_truth: dict, candidate_stats: dict, prompt_stats: dict):
    """Print formatted accuracy report."""
    total = len(ground_truth)
    success_count = len(classifications['SUCCESS'])
    
    print("\n" + "="*60)
    print("   PROPERTY WEBSITE SCRAPER - ACCURACY REPORT")
    print("="*60)
    print(f"\nTotal properties tested: {total}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("\n" + "-"*60)
    print("RESULTS BY CATEGORY")
    print("-"*60)
    
    # Calculate percentages
    for category in ['SUCCESS', 'WRONG_WEBSITE', 'PICKED_AGGREGATOR', 'NOT_FOUND', 'CLOUDFLARE_BLOCKED', 'ERROR', 'NOT_SCRAPED']:
        count = len(classifications[category])
        pct = (count / total * 100) if total > 0 else 0
        
        emoji = {
            'SUCCESS': '✅',
            'WRONG_WEBSITE': '❌',
            'PICKED_AGGREGATOR': '🔄',
            'NOT_FOUND': '❓',
            'CLOUDFLARE_BLOCKED': '🔒',
            'ERROR': '⚠️',
            'NOT_SCRAPED': '⏭️'
        }.get(category, '')
        
        print(f"{emoji} {category:20} {count:3} ({pct:5.1f}%)")
    
    # Overall accuracy
    print("\n" + "-"*60)
    accuracy = (success_count / total * 100) if total > 0 else 0
    print(f"📊 OVERALL ACCURACY: {accuracy:.1f}%")
    print("-"*60)
    
    # Candidate and Prompt accuracy (only if we have candidate data)
    if candidate_stats['total_with_candidates'] > 0:
        print("\n" + "-"*60)
        print("DIAGNOSTIC METRICS (requires candidates column)")
        print("-"*60)
        
        cand_total = candidate_stats['total_with_candidates']
        cand_correct = candidate_stats['correct_in_candidates']
        cand_accuracy = (cand_correct / cand_total * 100) if cand_total > 0 else 0
        
        print(f"🔍 CANDIDATE ACCURACY: {cand_accuracy:.1f}%")
        print(f"   (Correct URL in candidates: {cand_correct}/{cand_total})")
        print(f"   This measures: Is search finding the right site?")
        
        prompt_total = prompt_stats['picked_correct'] + prompt_stats['picked_wrong']
        if prompt_total > 0:
            prompt_accuracy = (prompt_stats['picked_correct'] / prompt_total * 100)
            print(f"\n🤖 PROMPT ACCURACY: {prompt_accuracy:.1f}%")
            print(f"   (GPT picked correct when available: {prompt_stats['picked_correct']}/{prompt_total})")
            print(f"   This measures: Is GPT picking well?")
        else:
            print(f"\n🤖 PROMPT ACCURACY: N/A (correct never in candidates)")
        
        print("-"*60)
    
    # Show examples of failures
    for category in ['WRONG_WEBSITE', 'PICKED_AGGREGATOR', 'NOT_FOUND']:
        items = classifications[category]
        if items:
            print(f"\n{category} examples (up to 5):")
            for item in items[:5]:
                print(f"  • {item['name']}")
                print(f"    Expected: {item['expected']}")
                print(f"    Got:      {item['scraped'] or 'None'}")
                if item.get('candidates'):
                    in_cand = "✅ YES" if item.get('correct_in_candidates') else "❌ NO"
                    print(f"    Correct in candidates? {in_cand}")
                    print(f"    Candidates: {item['candidates'][:5]}")
    
    print("\n" + "="*60)
    
    return accuracy


def save_detailed_results(classifications: dict, output_path: str):
    """Save detailed results to CSV for further analysis."""
    rows = []
    for category, items in classifications.items():
        for item in items:
            rows.append({
                'property_name': item['name'],
                'expected_domain': item['expected'],
                'scraped_domain': item.get('scraped', ''),
                'scraped_url': item.get('scraped_url', ''),
                'category': category,
                'error': item.get('error', ''),
                'correct_in_candidates': item.get('correct_in_candidates', ''),
                'candidates': '|'.join(item.get('candidates', [])[:5])  # First 5, pipe-separated
            })
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['property_name', 'expected_domain', 'scraped_domain', 'scraped_url', 
                      'category', 'correct_in_candidates', 'candidates', 'error']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"\n📁 Detailed results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Test property website scraper accuracy')
    parser.add_argument('--ground-truth', '-g', required=True, help='Ground truth CSV file')
    parser.add_argument('--results', '-r', help='Results CSV from scraper')
    parser.add_argument('--run-scraper', action='store_true', help='Run scraper first, then compare')
    parser.add_argument('--output', '-o', help='Output CSV for detailed results')
    
    args = parser.parse_args()
    
    # Load ground truth
    print(f"📂 Loading ground truth from: {args.ground_truth}")
    ground_truth = load_ground_truth(args.ground_truth)
    print(f"   Found {len(ground_truth)} properties")
    
    # Run scraper if requested
    results_file = args.results
    if args.run_scraper:
        print("\n🚀 Running scraper on ground truth file...")
        results_file = f"output/results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        cmd = [
            sys.executable, '-m', 'scraper',
            '--csv', args.ground_truth,
            '--sources', 'property_website',
            '--url-only',
            '--output', results_file
        ]
        subprocess.run(cmd, check=True)
    
    if not results_file:
        print("❌ No results file specified. Use --results or --run-scraper")
        return
    
    # Load results
    print(f"\n📂 Loading results from: {results_file}")
    results = load_results(results_file)
    print(f"   Found {len(results)} property_website results")
    
    # Generate and print report
    classifications, candidate_stats, prompt_stats = generate_report(ground_truth, results)
    accuracy = print_report(classifications, ground_truth, candidate_stats, prompt_stats)
    
    # Save detailed results
    output_path = args.output or f"reports/accuracy_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    save_detailed_results(classifications, output_path)
    
    return accuracy


if __name__ == "__main__":
    main()

