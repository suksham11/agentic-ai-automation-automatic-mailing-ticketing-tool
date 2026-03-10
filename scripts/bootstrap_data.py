import json
from pathlib import Path

from datasets import load_dataset

DATASET_NAME = "bitext/Bitext-customer-support-llm-chatbot-training-dataset"
RAW_DIR = Path("data/raw")
EVAL_DIR = Path("data/eval")


def main(sample_size: int = 500) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    ds = load_dataset(DATASET_NAME, split="train")
    sampled = ds.select(range(min(sample_size, len(ds))))

    raw_path = RAW_DIR / "bitext_sample.jsonl"
    eval_path = EVAL_DIR / "eval_set.jsonl"

    with raw_path.open("w", encoding="utf-8") as raw_file, eval_path.open("w", encoding="utf-8") as eval_file:
        for i, row in enumerate(sampled):
            rec = {
                "source": "public_synthetic",
                "instruction": row.get("instruction", ""),
                "intent": row.get("intent", "unknown"),
                "category": row.get("category", "unknown"),
                "response": row.get("response", ""),
            }
            raw_file.write(json.dumps(rec, ensure_ascii=False) + "\n")

            if i % 5 == 0:
                eval_file.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Wrote sample records to {raw_path}")
    print(f"Wrote eval records to {eval_path}")


if __name__ == "__main__":
    main()
