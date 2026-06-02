#!/usr/bin/env python3
"""
OBI Agent UI Server
FastAPI backend that:
  - serves the chat UI on http://localhost:8000
  - runs the Claude agent with OBI tools on POST /chat
  - streams responses via SSE on GET /chat/stream
"""

import sys
import os
import json
import asyncio
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
load_dotenv()
import os
import anthropic
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add agent dir to path so iio_tools is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))
from iio_tools import OBIBoard, find_obi_uri

app = FastAPI(title="OBI Agent")
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

PORTKEY_BASE_URL = "https://api.portkey.ai"
client = anthropic.Anthropic(
    api_key=os.environ["PORTKEY_API_KEY"],
    base_url=PORTKEY_BASE_URL,
    default_headers={
        "x-portkey-api-key": os.environ["PORTKEY_API_KEY"],
        "x-portkey-virtual-key": os.environ["PORTKEY_VIRTUAL_KEY"],
    },
)
MODEL = "claude-sonnet-4-6"

# ------------------------------------------------------------------ #
# Board singleton (connects once, reused across requests)
# ------------------------------------------------------------------ #
_board: OBIBoard | None = None

def get_board() -> OBIBoard:
    global _board
    if _board is None:
        _board = OBIBoard()
    return _board


# ------------------------------------------------------------------ #
# Tool definitions (same logic as MCP server, direct Python calls)
# ------------------------------------------------------------------ #

TOOLS = [
    {
        "name": "obi_get_context",
        "description": "Get OBI board connection info, firmware version, and context attributes.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "obi_list_devices",
        "description": "List all IIO devices on the OBI board.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "obi_list_device_attrs",
        "description": "List all attributes and current values for a device.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string", "description": "Device name (e.g. device_info, max20360, tmc5262)"}
            },
            "required": ["device"]
        }
    },
    {
        "name": "obi_read_attr",
        "description": "Read a single device attribute value.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "attr": {"type": "string"}
            },
            "required": ["device", "attr"]
        }
    },
    {
        "name": "obi_write_attr",
        "description": "Write a value to a device attribute. Check *_available attrs first for valid values.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "attr": {"type": "string"},
                "value": {"type": "string"}
            },
            "required": ["device", "attr", "value"]
        }
    },
    {
        "name": "obi_list_channels",
        "description": "List all channels for a device.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"}
            },
            "required": ["device"]
        }
    },
    {
        "name": "obi_list_channel_attrs",
        "description": "List all channel attributes and values.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "channel": {"type": "string", "description": "Channel id or name (e.g. fuel_gauge, charger, haptic)"}
            },
            "required": ["device", "channel"]
        }
    },
    {
        "name": "obi_read_channel_attr",
        "description": "Read a single channel attribute value.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "channel": {"type": "string"},
                "attr": {"type": "string"}
            },
            "required": ["device", "channel", "attr"]
        }
    },
    {
        "name": "obi_write_channel_attr",
        "description": "Write a value to a channel attribute.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "channel": {"type": "string"},
                "attr": {"type": "string"},
                "value": {"type": "string"}
            },
            "required": ["device", "channel", "attr", "value"]
        }
    },
    {
        "name": "obi_power_off",
        "description": "Power off the OBI board via MAX20360 PMIC PWR_OFF_CMD.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "obi_set_state",
        "description": "Set the device_info state (shipping, active, sleep).",
        "input_schema": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "shipping | active | sleep"}
            },
            "required": ["state"]
        }
    },
]


