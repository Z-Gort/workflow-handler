"""Module for grouping browser events into tab sessions."""

from typing import List, Dict, Optional
from .shared_types import TabSessionSummary, get_anthropic_client


def get_base_url(url):
    if not url:
        return None

    if "://" in url:
        return url.split("://")[0] + "://" + url.split("://")[1].split("/")[0]
    return url.split("/")[0]


def summarize_markdowns(markdowns: List[str]) -> str:
    """Create a concise summary of markdown content from multiple pages."""
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
        if response.content and len(response.content) > 0:
            content_block = response.content[0]
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
    """
    Group browser events into tab sessions based on URL changes and tab switches.

    Returns:
        List of TabSessionSummary objects representing grouped sessions
    """
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

    return tab_groups
