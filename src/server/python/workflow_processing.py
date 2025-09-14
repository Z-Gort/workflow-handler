"""Module for processing tab sessions to identify workflows."""

from typing import List, Tuple, Optional
from .shared_types import (
    TabSessionSummary,
    Workflow,
    WorkflowStep,
    DeterminerResponse,
    get_anthropic_client,
)


def is_workflow(
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

    else:
        return (DeterminerResponse.UNFINISHED, None)


def process_workflows_from_tab_sessions(
    tab_sessions: List[TabSessionSummary],
) -> List[Workflow]:
    """
    Process tab sessions to identify complete workflows using sliding window approach.

    Args:
        tab_sessions: List of tab session summaries to analyze

    Returns:
        List of identified workflows
    """
    workflows = []
    left = 0

    while left < len(tab_sessions):
        right = left + 1

        while right <= len(tab_sessions):
            current_window = tab_sessions[left:right]
            response, workflow = is_workflow(current_window)

            if response == DeterminerResponse.WORKFLOW:
                if workflow:
                    workflows.append(workflow)
                left = right  # Move past this workflow
                break

            elif response == DeterminerResponse.NOISE:
                left = right  # Move past this noise
                break

            else:
                right += 1

        # If we reach here without breaking, we've hit the end with an unfinished workflow
        if right > len(tab_sessions):
            break

    return workflows
