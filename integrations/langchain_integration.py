"""
Guardrails LangChain Integration

This module provides integration with LangChain, allowing you to use Guardrails
as a compliance layer in your LangChain applications.

Classes:
    GuardrailsCallbackHandler: Intercepts LLM inputs/outputs and checks compliance.
    GuardrailsRunnable: A Runnable for LCEL chains.
"""

from typing import Any, Dict, List, Optional, Union
import requests
import os

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.messages import BaseMessage


class GuardrailsCallbackHandler(BaseCallbackHandler):
    """
    Callback Handler that checks prompts and completions against Guardrails API.
    
    Raises an error or modifies the output if a violation is detected.
    """
    
    def __init__(
        self, 
        api_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        raise_on_violation: bool = True
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key or os.getenv("GUARDRAILS_API_KEY")
        self.raise_on_violation = raise_on_violation
        
    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        """Run when LLM starts running."""
        for prompt in prompts:
            self._check_compliance(prompt, "input")

import logging

logger = logging.getLogger(__name__)

# ... (rest of the file)

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """Run when LLM ends running."""
        if hasattr(response, "generations"):
            for generation_list in response.generations:
                for generation in generation_list:
                    self._check_compliance(generation.text, "output")

    def _check_compliance(self, text: str, source: str) -> None:
        """Call Guardrails API to check compliance."""
        if not text or not text.strip():
            return

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            resp = requests.post(
                f"{self.api_url}/v1/analyze",
                json={"prompt": text},
                headers=headers,
                timeout=5
            )
            resp.raise_for_status()
            result = resp.json()
            
            detections = result.get("detections", {})
            if detections.get("pii_found") or detections.get("injection_detected"):
                msg = f"Guardrails Violation detected in {source}: "
                details = []
                if detections.get("pii_found"):
                    details.append("PII detected")
                if detections.get("injection_detected"):
                    details.append("Prompt Injection detected")
                
                full_msg = msg + ", ".join(details)
                
                if self.raise_on_violation:
                    raise ValueError(full_msg)
                else:
                    logger.warning(full_msg)
                    
        except Exception as e:
            if self.raise_on_violation:
                raise e
            logger.error(f"Error checking compliance: {e}")


class GuardrailsRunnable(Runnable):
    """
    A LangChain Runnable that passes input through Guardrails API.
    
    Use this in an LCEL chain:
    chain = prompt | model | GuardrailsRunnable() | output_parser
    """
    
    def __init__(
        self, 
        api_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        mode: str = "analyze" # analyze, redact, or mask
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key or os.getenv("GUARDRAILS_API_KEY")
        self.mode = mode

    def invoke(self, input: Union[str, BaseMessage, Dict], config: Optional[RunnableConfig] = None) -> Any:
        text = ""
        if isinstance(input, str):
            text = input
        elif hasattr(input, "content"):
            text = input.content
        elif isinstance(input, dict):
            text = input.get("text") or input.get("content") or input.get("input") or str(input)
        else:
            text = str(input)
            
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        resp = requests.post(
            f"{self.api_url}/v1/analyze",
            json={"prompt": text},
            headers=headers
        )
        resp.raise_for_status()
        result = resp.json()
        
        if result.get("sanitized_prompt") and result.get("sanitized_prompt") != text:
            if isinstance(input, str):
                return result["sanitized_prompt"]
            elif hasattr(input, "content"):
                input.content = result["sanitized_prompt"]
                return input
                
        return input
