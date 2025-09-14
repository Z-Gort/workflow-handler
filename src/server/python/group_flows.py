import sys
import json
import os
from dataclasses import dataclass
from typing import List, Dict, Optional, Union, Tuple
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


def summarize_markdowns(markdowns: List[str]) -> str:
    if not markdowns:
        return "No content available"

    client = get_anthropic_client()

    combined_content = "\n\n--- PAGE SEPARATOR ---\n\n".join(markdowns)

    prompt = f"""Please create a concise viewport summary of the following web page content(s). 
Focus on the main topics, key information, and overall purpose. Keep it under 150 words.

Content from {len(markdowns)} page(s):
{combined_content}
"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        if response.content and len(response.content) > 0:
            content_block = response.content[0]
            # Handle different content block types
            if hasattr(content_block, "text"):
                return content_block.text.strip()  # type: ignore
            elif hasattr(content_block, "content"):
                return str(content_block.content).strip()  # type: ignore
            else:
                return str(content_block).strip()
        return f"Viewport summary of {len(markdowns)} page(s) - Error: No text content"
    except Exception as e:
        return f"Viewport summary of {len(markdowns)} page(s) - Error: {str(e)}"


def analyze_tab_group_activity(events: List[Dict], viewport_summary: str) -> str:
    client = get_anthropic_client()

    event_summary = []
    for event in events:
        event_type = event.get("type", "unknown")
        url = event.get("url", "")
        timestamp = event.get("timestamp", "")
        event_summary.append(f"- {event_type} on {url} at {timestamp}")

    events_text = "\n".join(event_summary)

    prompt = f"""Analyze this user browsing session and provide a concise activity summary (under 100 words).
Focus on what the user was doing, their intent, and the nature of their interaction.

Viewport Context: {viewport_summary}

User Events:
{events_text}
"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        print("RESPONSE", response)
        if response.content and len(response.content) > 0:
            content_block = response.content[0]
            # Handle different content block types
            if hasattr(content_block, "text"):
                return content_block.text.strip()  # type: ignore
            elif hasattr(content_block, "content"):
                return str(content_block.content).strip()  # type: ignore
            else:
                return str(content_block).strip()
        return f"Activity summary: {len(events)} events - Error: No text content"
    except Exception as e:
        event_types = [event.get("type", "") for event in events]
        return f"Activity summary: {len(events)} events ({', '.join(set(event_types))}) - Error: {str(e)}"


def get_base_url(url):
    if not url:
        return None
    # Extract domain from URL (everything up to first slash after protocol)
    if "://" in url:
        return url.split("://")[0] + "://" + url.split("://")[1].split("/")[0]
    return url.split("/")[0]


def create_tab_group_summary(
    group_events: List[Dict], tab_markdowns: Dict[int, str]
) -> Optional[TabSessionSummary]:
    """
    Creates a TabGroupSummary from a group of events.

    Args:
        group_events: List of events in this tab group
        tab_markdowns: Dictionary mapping tab_id to most recent markdown content
    """
    if not group_events:
        return None

    # Get base URL from first event (should be page-load or tab-switch)
    first_event = group_events[0]
    base_url = get_base_url(first_event.get("url", ""))
    tab_id = first_event.get("tabId")

    # Collect markdowns from page-load events in this group
    markdowns = []
    for event in group_events:
        if event.get("type") == "page-load":
            markdown = event.get("payload", {}).get("markdown", "")
            if markdown:
                markdowns.append(markdown)

    # If no markdowns in group (e.g., started with tab-switch), use tab's last known markdown
    if not markdowns and tab_id and tab_id in tab_markdowns:
        markdowns.append(tab_markdowns[tab_id])

    # Create summaries using placeholder functions
    viewport_summary = summarize_markdowns(markdowns)
    activity_summary = analyze_tab_group_activity(group_events, viewport_summary)

    return TabSessionSummary(
        url=base_url or "Unknown",
        viewport=viewport_summary,
        activity_summary=activity_summary,
        events_count=len(group_events),
        tab_id=tab_id,
    )


