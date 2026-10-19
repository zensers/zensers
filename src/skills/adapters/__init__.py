"""
Skill adapter module

Provides adapters for third-party tools/libraries, wrapping external tools into a unified Skill interface.

Currently supported:
- LangChain Tool adapter

Future extensible:
- LlamaIndex adapter
- WorkBuddy Skill adapter
- Custom tool adapter
"""

from .langchain_adapter import LangChainToolSkill, LangChainAdapter

__all__ = ["LangChainToolSkill", "LangChainAdapter"]
