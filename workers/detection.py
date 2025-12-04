import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from .main import app

# Load the tokenizer and model
tokenizer = AutoTokenizer.from_pretrained(
    "protectai/deberta-v3-base-prompt-injection-v2"
)  # nosec B615
model = AutoModelForSequenceClassification.from_pretrained(
    "protectai/deberta-v3-base-prompt-injection-v2"
)  # nosec B615


def get_injection_score(prompt: str) -> float:
    """
    Calculates the prompt injection score for a given prompt.

    Args:
        prompt: The prompt to analyze.

    Returns:
        The prompt injection score as a float between 0 and 1.
    """
    inputs = tokenizer(prompt, return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits

    return logits.softmax(dim=-1)[0][1].item()


@app.task
def detect_prompt_injection(prompt: str) -> float:
    """
    Celery task to detect prompt injection.

    Args:
        prompt: The prompt to analyze.

    Returns:
        The prompt injection score.
    """
    return get_injection_score(prompt)
