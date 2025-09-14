"""Main orchestrator for workflow processing from browser events."""

import sys
import json
from tab_sessions import group_events_into_tab_sessions
from workflow_processing import process_workflows_from_tab_sessions
from workflow_analysis import analyze_and_update_workflows, save_workflows_to_database


def main():
    batch_json = sys.argv[1]
    batch_data = json.loads(batch_json)

    # Step 1: Group events into tab sessions
    tab_group_summaries = group_events_into_tab_sessions(batch_data["events"])
    print("tab_group_summaries", tab_group_summaries)

    # Step 2: Process tab sessions to identify workflows
    workflows = process_workflows_from_tab_sessions(tab_group_summaries)
    print("workflows", workflows)

    # Step 3: Analyze workflows for tool usage and filter
    final_workflows = analyze_and_update_workflows(workflows)
    print("final_workflows", final_workflows)

    # Save to database
    save_workflows_to_database(final_workflows)
    print("✅ Processing complete!")


if __name__ == "__main__":
    main()
