"""
Fetch word data from School API (sd4) for words that failed in Elementary API (sd2).
Also handles accent removal for foreign words.
"""

import os
import json
import time
import requests
import unicodedata
from pathlib import Path
from dotenv import load_dotenv
from words import ONE_BEE, TWO_BEE, THREE_BEE

load_dotenv()

MW_API_KEY_ELEMENTARY = os.getenv("MW_API_KEY_ELEMENTARY")
MW_API_KEY_SCHOOL = os.getenv("MW_API_KEY_SCHOOL")
MW_API_URL_SD2 = "https://dictionaryapi.com/api/v3/references/sd2/json/{word}?key={key}"
MW_API_URL_SD4 = "https://dictionaryapi.com/api/v3/references/sd4/json/{word}?key={key}"

DATA_DIR = Path("mw_data")
DATA_DIR.mkdir(exist_ok=True)


def flatten_word_list(word_list):
    """Flatten word list handling alternate spellings"""
    flattened = []
    for item in word_list:
        if isinstance(item, list):
            primary = item[0]
            flattened.append(primary)
        else:
            flattened.append(item)
    return flattened


def remove_accents(text):
    """Remove accents from text (e.g., 'protégé' -> 'protege')"""
    # Normalize to NFD (decomposed form) then filter out combining characters
    nfd = unicodedata.normalize("NFD", text)
    return "".join(char for char in nfd if unicodedata.category(char) != "Mn")


def fetch_word_data(word, api_url, api_key):
    """Fetch data for a single word from MW API"""
    url = api_url.format(word=word, key=api_key)

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list) and len(data) > 0:
            if isinstance(data[0], dict) and "meta" in data[0]:
                return data
            else:
                return None
        else:
            return None

    except requests.exceptions.RequestException as e:
        return None


def extract_word_info(word, data, api_level):
    """Extract relevant information from MW API response"""
    if not data:
        return None

    entry = data[0]

    info = {
        "word": word,
        "api_response": data,
        "api_level": api_level,  # 'elementary' or 'school'
        "has_audio": False,
        "audio_file": None,
        "shortdef": [],
        "is_inflection": False,
        "base_word": None,
        "functional_label": None,
        "pronunciation": None,
    }

    # Check for audio
    if "hwi" in entry:
        hwi = entry["hwi"]
        if "prs" in hwi:
            for pr in hwi["prs"]:
                if "sound" in pr and "audio" in pr["sound"]:
                    info["has_audio"] = True
                    info["audio_file"] = pr["sound"]["audio"]
                    break

        if "prs" in hwi and len(hwi["prs"]) > 0:
            info["pronunciation"] = hwi["prs"][0].get("mw", "")

    if "shortdef" in entry:
        info["shortdef"] = entry["shortdef"]

    if "fl" in entry:
        info["functional_label"] = entry["fl"]

    # Check for inflections
    if "cxs" in entry:
        for cx in entry["cxs"]:
            if "cxl" in cx and "past tense" in cx["cxl"].lower():
                info["is_inflection"] = True
                if "cxtis" in cx and len(cx["cxtis"]) > 0:
                    info["base_word"] = cx["cxtis"][0].get("cxt", "")
                break

    return info


