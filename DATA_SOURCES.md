# Data Sources for Customer Support Agent

## Recommended Starter Dataset (Hugging Face)

- Dataset: `bitext/Bitext-customer-support-llm-chatbot-training-dataset`
- Link: https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset
- Why this one:
  - Customer-support focused (intents + responses)
  - Includes structured fields useful for automation agent MVP
  - Good for bootstrapping when you have no internal ticket history

## Suggested MVP Usage

- Use `instruction` as incoming customer message examples.
- Use `intent` and `category` to prototype ticket classification.
- Use `response` as initial drafting templates (with human review).
- Convert a subset into markdown files for retrieval testing in `data/kb/`.

## Important Notes

- Treat this dataset as bootstrap data, not production truth.
- Add company policy docs and real ticket outcomes as soon as available.
- Keep an audit trail of data origin: `public_synthetic` vs `internal_verified`.