def run_tool(name: str, args: dict) -> str:
    board = get_board()
    try:
        if name == "obi_get_context":
            result = board.get_context_info()
        elif name == "obi_list_devices":
            result = board.list_devices()
        elif name == "obi_list_device_attrs":
            result = board.list_device_attrs(args["device"])
        elif name == "obi_read_attr":
            val = board.read_device_attr(args["device"], args["attr"])
            result = {"device": args["device"], "attr": args["attr"], "value": val}
        elif name == "obi_write_attr":
            new_val = board.write_device_attr(args["device"], args["attr"], args["value"])
            result = {"device": args["device"], "attr": args["attr"], "written": args["value"], "readback": new_val}
        elif name == "obi_list_channels":
            result = board.list_channels(args["device"])
        elif name == "obi_list_channel_attrs":
            result = board.list_channel_attrs(args["device"], args["channel"])
        elif name == "obi_read_channel_attr":
            val = board.read_channel_attr(args["device"], args["channel"], args["attr"])
            result = {"value": val}
        elif name == "obi_write_channel_attr":
            new_val = board.write_channel_attr(args["device"], args["channel"], args["attr"], args["value"])
            result = {"written": args["value"], "readback": new_val}
        elif name == "obi_power_off":
            board.write_device_attr("max20360", "pwr_cmd", "PWR_OFF_CMD")
            result = {"status": "PWR_OFF_CMD sent"}
        elif name == "obi_set_state":
            new_val = board.write_device_attr("device_info", "state", args["state"])
            result = {"state_written": args["state"], "readback": new_val}
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as e:
        result = {"error": str(e)}
    return json.dumps(result)


SYSTEM_PROMPT = """You are the OBI Agent — an AI assistant for the On-Body Injector development platform by Analog Devices.

You have direct control over the OBI board connected via USB serial. The board runs Zephyr RTOS with tinyiiod on a MAX32655 MCU.

Available devices on the board:
- device_info: system state (active/shipping/sleep), firmware versions, sensor status flags
- max20360: PMIC — battery charging, fuel gauge, LEDs, haptic motor, power commands
- adxl367: low-power accelerometer (drop detection)
- adxl371: high-g accelerometer (shock detection)
- max22216: DC motor / solenoid driver
- tmc5262: stepper motor driver
- max40109: pressure sensor AFE
- maxm86161: optical PPG sensor (SpO2/HR)
- ad5940: impedance/capacitance AFE
- ad7746: capacitance sensor
- max30210-onboard: temperature sensor
- max31331: RTC
- max98361: audio amplifier
- ad4130: ADC
- tmc5221: stepper driver (secondary)
- ds2477: SHA-3 authenticator
- maxq1065: secure microcontroller

Guidelines:
MAX20360 LED color mapping (do not guess — use this):
- led0 = RED
- led1 = GREEN
- led2 = BLUE

- Always check *_available attributes before writing to know valid values
- For power-off, use obi_power_off (sends PWR_OFF_CMD to MAX20360)
- For state changes (shipping/active/sleep), use obi_set_state
- Be concise and action-oriented — show results clearly
- If a device shows status=disabled, mention it when relevant
"""


# ------------------------------------------------------------------ #
# Agent loop with streaming
# ------------------------------------------------------------------ #

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


async def agent_stream(message: str, history: list[dict]) -> AsyncIterator[str]:
    messages = history + [{"role": "user", "content": message}]

    def send_event(event_type: str, data: dict) -> str:
        return f"data: {json.dumps({'type': event_type, **data})}\n\n"

    yield send_event("status", {"text": "Connecting to OBI board..."})

    # Check board connection
    try:
        board = get_board()
        yield send_event("status", {"text": f"Connected: {board.uri}"})
    except Exception as e:
        yield send_event("error", {"text": f"Board not found: {e}"})
        return

    # Agentic loop
    while True:
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        )

        # Collect text and tool uses from response
        text_parts = []
        tool_uses = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        if text_parts:
            yield send_event("text", {"text": "".join(text_parts)})

        # If no tool calls, we're done
        if response.stop_reason == "end_turn" or not tool_uses:
            yield send_event("done", {"text": "".join(text_parts)})
            break

        # Process tool calls
        tool_results = []
        for tool_use in tool_uses:
            yield send_event("tool_call", {"name": tool_use.name, "input": tool_use.input})
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda tu=tool_use: run_tool(tu.name, tu.input)
            )
            yield send_event("tool_result", {"name": tool_use.name, "result": result})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result,
            })

        # Append assistant + tool results to messages and continue
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    return StreamingResponse(
        agent_stream(req.message, req.history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/board/status")
async def board_status():
    try:
        board = get_board()
        return {"connected": True, "uri": board.uri}
    except Exception as e:
        return {"connected": False, "error": str(e)}


@app.get("/", response_class=HTMLResponse)
async def root():
    index = static_dir / "index.html"
    return HTMLResponse(content=index.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
