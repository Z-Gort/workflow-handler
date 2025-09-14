### 1. Frontend Web Application

- **Technology**: Next.js with TypeScript
- **Database**: PostgreSQL with Drizzle ORM
- **API**: RESTful endpoints for browser interaction ingestion
- **Location**: `src/app/`, `src/server/db/`

### 2. Python Workflow Processing Pipeline

- **Location**: `src/server/python/`
- **Main File**: `group_flows.py`
- **Dependencies**: Claude AI API, psycopg2, anthropic

#### Processing Stages:

1. **Event Grouping** → **Tab Session Summaries**
   - Groups browser events by URL and tab context
   - Creates `TabSessionSummary` objects with viewport and activity summaries
   - Uses AI to summarize page content and user behavior

2. **Workflow Detection** → **AI Classification**
   - Applies expanding window algorithm to detect workflow boundaries
   - AI classifies sequences as: `WORKFLOW`, `NOISE`, or `UNFINISHED`
   - Strict criteria: must show purposeful progression toward actionable goals

3. **Tool Analysis** → **Step Classification**
   - Scans workflow steps for platform keywords (Slack, Jira, Notion, etc.)
   - Uses AI to map specific steps to available tools from `tools-dump/`
   - Classifies steps as `tool` or `browser_context`

4. **Deduplication** → **Database Storage**
   - Compares tool sets to identify duplicate workflows
   - Stores unique workflows in PostgreSQL
   - Maintains workflow metadata and step sequences

### 3. Database Schema

```sql
-- PostgreSQL table: workflow-handler_workflow
CREATE TABLE "workflow-handler_workflow" (
  id SERIAL PRIMARY KEY,
  summary TEXT NOT NULL,
  steps JSONB NOT NULL,  -- Array of workflow steps with tools
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 4. Tool Integration System

- **Tool Definitions**: `src/server/python/tools-dump/`
- **Supported Platforms**: Slack, Jira, Linear, Notion, HubSpot, Google Workspace, GitHub, Discord, Microsoft Office
- **Format**: JSON tool definitions with names, descriptions, and input schemas

## Data Flow

1. **Browser Events** → Captured by browser extension
2. **API Ingestion** → `/api/interactions` endpoint receives event batches
3. **Python Processing** → `group_flows.py` processes events through pipeline
4. **AI Analysis** → Claude AI models classify workflows and map tools
5. **Database Storage** → Curated workflows stored with deduplication
6. **Automation Ready** → Workflows available for automation platforms