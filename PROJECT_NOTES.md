# Callzilla Project Notes

Reference document for key architectural decisions and features. Read this in new sessions.

---

## Phrase-Based Call Tree Timing (Dec 2024)

### Why We Built It
- Call trees often **repeat menus** while waiting for input (e.g., "Press 1 for leasing... Press 1 for leasing...")
- Old approach: Wait for menu to end, then press button → Would press AFTER the repeat started
- New approach: Press button right after the option is first spoken

### How It Works
1. **Word-level timestamps** from Whisper (`timestamp_granularities=["word"]`)
2. **GPT returns exact KEY_PHRASE** - verbatim quote like "Press 1 for leasing"
3. **Normalization** for matching (lowercase, "one"→"1", remove punctuation)
4. **find_phrase_timing()** finds FIRST occurrence of phrase in word list
5. **Button press timing**: `skip_seconds + phrase_end_time + 1s buffer`

### Key Files
- `audio_analyzer.py`: `find_phrase_timing()`, `normalize_for_matching()`, word-level Whisper
- `gpt_analysis.py`: Updated prompt to request `KEY_PHRASE: [exact verbatim quote]`
- `simple_production_caller.py`: Uses phrase timing instead of menu duration

### Debug Output
Shows all occurrences found with timestamps and context:
```
🔍 DEBUG: Found 2 occurrence(s) of phrase:
   [1] at word index 7, ends at 5.2s  ← Uses this one
   [2] at word index 29, ends at 14.0s
```

---

## Webhook Hangup Logic (Dec 2024)

### Current Behavior
- `app.py` webhooks use `record(timeout=8, maxLength=120)`
- Hangs up after **8 seconds of silence** OR **120 seconds total**
- This prevents infinite recordings on repeating menus

### Important: No Fallbacks
- We intentionally removed word-count estimation fallbacks
- If phrase matching fails, it fails loudly so we can fix the root cause
- Bad engineering to hide bugs with fallbacks

---

## Call Flow Architecture

### Single Function: `make_call()`
- First call: No button sequence → listens to identify menu
- Subsequent calls: With button sequence → navigates through tree
- No separate "exploration" vs "navigation" - same function handles both

### TwiML Structure (button sequence calls)
1. Initial 1s pause
2. For each button: Play DTMF + Pause until next button time
3. Gather with speech detection webhook
4. Record triggered by webhook

---

## Known Edge Cases

### Handled
- ✅ Repeating call trees (first occurrence matching)
- ✅ Multi-layer call trees (cumulative timing with skip_seconds)
- ✅ Poor Whisper segmentation (word-level timestamps)
- ✅ Number words ("one" vs "1") via normalization

### TODO / Watch Out For
- Call trees where no input routes to leasing automatically
- Very long menus where Gather timeout fires before button press
- Whisper mishearing numbers (e.g., "4" as "for")

---

## Environment & Running

### Required Services
- Flask app running (`python3 app.py`)
- ngrok tunnel (`ngrok http 5001`)
- Twilio credentials in `.env`

### Main Commands
```bash
# Full scrape + call
python3 simple_production_caller.py properties.csv

# Scrape only
python3 simple_production_caller.py properties.csv --scrape-only

# Call only (needs phone column)
python3 simple_production_caller.py scraped_phones.csv
```

---

## Git Conventions
- Data files (CSVs with results/phones) are gitignored
- Commit meaningful changes with descriptive messages
- Push to: https://github.com/elie-eliseai/callzilla.git