def group_events_into_tab_sessions(events) -> List[TabSessionSummary]:
    tab_groups = []
    current_group = []
    current_base_url = None
    tab_markdowns = {}  # Track markdowns by tab_id

    for event in events:
        event_type = event.get("type", "")

        # Update tab markdowns when we see page-load events
        if event_type == "page-load":
            tab_id = event.get("tabId")
            markdown = event.get("payload", {}).get("markdown", "")
            if tab_id and markdown:
                tab_markdowns[tab_id] = markdown

        if event_type == "page-load":
            event_base_url = get_base_url(event.get("url", ""))

            # Only start new group if base URL changed
            if event_base_url != current_base_url:
                # Save current group before starting new one
                if current_group:
                    summary = create_tab_group_summary(current_group, tab_markdowns)
                    if summary:
                        tab_groups.append(summary)
                current_group = [event]
                current_base_url = event_base_url
            else:
                # Same base URL, just add to current group
                current_group.append(event)

        elif event_type == "tab-switch":
            # Save current group before starting new one
            if current_group:
                summary = create_tab_group_summary(current_group, tab_markdowns)
                if summary:
                    tab_groups.append(summary)
            # Start new group with this tab-switch event
            current_group = [event]
            # Reset base URL tracking since we switched tabs
            current_base_url = None

        elif event_type == "tab-removal":
            # Save current group before ending
            if current_group:
                summary = create_tab_group_summary(current_group, tab_markdowns)
                if summary:
                    tab_groups.append(summary)
            current_group = []
            current_base_url = None

        else:
            # Regular events (click, type, copy, paste, highlight)
            current_group.append(event)

    if current_group:
        summary = create_tab_group_summary(current_group, tab_markdowns)
        if summary:
            tab_groups.append(summary)

    # Print debug info
    for i, summary in enumerate(tab_groups):
        print(f"--- GROUP {i+1} ---")
        print(f"URL: {summary.url}")
        print(f"Events: {summary.events_count}")
        print(f"Viewport: {summary.viewport}")
        print(f"Activity: {summary.activity_summary}")
        print()

    print(f"Total groups: {len(tab_groups)}")
    return tab_groups


