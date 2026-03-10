import json
from pathlib import Path

RAW_FILE = Path("data/raw/bitext_sample.jsonl")
KB_DIR = Path("data/kb")


def main(max_docs: int = 80) -> None:
    KB_DIR.mkdir(parents=True, exist_ok=True)

    if not RAW_FILE.exists():
        raise FileNotFoundError("Run scripts/bootstrap_data.py first.")

    by_intent: dict[str, list[dict]] = {}

    with RAW_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            by_intent.setdefault(row.get("intent", "unknown"), []).append(row)

    written = 0
    for intent, rows in by_intent.items():
        if written >= max_docs:
            break
        out = KB_DIR / f"{intent}.md"
        body = [f"# Intent: {intent}", "", "## Examples"]
        for row in rows[:10]:
            body.append(f"- User: {row.get('instruction', '').strip()}")
            body.append(f"  Suggested response: {row.get('response', '').strip()}")
        out.write_text("\n".join(body), encoding="utf-8")
        written += 1

    print(f"Generated {written} KB markdown files in {KB_DIR}")


if __name__ == "__main__":
    main()
