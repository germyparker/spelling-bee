"""
Check which words are missing audio files and need manual recording.
"""

import json
from pathlib import Path
from words import ONE_BEE, TWO_BEE, THREE_BEE


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


def main():
    mw_data_dir = Path("mw_data")

    if not mw_data_dir.exists():
        print("❌ mw_data directory not found. Run fetch_mw_data.py first!")
        return

    all_words = [
        ("ONE_BEE", flatten_word_list(ONE_BEE)),
        ("TWO_BEE", flatten_word_list(TWO_BEE)),
        ("THREE_BEE", flatten_word_list(THREE_BEE)),
    ]

    missing_audio = []

    for level_name, word_list in all_words:
        for word in word_list:
            json_file = mw_data_dir / f"{word}.json"

            if json_file.exists():
                with open(json_file) as f:
                    data = json.load(f)

                if not data.get("has_audio"):
                    missing_audio.append(
                        {
                            "word": word,
                            "level": level_name,
                            "is_inflection": data.get("is_inflection", False),
                            "base_word": data.get("base_word", ""),
                            "definition": " • ".join(data.get("shortdef", []))
                            if data.get("shortdef")
                            else "No definition available",
                        }
                    )
            else:
                missing_audio.append(
                    {
                        "word": word,
                        "level": level_name,
                        "is_inflection": False,
                        "base_word": "",
                        "definition": "No MW data available",
                    }
                )

    if missing_audio:
        print("\n" + "=" * 70)
        print("⚠️  WORDS REQUIRING MANUAL AUDIO FILES")
        print("=" * 70)
        print(f"\nTotal words needing audio: {len(missing_audio)}\n")

        for item in missing_audio:
            print(f"📝 {item['word'].upper()} ({item['level']})")
            if item["is_inflection"]:
                print(f"   ℹ️  Inflection of: {item['base_word']}")
            print(f"   Definition: {item['definition'][:100]}...")
            print(f"   File needed: audio/{item['level'].lower()}/{item['word']}.mp3")
            print()

        print("=" * 70)
        print("\n💡 SUGGESTIONS:")
        print("1. Use a text-to-speech tool (e.g., macOS 'say' command, Google TTS)")
        print("2. Record your own voice saying the words")
        print("3. Use online pronunciation tools and record the audio")
        print("\nExample using macOS 'say' command:")
        print(
            f"  say -o audio/one_bee/{missing_audio[0]['word']}.mp3 --data-format=LEF32@22050 '{missing_audio[0]['word']}'"
        )
        print("=" * 70)
    else:
        print("\n✅ All words have audio available from Merriam-Webster API!")


if __name__ == "__main__":
    main()
