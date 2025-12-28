"""
Download audio files from Merriam-Webster to local filesystem.
Creates organized directory structure: audio/one_bee/, audio/two_bee/, audio/three_bee/
"""

import json
import requests
import time
from pathlib import Path

DATA_DIR = Path("mw_data")
AUDIO_DIR = Path("audio")

# Create audio directories
for level_dir in ["one_bee", "two_bee", "three_bee"]:
    (AUDIO_DIR / level_dir).mkdir(parents=True, exist_ok=True)


def download_audio(url, output_path):
    """Download audio file from URL to local path"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(response.content)

        return True
    except requests.exceptions.RequestException as e:
        print(f"    ❌ Error downloading: {e}")
        return False


def main():
    # Get all JSON files
    json_files = list(DATA_DIR.glob("*.json"))

    if not json_files:
        print("❌ No JSON files found in mw_data/. Run fetch_mw_data.py first!")
        return

    print(f"📥 Found {len(json_files)} word data files")
    print("🎵 Downloading audio files...\n")

    summary = {
        "total_words": len(json_files),
        "with_audio_url": 0,
        "downloaded": 0,
        "already_exist": 0,
        "failed": 0,
        "no_audio": 0,
        "invalid_json": 0,
    }

    for json_file in sorted(json_files):
        try:
            with open(json_file) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ Error reading {json_file.name}: {e}")
            summary["invalid_json"] += 1
            continue

        # Validate JSON structure
        if not isinstance(data, dict):
            print(
                f"⚠️  {json_file.name}: Invalid JSON structure (expected dict, got {type(data).__name__})"
            )
            summary["invalid_json"] += 1
            continue

        if "word" not in data:
            print(f"⚠️  {json_file.name}: Missing 'word' field")
            summary["invalid_json"] += 1
            continue

        word = data["word"]

        # Get difficulty level - handle both old and new format
        level = data.get("difficulty_level")
        if level is None:
            # Try to infer from filename or skip
            print(f"⚠️  {word}: Missing 'difficulty_level' field, skipping")
            continue

        level_dir = ["one_bee", "two_bee", "three_bee"][level - 1]

        # Determine output path
        output_path = AUDIO_DIR / level_dir / f"{word}.mp3"

        print(f"Processing: {word} ({level_dir})")

        # Check if audio URL exists
        audio_url = data.get("audio_url")

        if not audio_url:
            print(f"  ⚠️  No audio URL available")
            summary["no_audio"] += 1
            continue

        summary["with_audio_url"] += 1

        # Check if already downloaded
        if output_path.exists():
            file_size = output_path.stat().st_size
            if file_size > 1000:  # At least 1KB (sanity check)
                print(f"  ✓ Already exists ({file_size:,} bytes)")
                summary["already_exist"] += 1
                continue
            else:
                print(
                    f"  ⚠️  File exists but seems corrupted (only {file_size} bytes), re-downloading..."
                )

        # Download
        print(f"  ⬇️  Downloading from MW...")
        print(f"     {audio_url}")

        if download_audio(audio_url, output_path):
            file_size = output_path.stat().st_size
            print(f"  ✓ Downloaded successfully ({file_size:,} bytes)")
            summary["downloaded"] += 1
        else:
            print(f"  ❌ Download failed")
            summary["failed"] += 1

        # Rate limiting - be nice to MW's servers
        time.sleep(0.3)

    # Print summary
    print("\n" + "=" * 60)
    print("📊 DOWNLOAD SUMMARY")
    print("=" * 60)
    print(f"Total words:                {summary['total_words']}")
    print(f"Words with audio URL:       {summary['with_audio_url']}")
    print(f"Successfully downloaded:    {summary['downloaded']}")
    print(f"Already existed:            {summary['already_exist']}")
    print(f"Download failed:            {summary['failed']}")
    print(f"No audio available:         {summary['no_audio']}")
    print(f"Invalid JSON files:         {summary['invalid_json']}")
    print("=" * 60)

    # Show directory sizes
    print("\n📂 Audio directory sizes:")
    for level_dir in ["one_bee", "two_bee", "three_bee"]:
        level_path = AUDIO_DIR / level_dir
        mp3_files = list(level_path.glob("*.mp3"))
        total_size = sum(f.stat().st_size for f in mp3_files)
        print(
            f"  {level_dir:12s}: {len(mp3_files):3d} files, {total_size / 1024 / 1024:.2f} MB"
        )

    if summary["invalid_json"] > 0:
        print(f"\n⚠️  {summary['invalid_json']} invalid JSON files detected.")
        print("   These files may need to be regenerated. Check the output above.")

    if summary["no_audio"] > 0:
        print(f"\n⚠️  {summary['no_audio']} words still need manual audio recording.")
        print("   Run check_missing_audio.py to see which words need audio files.")


if __name__ == "__main__":
    main()
