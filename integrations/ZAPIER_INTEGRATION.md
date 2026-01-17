# ⚡ Zapier Integration Guide

This guide explains how to connect Guardrails to Zapier to automate compliance checks in your workflows.

## Overview

The Guardrails Zapier integration allows you to:
- **Action**: Analyze text from any app (Slack, Gmail, Typeform) for PII and compliance violations.
- **Trigger**: Start a workflow when a new violation is logged in Guardrails.

## Installation (Private Integration)

Since this is a private API, you will create a custom integration in the Zapier Platform.

### 1. Create Integration

1. Go to [Zapier Platform](https://developer.zapier.com/).
2. Click **Start a Zapier Integration**.
3. Name it "Guardrails".
4. Role: **Private**.

### 2. Configure Authentication

1. Select **API Key** authentication.
2. In the connection settings, define a field `api_key`.
3. Set the test URL to `https://api.guardrails.dev/v1/health`.

### 3. Import Definition

You can manually configure the triggers/actions or use the CLI. For manual configuration based on our spec:

#### Action: Analyze Prompt
- **API Endpoint**: `POST /v1/analyze`
- **Input Field**: `prompt` (String, Required)
- **Request Body**: `{"prompt": "{{bundle.inputData.prompt}}"}`
- **Headers**: `Authorization: Bearer {{bundle.authData.api_key}}`

#### Trigger: New Violation
- **API Endpoint**: `GET /v1/analytics/violations`
- **Polling**: Checks for new violations every 5-15 minutes.

## Example Workflows

### 1. Slack Moderation Bot
**Trigger**: New Message posted to channel #general (Slack)
**Action**: Analyze Prompt (Guardrails)
**Filter**: Only continue if `detections.pii_found` is `true`
**Action**: Send Direct Message to User (Slack) - "Please do not post PII."

### 2. Compliance Audit Log
**Trigger**: New Compliance Violation (Guardrails)
**Action**: Create Row (Google Sheets)
**Mapping**:
- Column A: `severity`
- Column B: `message`
- Column C: `created_at`
