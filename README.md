# OBI Agent

AI assistant for the On-Body Injector development platform. Talk to the board in plain English.

## What it does

- Natural language control of all 17 IIO devices on the OBI board
- Auto-detects the board on any COM port (no config needed)
- Two interfaces: CLI in terminal, or web chat UI at localhost:8000

**Examples:**
```
"what's the battery level?"
"change state to shipping"
"turn on the red LED"
"move the stepper motor right"
"turn off the board"
```

## Setup

**1. Install dependencies**
```
pip install -r requirements_agent.txt
```

**2. Create a `.env` file** in the project root:
```
PORTKEY_API_KEY=your_portkey_api_key
PORTKEY_VIRTUAL_KEY=your_portkey_virtual_key
```

**3. Plug in the OBI board** via USB. The agent auto-detects the COM port.

## Run

**CLI (terminal):**
```
python agent/agent.py
```

**Web UI (opens at http://localhost:8000):**
```
python ui/server.py
```

## Project structure

```
agent/
  agent.py        ← CLI agent
  mcp_server.py   ← MCP server (for Claude Code VSCode extension)
  iio_tools.py    ← OBI board interface via pylibiio
ui/
  server.py       ← FastAPI backend
  static/
    index.html    ← Web chat UI
requirements_agent.txt
.mcp.json         ← MCP config for Claude Code
```

## Using with Claude Code (VSCode)

The `.mcp.json` is already configured. With the board plugged in, Claude Code will have direct OBI tools available — no separate server needed.
