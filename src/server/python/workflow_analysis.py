"""Module for analyzing workflows for tool usage and filtering."""

import os
import json
import glob
import psycopg2
from typing import List, Dict, Optional, Tuple, Set
from .shared_types import Workflow, WorkflowStep, get_anthropic_client


def load_available_tools() -> Dict[str, List[Dict]]:
    """
    Load available tools from the tools-dump directory.
    Returns dict mapping platform names to list of tool definitions.
    """
    tools_by_platform = {}
    tools_dir = os.path.join(os.path.dirname(__file__), "tools-dump")

    for file_path in glob.glob(os.path.join(tools_dir, "*.txt")):
        platform = os.path.basename(file_path).replace(".txt", "")
        tools = []

        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        tool_data = json.loads(line)
                        tools.append(tool_data)
                    except json.JSONDecodeError:
                        continue

        tools_by_platform[platform] = tools

    return tools_by_platform


def analyze_workflow_step_for_tools(
    step: WorkflowStep, available_tools: Dict[str, List[Dict]]
) -> Tuple[bool, Optional[str]]:
    """
    Analyze a workflow step to determine if it uses tools and which specific tool.

    Returns:
        Tuple of (uses_tool: bool, tool_name: Optional[str])
    """
    # Keywords that indicate tool usage
    platform_keywords = {
        "slack": "slack",
        "jira": "jira",
        "linear": "linear",
        "notion": "notion",
        "hubspot": "hubspot",
        "google sheets": "google_sheets",
        "google docs": "google_docs",
        "google drive": "google_drive",
        "google calendar": "google_calendar",
        "gmail": "gmail",
        "github": "github",
        "discord": "discord",
        "reddit": "reddit",
        "microsoft outlook": "microsoft_outlook",
        "microsoft teams": "microsoft_teams",
    }

    step_text = step.description.lower()

    # Check if any platform keywords are mentioned
    detected_platforms = []
    for keyword, platform in platform_keywords.items():
        if keyword in step_text and platform in available_tools:
            detected_platforms.append(platform)

    if not detected_platforms:
        return False, None

    client = get_anthropic_client()

    # Build tool options for detected platforms
    tool_options = []
    for platform in detected_platforms:
        for tool in available_tools[platform]:
            tool_info = f"- {tool['name']}: {tool['description']}"
            tool_options.append(tool_info)

    tools_text = "\n".join(tool_options)

    prompt = f"""Analyze this workflow step to determine which specific tool it uses.

WORKFLOW STEP:
{step.description}

AVAILABLE TOOLS:
{tools_text}

Determine if this step uses any of the available tools. Look for action words that match tool capabilities:
- Creating, updating, sending, posting → specific tool actions
- Just mentioning or viewing a platform → no tool needed

Be strict: only identify a tool if the step clearly performs an ACTION that requires the tool."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
            tools=[
                {
                    "name": "identify_tool",
                    "description": "Identify if and which tool the workflow step uses",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "uses_tool": {
                                "type": "boolean",
                                "description": "Whether this step uses any of the available tools",
                            },
                            "tool_name": {
                                "type": "string",
                                "description": "The exact name of the tool used, or empty string if no tool",
                            },
                        },
                        "required": ["uses_tool", "tool_name"],
                    },
                }
            ],
            tool_choice={"type": "tool", "name": "identify_tool"},
        )

        tool_use = response.content[0]
        result = tool_use.input  # type: ignore

        uses_tool = result["uses_tool"]  # type: ignore
        tool_name = result["tool_name"]  # type: ignore

        if uses_tool and tool_name:
            return True, tool_name
        else:
            return False, None

    except Exception as e:
        print(f"❌ Tool analysis error: {e}")
        return False, None


def extract_workflow_tools(workflow: Workflow) -> Set[str]:
    """Extract all tools used in a workflow."""
    tools = set()
    for step in workflow.steps:
        if step.tools:
            tools.update(step.tools)
    return tools


def get_database_connection():
    """Get database connection using the provided credentials."""
    return psycopg2.connect(
        "postgresql://postgres:BEcPVpp7PEtP8QDR@localhost:5432/workflow-handler"
    )


def filter_workflow(workflow: Workflow, conn) -> bool:
    """
    Check if workflow should be filtered out based on duplicate tool usage.

    Returns:
        True if workflow should be filtered out, False if it should be kept
    """
    current_tools = extract_workflow_tools(workflow)
    cursor = conn.cursor()
    try:
        # Get all existing workflows
        cursor.execute('SELECT steps FROM "workflow-handler_workflow"')
        existing_workflows = cursor.fetchall()

        for (existing_steps,) in existing_workflows:
            # Extract tools from existing workflow
            existing_tools = set()
            if existing_steps:
                for step in existing_steps:
                    if step.get("tools"):
                        existing_tools.update(step["tools"])

            if current_tools == existing_tools:
                return True

        return False

    except Exception as e:
        print(f"❌ Error checking for duplicates: {e}")
        return False
    finally:
        cursor.close()


def format_workflows_for_database(workflows: List[Workflow]) -> List[Dict]:
    """Format workflows for database insertion."""
    formatted_workflows = []

    for workflow in workflows:
        # Convert steps to JSON-serializable format
        steps_data = []
        for step in workflow.steps:
            step_dict = {
                "description": step.description,
                "type": step.type,
                "tools": step.tools,
            }
            steps_data.append(step_dict)

        formatted_workflow = {"summary": workflow.summary, "steps": steps_data}
        formatted_workflows.append(formatted_workflow)

    return formatted_workflows


def save_workflows_to_database(workflows: List[Workflow]) -> None:
    """Save workflows to database, filtering out duplicates."""
    if not workflows:
        return

    conn = None
    cursor = None
    try:
        conn = get_database_connection()
        cursor = conn.cursor()

        for workflow in workflows:
            if filter_workflow(workflow, conn):
                continue

            formatted_data = format_workflows_for_database([workflow])[0]
            cursor.execute(
                """
                INSERT INTO "workflow-handler_workflow" (summary, steps)
                VALUES (%s, %s)
                """,
                (formatted_data["summary"], json.dumps(formatted_data["steps"])),
            )
        conn.commit()

    except Exception as e:
        print(f"❌ Database error: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def analyze_and_update_workflows(workflows: List[Workflow]) -> List[Workflow]:
    """
    Analyze workflows to identify tool usage and update step information.
    Filter out workflows that have no tool steps.

    Args:
        workflows: List of workflows to analyze

    Returns:
        List of workflows that contain at least one tool step
    """
    available_tools = load_available_tools()
    updated_workflows = []

    for workflow in workflows:
        has_tool_step = False

        for step in workflow.steps:
            uses_tool, tool_name = analyze_workflow_step_for_tools(
                step, available_tools
            )

            if uses_tool:
                step.type = "tool"
                step.tools = [tool_name] if tool_name else None
                has_tool_step = True
            else:
                step.type = "browser_context"

        if has_tool_step:
            updated_workflows.append(workflow)

    return updated_workflows
