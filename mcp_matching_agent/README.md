# Recruitment Matching Agent — MCP + LangGraph

A submission-ready of implementation of a recruitment matching agent that replaces direct filesystem access with the **Model Context Protocol (MCP)**. LangGraph orchestrates the recruitment workflow while the MCP server owns filesystem operations and resume resources.

## Learning objectives covered

- Understand Model Context Protocol (MCP)
- Replace custom filesystem tools with an MCP server
- Use standardized MCP tool/resource interfaces
- Separate agent orchestration from data access
- Support local stdio and deployable Streamable HTTP transport

## Assignment mapping

### Part A — MCP Server (50%)

`filesystem_mcp_server.py` provides:

- `list_files()`
- `read_file()`
- `write_file()`
- `search_files()`
- `watch_directory()`
- `batch_process()`
- `server_status()`
- MCP resources: `filesystem://index`, `resume://{filename}`, `config://server`
- Configuration via `config/server_config.json`
- Path traversal protection
- File extension and size validation
- SDK-managed JSON-RPC 2.0 lifecycle, discovery, errors and transport

### Part B — Agent Refactoring (30%)

`matching_agent.py` contains no direct resume-file reads. It starts `filesystem_mcp_server.py` as an MCP subprocess and calls `batch_process()` through an MCP client.

LangGraph workflow:

```text
START
  ↓
Parse JD
  ↓
Extract Requirements
  ↓
Search Resumes (MCP)
  ↓
Rank Candidates
  ↓
Generate Report
  ↓
Human Feedback Loop
  ↓
END
```

The state tracks job requirements, conversation history, candidate data, shortlist, reasoning, report and feedback.

## Requirements

- Python 3.10+
- pip
- Windows, macOS or Linux

## Setup — Windows CMD

```cmd
cd mcp_matching_agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run the agent

```cmd
python matching_agent.py "React developer with 3+ years experience, JavaScript and Node.js"
```

You should see a ranked recruitment report using the sample resumes.

## Run the MCP server directly

STDIO is the default local MCP transport:

```cmd
python filesystem_mcp_server.py
```

The process waits for an MCP client. Do not type ordinary text into it.

For a deployable HTTP transport:

```cmd
set MCP_TRANSPORT=streamable-http
python filesystem_mcp_server.py
```

The MCP SDK exposes the Streamable HTTP endpoint according to its configured server transport.

## MCP Inspector

With the MCP CLI installed through the dependency:

```cmd
mcp dev filesystem_mcp_server.py
```

Use the Inspector to verify tool discovery, resource discovery and tool execution.

## Test

```cmd
pytest -q
```

## Interactive examples

The agent supports natural-language job descriptions such as:

```text
Find me candidates with React and 3+ years experience.
```

```text
Find candidates with Python, SQL and AWS.
```

The report explains matched skills, experience and the deterministic score calculation.

## Design notes

MCP distinguishes **tools** (actions) from **resources** (context/data). Therefore, filesystem operations are exposed as MCP tools, while resume contents and the filesystem index are MCP resources. This is the protocol-native implementation of the assignment's requirement to expose filesystem functionality through MCP.

JSON-RPC 2.0 framing, initialization, capability discovery, tool discovery, resource discovery and transport handling are delegated to the official MCP Python SDK instead of reimplementing the protocol manually. This avoids a fragile custom JSON-RPC layer and follows the MCP architecture.

## Security / production considerations

- Files are sandboxed to `data/resumes` by default.
- Path traversal is rejected.
- File extensions are allow-listed.
- Maximum file size is configurable.
- No API keys are committed.
- Logs go to stderr through Python logging so stdio protocol traffic remains clean.
- Streamable HTTP can be used for deployment; add authentication, TLS and an allow-listed host/origin policy at the deployment boundary.

## Multi-MCP bonus

The architecture intentionally isolates MCP access in `MCPFilesystemClient`. A second MCP client/server (for example, a web-search or database MCP server) can be added as another client and its results merged into the LangGraph state without changing filesystem code.

## Submission checklist

- [x] `filesystem_mcp_server.py`
- [x] MCP tools
- [x] MCP resources
- [x] `watch_directory()`
- [x] `batch_process()`
- [x] JSON-RPC 2.0 via MCP SDK
- [x] Resource discovery
- [x] Configuration management
- [x] Error handling
- [x] MCP client in agent
- [x] LangGraph workflow
- [x] Human feedback checkpoint
- [x] Sample resume dataset
- [x] Tests
- [x] README
- [x] `.gitignore`
