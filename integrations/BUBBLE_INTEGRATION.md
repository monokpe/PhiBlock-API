# 🫧 Bubble.io Integration Guide

This guide explains how to connect your Bubble.io application to Guardrails using the API Connector.

## Prerequisites

1. A Bubble.io account and app.
2. The **API Connector** plugin installed in your Bubble app.
3. Your Guardrails API Key.

## Setup Instructions

### 1. Import OpenAPI Spec

1. Open your Bubble app editor.
2. Go to **Plugins** > **API Connector**.
3. Click **Add another API**.
4. Name it "Guardrails".
5. Click **Import from JSON/OpenAPI**.
6. Paste the contents of [`bubble_openapi.json`](./bubble_openapi.json).
7. Click **Import**.

### 2. Configure Authentication

1. In the API Connector settings for "Guardrails":
2. Set **Authentication** to `Private key in header`.
3. **Key name**: `Authorization`
4. **Key value**: `Bearer YOUR_API_KEY`
5. **Development key value**: `Bearer YOUR_DEV_API_KEY`

### 3. Initialize Call

1. Expand the `Analyze Prompt` call.
2. Click **Initialize call**.
3. You should see a success response with `sanitized_prompt` and `detections`.
4. Click **Save**.

## Usage in Workflows

You can now use Guardrails in any workflow:

1. Add an action **Guardrails - Analyze Prompt**.
2. Map the **prompt** field to your input (e.g., `Input A's value`).
3. Use the result in subsequent steps:
   - `Result of step 1's sanitized_prompt` (to save safe data)
   - `Result of step 1's detections pii_found` (to show alerts)

## Example: Blocking PII

1. **Workflow**: When "Submit" is clicked.
2. **Step 1**: Guardrails - Analyze Prompt.
3. **Step 2**: Create a new Thing (Only when `Result of step 1's detections pii_found` is `no`).
4. **Step 3**: Show Alert (Only when `Result of step 1's detections pii_found` is `yes`).