def format_audio_url(audio_file):
    """Format MW audio URL"""
    if not audio_file:
        return None

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
    # Get all words from lists
    all_word_lists = [
        (1, "ONE_BEE", flatten_word_list(ONE_BEE)),
        (2, "TWO_BEE", flatten_word_list(TWO_BEE)),
        (3, "THREE_BEE", flatten_word_list(THREE_BEE)),
    ]

    # Find words without JSON files
    missing_words = []
    for level, level_name, word_list in all_word_lists:
        for word in word_list:
            json_file = DATA_DIR / f"{word}.json"
            if not json_file.exists():
                missing_words.append((level, level_name, word))

    if not missing_words:
        print("✅ All words have JSON files!")
        return

    print(f"\n📋 Found {len(missing_words)} words without JSON files")
    print("🔍 Attempting to fetch from School API (sd4)...\n")

    summary = {
        "total": len(missing_words),
        "found_exact": 0,
        "found_no_accent": 0,
        "still_missing": 0,
        "with_audio": 0,
        "without_audio": 0,
    }

    for level, level_name, word in missing_words:
        print(f"\n{'=' * 60}")
        print(f"Processing: {word} ({level_name})")
        print("=" * 60)

        json_file = DATA_DIR / f"{word}.json"
        data = None
        search_variants = [word]

        # Add variant without accents if word has accents
        word_no_accent = remove_accents(word)
        if word_no_accent != word:
            search_variants.append(word_no_accent)
            print(f"  Will try variant without accents: '{word_no_accent}'")

        # Try each variant
        for variant in search_variants:
            print(f"  🔍 Trying: '{variant}' in School API...")
            data = fetch_word_data(variant, MW_API_URL_SD4, MW_API_KEY_SCHOOL)

            if data:
                print(f"  ✓ Found in School API!")
                if variant != word:
                    summary["found_no_accent"] += 1
                    print(f"  ℹ️  Found using de-accented variant")
                else:
                    summary["found_exact"] += 1
                break
            else:
                print(f"  ✗ Not found")

        # If still not found, try Elementary API one more time
        # (in case there was a temporary network issue)
        if not data:
            print(f"  🔍 Retrying Elementary API...")
            data = fetch_word_data(word, MW_API_URL_SD2, MW_API_KEY_ELEMENTARY)
            if data:
                print(f"  ✓ Found in Elementary API on retry!")
                summary["found_exact"] += 1

        if data:
            # Extract info
            api_level = (
                "school" if variant in search_variants[1:] or not data else "elementary"
            )
            info = extract_word_info(word, data, api_level)

            if info:
                info["difficulty_level"] = level
                info["level_name"] = level_name
                info["alternates"] = []
                info["original_search_term"] = variant if variant != word else word

                if info["has_audio"]:
                    info["audio_url"] = format_audio_url(info["audio_file"])
                    summary["with_audio"] += 1
                    print(f"  ✓ Has audio: {info['audio_file']}")
                else:
                    summary["without_audio"] += 1
                    print(f"  ✗ No audio available")

                if info["shortdef"]:
                    print(f"  ✓ Has definition")
                else:
                    print(f"  ⚠️  No shortdef available")

                # Save
                with open(json_file, "w") as f:
                    json.dump(info, f, indent=2)

                print(f"  💾 Saved to {json_file.name}")
            else:
                print(f"  ⚠️  Could not extract info from response")
                summary["still_missing"] += 1
        else:
            print(f"  ❌ Not found in any API")
            summary["still_missing"] += 1

            # Create minimal entry so we don't keep trying
            minimal_info = {
                "word": word,
                "api_response": [],
                "api_level": "none",
                "has_audio": False,
                "audio_file": None,
                "shortdef": [],
                "is_inflection": False,
                "base_word": None,
                "functional_label": None,
                "pronunciation": None,
                "difficulty_level": level,
                "level_name": level_name,
                "alternates": [],
                "note": "Not found in Elementary or School API",
            }

            with open(json_file, "w") as f:
                json.dump(minimal_info, f, indent=2)

            print(f"  💾 Saved minimal entry")

        # Rate limiting
        time.sleep(0.5)

    # Print summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"Total words processed:       {summary['total']}")
    print(f"Found with exact spelling:   {summary['found_exact']}")
    print(f"Found without accents:       {summary['found_no_accent']}")
    print(f"Still missing:               {summary['still_missing']}")
    print(f"Words with audio:            {summary['with_audio']}")
    print(f"Words without audio:         {summary['without_audio']}")
    print("=" * 60)

    if summary["still_missing"] > 0:
        print("\n⚠️  Words still not found:")
        for level, level_name, word in missing_words:
            json_file = DATA_DIR / f"{word}.json"
            if json_file.exists():
                with open(json_file) as f:
                    info = json.load(f)
                    if info.get("api_level") == "none":
                        print(f"  - {word} ({level_name})")


if __name__ == "__main__":
    if not MW_API_KEY_ELEMENTARY or not MW_API_KEY_SCHOOL:
        print(
            "❌ Error: MW_API_KEY_ELEMENTARY and MW_API_KEY_SCHOOL must be in .env file"
        )
        exit(1)

    main()