def ai_workflow_determiner(
    window: List[TabSessionSummary],
) -> Tuple[DeterminerResponse, Optional[Workflow]]:
    """
    Use AI to determine if a window of tab sessions constitutes a workflow.
    """
    client = get_anthropic_client()

    # Build session descriptions
    session_descriptions = []
    for i, session in enumerate(window):
        session_descriptions.append(
            f"Session {i+1}: {session.url}\n"
            f"  Page content: {session.viewport}\n"
            f"  User activity: {session.activity_summary}\n"
            f"  Events: {session.events_count}"
        )

    sessions_text = "\n\n".join(session_descriptions)

    prompt = f"""Analyze this sequence of browser sessions to determine if they constitute a complete workflow, are just noise/random browsing, or are part of an unfinished workflow.

BROWSER SESSIONS TO ANALYZE:
{sessions_text}

WORKFLOW DEFINITION:
A workflow is a coherent sequence of browser activities that accomplish a SPECIFIC, ACTIONABLE goal. The user must be actively working toward something concrete, not just browsing or consuming content.

VALID WORKFLOW EXAMPLES:
- Research a person on LinkedIn → Add their details to a spreadsheet → Create/update CRM contact
- Read support documentation → Summarize findings → Add to knowledge base  
- Check email for meeting request → Check calendar availability → Respond with availability
- Compare product prices across sites → Add item to cart → Complete purchase
- Research job posting → Update resume → Submit application

CRITICAL WORKFLOW REQUIREMENTS:
1. COMPLETE WORKFLOW: 
   - Must have 2+ DISTINCT, RELATED ACTIONS that build toward a clear goal
   - Shows intentional progression with PURPOSE (not random browsing)
   - Has a logical story: research → action → completion
   - User must be CREATING, UPDATING, SENDING, or COMPLETING something
   - NOT just reading, browsing, or consuming content
   - It CAN have some noise, just IGNORE it when describing the workflow

2. IGNORE NOISE IN WORKFLOWS:
   - Authentication pages, login flows, OAuth screens are irrelevant noise
   - Accidental clicks, brief visits, loading pages should be ignored
   - Focus only on the meaningful actions that advance the goal
   - If removing noise leaves <2 meaningful steps, it's not a workflow

3. NOISE/RANDOM (classify as "noise"):
   - Just browsing social media, news, entertainment
   - Only reading/consuming content without follow-up action
   - Single actions without clear continuation
   - General research without specific goal or outcome
   - Just "accessing" or "viewing" platforms without doing anything

4. UNFINISHED WORKFLOW:
   - Shows clear intentional progression toward a specific goal
   - Has meaningful actions building up to something
   - But missing the final completion step
   - Could become a complete workflow with more sessions

BE VERY STRICT: If the user is just browsing, reading, or "accessing" things without clear productive action, it is NOT a workflow. 
Workflows must tell a story of purposeful work toward a specific outcome. It is possible that within a workflow there is intermittemnt noise, so if there is ANY logical buildup happening, classify as UNFINISHED."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        tools=[
            {
                "name": "classify_workflow",
                "description": "Classify the browser sessions as workflow, noise, or unfinished",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "classification": {
                            "type": "string",
                            "enum": ["workflow", "noise", "unfinished"],
                            "description": "Whether this is a complete workflow, noise, or unfinished workflow",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Reasoning for this classification decision",
                        },
                        "workflow_summary": {
                            "type": "string",
                            "description": "If classification is 'workflow', provide a clear summary of what the workflow accomplishes. Leave empty for noise/unfinished.",
                        },
                        "workflow_steps": {
                            "type": "array",
                            "description": "If classification is 'workflow', break down into logical steps. Leave empty for noise/unfinished.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {
                                        "type": "string",
                                        "description": "What happens in this step",
                                    }
                                },
                                "required": ["description"],
                            },
                        },
                    },
                    "required": ["classification", "reasoning"],
                },
            }
        ],
        tool_choice={"type": "tool", "name": "classify_workflow"},
    )

    # Extract structured output - we're forcing tool call so format is guaranteed
    tool_use = response.content[0]
    result = tool_use.input  # type: ignore

    classification = result["classification"]  # type: ignore

    if classification == "workflow":
        workflow_summary = result.get("workflow_summary", "")  # type: ignore
        workflow_steps_data = result.get("workflow_steps", [])  # type: ignore

        steps = []
        for step_data in workflow_steps_data:
            steps.append(WorkflowStep(description=step_data["description"]))  # type: ignore

        workflow = Workflow(summary=workflow_summary, steps=steps)
        return (DeterminerResponse.WORKFLOW, workflow)

    elif classification == "noise":
        return (DeterminerResponse.NOISE, None)

    else:  # unfinished
        return (DeterminerResponse.UNFINISHED, None)


def process_workflows_from_tab_sessions(
    tab_sessions: List[TabSessionSummary],
) -> List[Workflow]:
    workflows = []
    left = 0

    while left < len(tab_sessions):
        right = left + 1

        # Keep expanding window until we get a decisive answer
        while right <= len(tab_sessions):
            current_window = tab_sessions[left:right]
            response, workflow = ai_workflow_determiner(current_window)

            if response == DeterminerResponse.WORKFLOW:
                if workflow:
                    print(f"✅ Workflow found: {workflow.summary}")
                    workflows.append(workflow)
                left = right  # Move past this workflow
                break

            elif response == DeterminerResponse.NOISE:
                print(
                    f"🗑️  Noise detected, discarding window of {len(current_window)} sessions"
                )
                left = right  # Move past this noise
                break

            else:
                print(
                    f"⏳ Unfinished workflow, expanding window (currently {len(current_window)} sessions)"
                )
                right += 1

        # If we reach here without breaking, we've hit the end with an unfinished workflow
        if right > len(tab_sessions):
            break

    return workflows


def main():
    # Parse batch JSON from command line argument
    batch_json = sys.argv[1]

    batch_data = json.loads(batch_json)

    # Group events into tab sessions
    tab_group_summaries = group_events_into_tab_sessions(batch_data["events"])
    print("tab_group_summaries", tab_group_summaries)
    # Process tab sessions to identify workflows
    workflows = process_workflows_from_tab_sessions(tab_group_summaries)
    print("workflows", workflows)


if __name__ == "__main__":
    main()
