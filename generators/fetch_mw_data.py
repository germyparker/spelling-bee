"""
Fetch word data from Merriam-Webster API and save as JSON files.
Run this once to populate the mw_data/ directory.
"""

import os
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
from words import ONE_BEE, TWO_BEE, THREE_BEE

load_dotenv()

MW_API_KEY = os.getenv("MW_API_KEY_ELEMENTARY")
MW_API_URL = "https://dictionaryapi.com/api/v3/references/sd2/json/{word}?key={key}"

# Create data directory
DATA_DIR = Path("mw_data")
DATA_DIR.mkdir(exist_ok=True)


def flatten_word_list(word_list):
    """Flatten word list handling alternate spellings"""
    flattened = []
    for item in word_list:
        if isinstance(item, list):
            # First item is primary, rest are alternates
            primary = item[0]
            alternates = item[1:] if len(item) > 1 else []
            flattened.append(
                {"word": primary, "alternates": alternates, "is_primary": True}
            )
            for alt in alternates:
                flattened.append(
                    {
                        "word": alt,
                        "alternates": [],
                        "is_primary": False,
                        "primary_word": primary,
                    }
                )
        else:
            flattened.append({"word": item, "alternates": [], "is_primary": True})
    return flattened


def fetch_word_data(word):
    """Fetch data for a single word from MW API"""
    url = MW_API_URL.format(word=word, key=MW_API_KEY)

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        # Check if we got actual word data or just search suggestions
        if isinstance(data, list) and len(data) > 0:
            if isinstance(data[0], dict) and "meta" in data[0]:
                return data
            else:
                print(f"  ⚠️  '{word}' returned search suggestions, not word data")
                return None
        else:
            print(f"  ⚠️  '{word}' returned empty response")
            return None

    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error fetching '{word}': {e}")
        return None


def extract_word_info(word, data):
    """Extract relevant information from MW API response"""
    if not data:
        return None

    # Get the first entry (most relevant)
    entry = data[0]

    info = {
        "word": word,
        "api_response": data,  # Store full response for reference
        "has_audio": False,
        "audio_file": None,
        "shortdef": [],
        "is_inflection": False,
        "base_word": None,
        "functional_label": None,
        "pronunciation": None,
    }

    # Check for audio in hwi (headword information)
    if "hwi" in entry:
        hwi = entry["hwi"]
        if "prs" in hwi:
            for pr in hwi["prs"]:
                if "sound" in pr and "audio" in pr["sound"]:
                    info["has_audio"] = True
                    info["audio_file"] = pr["sound"]["audio"]
                    break

        # Get pronunciation
        if "prs" in hwi and len(hwi["prs"]) > 0:
            info["pronunciation"] = hwi["prs"][0].get("mw", "")

    # Get short definitions
    if "shortdef" in entry:
        info["shortdef"] = entry["shortdef"]

    # Get functional label (noun, verb, etc.)
    if "fl" in entry:
        info["functional_label"] = entry["fl"]

    # Check if this is an inflection (like "stuck" -> "stick")
    if "cxs" in entry:
        for cx in entry["cxs"]:
            if "cxl" in cx and "past tense" in cx["cxl"].lower():
                info["is_inflection"] = True
                if "cxtis" in cx and len(cx["cxtis"]) > 0:
                    info["base_word"] = cx["cxtis"][0].get("cxt", "")
                break

    return info


def format_audio_url(audio_file):
    """Format MW audio URL based on their subdirectory rules"""
    if not audio_file:
        return None

    # MW audio URL structure: https://media.merriam-webster.com/audio/prons/[lang]/[country]/[format]/[subdirectory]/[filename].[format]
    # Subdirectory rules:
    # - If starts with "bix", subdir is "bix"
    # - If starts with "gg", subdir is "gg"
    # - If starts with number or special char, subdir is "number"
    # - Otherwise, subdir is first letter

    if audio_file.startswith("bix"):
        subdir = "bix"
    elif audio_file.startswith("gg"):
        subdir = "gg"
    elif audio_file[0].isdigit() or not audio_file[0].isalpha():
        subdir = "number"
    else:
        subdir = audio_file[0]

    return f"https://media.merriam-webster.com/audio/prons/en/us/mp3/{subdir}/{audio_file}.mp3"


