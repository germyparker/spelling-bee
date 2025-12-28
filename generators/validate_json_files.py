"""
Validate all JSON files in mw_data/ and identify any structural issues.
"""

import json
from pathlib import Path

DATA_DIR = Path("mw_data")


def validate_json_file(json_file):
    """Validate a single JSON file and return issues"""
    issues = []

    try:
        with open(json_file) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"JSON decode error: {e}"]

    # Check if it's a dict
    if not isinstance(data, dict):
        return [f"Wrong type: expected dict, got {type(data).__name__}"]

    # Check required fields
    required_fields = ["word", "has_audio", "audio_file", "shortdef"]
    for field in required_fields:
        if field not in data:
            issues.append(f"Missing field: '{field}'")

    # Check for unexpected structure (like raw API response)
    if "word" not in data and isinstance(data, list):
        issues.append(
            "Appears to be raw API response (list) instead of extracted info (dict)"
        )

    # Check if it has proper extracted structure
    if "difficulty_level" not in data:
        issues.append("Missing 'difficulty_level' field")

    if "audio_url" not in data:
        issues.append("Missing 'audio_url' field")

    return issues


def main():
    json_files = list(DATA_DIR.glob("*.json"))

    if not json_files:
        print("❌ No JSON files found in mw_data/")
        return

    print(f"🔍 Validating {len(json_files)} JSON files...\n")

    problematic_files = []

    for json_file in sorted(json_files):
        issues = validate_json_file(json_file)

        if issues:
            problematic_files.append((json_file, issues))
            print(f"❌ {json_file.name}")
            for issue in issues:
                print(f"   - {issue}")
            print()

    if problematic_files:
        print("=" * 60)
        print(f"⚠️  Found {len(problematic_files)} problematic files")
        print("=" * 60)
        print("\n💡 Suggested fixes:")
        print("1. Delete problematic files")
        print("2. Re-run fetch_mw_data.py or fetch_fallback_words.py")
        print("\nOr delete individually:")
        for json_file, _ in problematic_files:
            print(f"   rm {json_file}")
    else:
        print("✅ All JSON files are valid!")

        # Additional stats
        print("\n📊 JSON File Statistics:")

        stats = {
            "with_audio": 0,
            "without_audio": 0,
            "elementary": 0,
            "school": 0,
            "none": 0,
            "is_inflection": 0,
        }

        for json_file in json_files:
            with open(json_file) as f:
                data = json.load(f)

            if data.get("has_audio"):
                stats["with_audio"] += 1
            else:
                stats["without_audio"] += 1

            api_level = data.get("api_level", "unknown")
            if api_level == "elementary":
                stats["elementary"] += 1
            elif api_level == "school":
                stats["school"] += 1
            elif api_level == "none":
                stats["none"] += 1

            if data.get("is_inflection"):
                stats["is_inflection"] += 1

        print(f"  Total files:           {len(json_files)}")
        print(
            f"  With audio:            {stats['with_audio']} ({stats['with_audio'] / len(json_files) * 100:.1f}%)"
        )
        print(
            f"  Without audio:         {stats['without_audio']} ({stats['without_audio'] / len(json_files) * 100:.1f}%)"
        )
        print(f"  From Elementary API:   {stats['elementary']}")
        print(f"  From School API:       {stats['school']}")
        print(f"  Not found in any API:  {stats['none']}")
        print(f"  Inflections:           {stats['is_inflection']}")


if __name__ == "__main__":
    main()
