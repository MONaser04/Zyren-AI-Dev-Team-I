"""
Unified Intent Classification Schema
======================================
Used by the Liaison agent to route incoming natural language intelligently.
"""
from enum import Enum
from pydantic import BaseModel, Field
from typing import Any, Dict

class UserIntentCategory(str, Enum):
    """Broad categories of user intent."""
    CONVERSATIONAL = "conversational"
    SYSTEM_COMMAND = "system_command"
    RESEARCH = "research"
    DEEP_RESEARCH = "deep_research"
    FAST_CODE = "fast_code"
    FULL_SDLC = "full_sdlc"

class ParsedIntent(BaseModel):
    """The structured output of the LLM intent classifier."""
    category: UserIntentCategory = Field(
        ...,
        description="The classified category of the user's intent."
    )
    reasoning: str = Field(
        ...,
        description="A brief explanation of why this category was chosen."
    )
    extracted_parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Any useful parameters extracted (e.g. 'model_name', 'topic')."
    )
    reply: str = Field(
        default="",
        description="A direct response to the user, REQUIRED for CONVERSATIONAL intents. If it's a follow up question, answer it directly using context."
    )
    extracted_facts: list[str] = Field(
        default_factory=list,
        description="New persistent facts about the user to remember (e.g., 'My name is X')."
    )
    facts_to_remove: list[str] = Field(
        default_factory=list,
        description="Old facts to remove if the user corrects them."
    )