def main():
    all_words = [
        (1, "ONE_BEE", flatten_word_list(ONE_BEE)),
        (2, "TWO_BEE", flatten_word_list(TWO_BEE)),
        (3, "THREE_BEE", flatten_word_list(THREE_BEE)),
    ]

    summary = {
        "total": 0,
        "with_audio": 0,
        "without_audio": 0,
        "with_shortdef": 0,
        "without_shortdef": 0,
        "is_inflection": 0,
        "alternates_skipped": 0,
    }

    for level, level_name, words in all_words:
        print(f"\n📚 Processing {level_name} ({len(words)} words)...")

        for word_info in words:
            word = word_info["word"]

            # Skip non-primary words (alternates) for API fetching
            # We'll only fetch the primary spelling
            if not word_info["is_primary"]:
                print(f"  ⏭️  Skipping alternate spelling: {word}")
                summary["alternates_skipped"] += 1
                continue

            summary["total"] += 1

            # Check if we already have this data
            json_file = DATA_DIR / f"{word}.json"
            if json_file.exists():
                print(f"  ✓ Already have data for '{word}'")
                # Load and update summary
                with open(json_file) as f:
                    existing_info = json.load(f)
                    if existing_info.get("has_audio"):
                        summary["with_audio"] += 1
                    else:
                        summary["without_audio"] += 1
                    if existing_info.get("shortdef"):
                        summary["with_shortdef"] += 1
                    else:
                        summary["without_shortdef"] += 1
                    if existing_info.get("is_inflection"):
                        summary["is_inflection"] += 1
                continue

            print(f"  ⬇️  Fetching '{word}'...")

            # Fetch from API
            data = fetch_word_data(word)

            if data:
                info = extract_word_info(word, data)

                # Add metadata
                info["difficulty_level"] = level
                info["level_name"] = level_name
                info["alternates"] = word_info.get("alternates", [])

                # Format audio URL if available
                if info["has_audio"]:
                    info["audio_url"] = format_audio_url(info["audio_file"])
                    summary["with_audio"] += 1
                else:
                    summary["without_audio"] += 1

                if info["shortdef"]:
                    summary["with_shortdef"] += 1
                else:
                    summary["without_shortdef"] += 1

                if info["is_inflection"]:
                    summary["is_inflection"] += 1

                # Save to file
                with open(json_file, "w") as f:
                    json.dump(info, f, indent=2)

                print(f"    ✓ Saved data for '{word}'")
                print(
                    f"      Audio: {'✓' if info['has_audio'] else '✗'} | ShortDef: {'✓' if info['shortdef'] else '✗'} | Inflection: {'✓' if info['is_inflection'] else '✗'}"
                )
            else:
                print(f"    ✗ Failed to fetch '{word}'")

            # Rate limiting - be nice to MW's API
            time.sleep(0.5)

    # Print summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"Total words processed:     {summary['total']}")
    print(
        f"Words with audio:          {summary['with_audio']} ({summary['with_audio'] / summary['total'] * 100:.1f}%)"
    )
    print(
        f"Words without audio:       {summary['without_audio']} ({summary['without_audio'] / summary['total'] * 100:.1f}%)"
    )
    print(
        f"Words with shortdef:       {summary['with_shortdef']} ({summary['with_shortdef'] / summary['total'] * 100:.1f}%)"
    )
    print(
        f"Words without shortdef:    {summary['without_shortdef']} ({summary['without_shortdef'] / summary['total'] * 100:.1f}%)"
    )
    print(
        f"Inflections:               {summary['is_inflection']} ({summary['is_inflection'] / summary['total'] * 100:.1f}%)"
    )
    print(f"Alternate spellings skipped: {summary['alternates_skipped']}")
    print("=" * 60)

    # List words without audio (need manual audio files)
    print("\n⚠️  Words needing manual audio files:")
    for json_file in DATA_DIR.glob("*.json"):
        with open(json_file) as f:
            info = json.load(f)
            if not info.get("has_audio"):
                print(f"  - {info['word']} (Level {info['difficulty_level']})")


if __name__ == "__main__":
    if not MW_API_KEY:
        print("❌ Error: MW_API_KEY_ELEMENTARY not found in .env file")
        exit(1)

    main()
