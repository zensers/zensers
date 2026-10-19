# -*- coding: utf-8 -*-
"""
API Module
"""

from .research_api import ResearchAPI, research_api
from .document_api import DocumentAPI  # Original API
from .prompt_api import PromptAPI, prompt_api, create_prompt_api

__all__ = [
    "ResearchAPI",
    "research_api",
    "DocumentAPI",
    "PromptAPI",
    "prompt_api",
    "create_prompt_api",
]
