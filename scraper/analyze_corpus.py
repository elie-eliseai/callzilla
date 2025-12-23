#!/usr/bin/env python3
"""
Analyze the GPT decisions corpus to find patterns in failures.
"""
import json
import csv
from pathlib import Path
from urllib.parse import urlparse

def extract_domain(url):
    """Extract domain from URL."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except:
        return ""

def load_corpus(corpus_file="gpt_decisions_corpus.jsonl"):
    """Load all GPT decisions from corpus."""
    decisions = []
    path = Path(__file__).parent / corpus_file
    if path.exists():
        with open(path) as f:
            for line in f:
                if line.strip():
                    decisions.append(json.loads(line))
    return decisions

def load_ground_truth(gt_file):
    """Load ground truth from CSV."""
    gt = {}
    path = Path(__file__).parent / gt_file
    if path.exists():
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get('property_name', '').strip()
                if name:
                    gt[name] = row.get('expected_domain', '').lower()
    return gt

def analyze(corpus_file="gpt_decisions_corpus.jsonl", gt_file="input/test_with_orgs.csv"):
    """Analyze corpus against ground truth."""
    decisions = load_corpus(corpus_file)
    ground_truth = load_ground_truth(gt_file)
    
    print(f"\n📊 GPT DECISIONS CORPUS ANALYSIS")
    print(f"=" * 60)
    print(f"Total decisions in corpus: {len(decisions)}")
    print(f"Ground truth entries: {len(ground_truth)}")
    
    correct = []
    wrong = []
    
    for d in decisions:
        prop_name = d.get("property_name", "")
        expected = ground_truth.get(prop_name, "")
        picked_url = d.get("gpt_picked_url", "")
        picked_domain = extract_domain(picked_url)
        
        if not expected:
            continue  # No ground truth for this property
        
        # Check if correct (domain match)
        is_correct = (picked_domain == expected or 
                     picked_domain == 'www.' + expected or
                     expected in picked_domain or
                     picked_domain in expected)
        
        entry = {
            "property": prop_name,
            "expected": expected,
            "picked_domain": picked_domain,
            "picked_url": picked_url,
            "candidates": d.get("candidates", []),
            "gpt_pick": d.get("gpt_pick"),
            "correct": is_correct
        }
        
        if is_correct:
            correct.append(entry)
        else:
            wrong.append(entry)
    
    print(f"\n✅ Correct: {len(correct)}")
    print(f"❌ Wrong: {len(wrong)}")
    if correct or wrong:
        print(f"📈 Accuracy: {len(correct) / (len(correct) + len(wrong)) * 100:.1f}%")
    
    if wrong:
        print(f"\n" + "-" * 60)
        print("FAILURE ANALYSIS")
        print("-" * 60)
        
        for i, w in enumerate(wrong, 1):
            print(f"\n{'='*60}")
            print(f"❌ FAILURE {i}: {w['property']}")
            print(f"   Expected: {w['expected']}")
            print(f"   GPT picked: {w['picked_domain']} (choice #{w['gpt_pick']})")
            print(f"\n   CANDIDATES GPT SAW:")
            
            correct_candidate_num = None
            for j, c in enumerate(w['candidates'], 1):
                c_domain = extract_domain(c['url'])
                is_expected = (c_domain == w['expected'] or 
                              c_domain == 'www.' + w['expected'] or
                              w['expected'] in c_domain)
                marker = " ✓ EXPECTED" if is_expected else ""
                if is_expected:
                    correct_candidate_num = j
                
                print(f"\n   {j}. {c['title']}{marker}")
                print(f"      URL: {c['url']}")
                print(f"      Snippet: {c['snippet'][:100]}...")
            
            if correct_candidate_num:
                print(f"\n   ⚠️  Correct answer was #{correct_candidate_num}, GPT picked #{w['gpt_pick']}")
            else:
                print(f"\n   ⚠️  Correct URL was NOT in candidates!")
    
    # Save detailed analysis
    output_path = Path(__file__).parent / "reports" / "corpus_analysis.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "total_decisions": len(decisions),
            "correct_count": len(correct),
            "wrong_count": len(wrong),
            "accuracy": len(correct) / (len(correct) + len(wrong)) * 100 if (correct or wrong) else 0,
            "failures": wrong
        }, f, indent=2)
    print(f"\n📁 Detailed analysis saved to: {output_path}")

if __name__ == "__main__":
    import sys
    gt_file = sys.argv[1] if len(sys.argv) > 1 else "input/test_with_orgs.csv"
    analyze(gt_file=gt_file)





