"""Shared types and utilities for workflow processing."""

import os
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum
from anthropic import Anthropic


@dataclass
class TabSessionSummary:
    url: str
    viewport: str  # Summary of markdowns from page-loads in this group
    activity_summary: str  # Analysis of the full tab group activities
    events_count: int
    tab_id: Optional[int] = None


@dataclass
class WorkflowStep:
    description: str
    type: Optional[str] = (
        None  # Will be determined later when tool context is available
    )
    tools: Optional[List[str]] = None  # Only used for tool type steps


@dataclass
class Workflow:
    summary: str
    steps: List[WorkflowStep]


class DeterminerResponse(Enum):
    WORKFLOW = "workflow"  # Complete workflow found
    NOISE = "noise"  # Should be discarded
    UNFINISHED = "unfinished"  # Part of workflow but needs more data


def get_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    return Anthropic(api_key=api_key)
