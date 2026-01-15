# 🦜🔗 Guardrails LangChain Integration

This guide explains how to use Guardrails to secure your LangChain applications.

## Overview

The integration provides two main components:
1. **`GuardrailsCallbackHandler`**: Automatically checks all LLM inputs and outputs for compliance.
2. **`GuardrailsRunnable`**: A composable unit for LCEL (LangChain Expression Language) chains that can sanitize or validate data.

## Installation

Ensure you have the Guardrails API running (default: `http://localhost:8000`).

You don't need a separate package installation if you are running this within the repo, but in a production setup, you would install the package containing the integration.

## Usage

### 1. Using the Callback Handler

The callback handler is the easiest way to add global protection to your chains.

```python
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from integrations.langchain_integration import GuardrailsCallbackHandler

# Initialize the handler
guardrails_handler = GuardrailsCallbackHandler(
    api_url="http://localhost:8000",
    raise_on_violation=True  # Raise error if PII/Injection detected
)

# Add to your model
llm = ChatOpenAI(
    callbacks=[guardrails_handler]
)

# Now all calls are protected
try:
    llm.invoke("My name is John Doe and my SSN is 123-45-6789")
except ValueError as e:
    print(f"Blocked: {e}")
```

### 2. Using LCEL Runnable

For more granular control, use `GuardrailsRunnable` in your chains. This allows you to sanitize input *before* it reaches the LLM.

```python
from langchain_core.output_parsers import StrOutputParser
from integrations.langchain_integration import GuardrailsRunnable

# Initialize runnable
guardrails = GuardrailsRunnable(api_url="http://localhost:8000")

# Create a chain: Input -> Guardrails (Sanitize) -> LLM -> Output
chain = (
    guardrails
    | ChatOpenAI()
    | StrOutputParser()
)

# "John Doe" will be replaced with "[PERSON]" before reaching the LLM
result = chain.invoke("Tell me a story about John Doe")
```

## Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `api_url` | URL of the Guardrails API | `http://localhost:8000` |
| `api_key` | API Key (or set `GUARDRAILS_API_KEY` env var) | `None` |
| `raise_on_violation` | Whether to raise exception on detection | `True` |

## Supported Checks

- **PII Detection**: Identifies and redacts sensitive info.
- **Prompt Injection**: Blocks malicious system override attempts.
- **Compliance**: Checks against HIPAA, GDPR, PIPEDA rules.
