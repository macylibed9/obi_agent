#!/usr/bin/env python3
"""
OBI MCP Server — exposes IIO board control as MCP tools over stdio.
Claude calls these tools when you chat with the agent.

Usage:
    python agent/mcp_server.py
    python agent/mcp_server.py --uri serial:COM11,230400,8n1n
"""

import sys
import json
import argparse
import traceback
from typing import Any

# Lazy-init board so server starts even if board is unplugged
_board = None
_board_uri = None


def get_board():
    global _board
    if _board is None:
        from iio_tools import OBIBoard
        _board = OBIBoard(_board_uri)
    return _board


# ------------------------------------------------------------------ #
# MCP protocol helpers
# ------------------------------------------------------------------ #

def send(msg: dict):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def ok(request_id, content: Any):
    send({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [{"type": "text", "text": json.dumps(content, indent=2)}]
        }
    })


def err(request_id, message: str, code: int = -32000):
    send({
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message}
    })


# ------------------------------------------------------------------ #
# Tool definitions
# ------------------------------------------------------------------ #

TOOLS = [
    {
        "name": "obi_get_context",
        "description": "Get OBI board connection info and context attributes (URI, firmware version, hw_name, etc).",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "obi_list_devices",
        "description": "List all IIO devices on the OBI board (device_info, max20360, adxl367, tmc5262, etc).",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "obi_list_device_attrs",
        "description": "List all attributes and their current values for a specific device.",
        "inputSchema": {
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
        "inputSchema": {
            "type": "object",
            "properties": {
                "device": {"type": "string", "description": "Device name"},
                "attr": {"type": "string", "description": "Attribute name"}
            },
            "required": ["device", "attr"]
        }
    },
    {
        "name": "obi_write_attr",
        "description": "Write a value to a device attribute. Always check *_available attributes first to know valid values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device": {"type": "string", "description": "Device name"},
                "attr": {"type": "string", "description": "Attribute name"},
                "value": {"type": "string", "description": "Value to write"}
            },
            "required": ["device", "attr", "value"]
        }
    },
    {
        "name": "obi_list_channels",
        "description": "List all channels for a device (e.g. charger, fuel_gauge, haptic channels on max20360).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device": {"type": "string", "description": "Device name"}
            },
            "required": ["device"]
        }
    },
    {
        "name": "obi_list_channel_attrs",
        "description": "List all attributes and values for a specific channel on a device.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device": {"type": "string", "description": "Device name"},
                "channel": {"type": "string", "description": "Channel id or name (e.g. fuel_gauge, charger, haptic)"}
            },
            "required": ["device", "channel"]
        }
    },
    {
        "name": "obi_read_channel_attr",
        "description": "Read a single channel attribute value.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device": {"type": "string", "description": "Device name"},
                "channel": {"type": "string", "description": "Channel id or name"},
                "attr": {"type": "string", "description": "Attribute name"}
            },
            "required": ["device", "channel", "attr"]
        }
    },
    {
        "name": "obi_write_channel_attr",
        "description": "Write a value to a channel attribute.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device": {"type": "string", "description": "Device name"},
                "channel": {"type": "string", "description": "Channel id or name"},
                "attr": {"type": "string", "description": "Attribute name"},
                "value": {"type": "string", "description": "Value to write"}
            },
            "required": ["device", "channel", "attr", "value"]
        }
    },
    {
        "name": "obi_power_off",
        "description": "Send PWR_OFF_CMD to the MAX20360 PMIC to power off the OBI board.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "obi_set_state",
        "description": "Set the device_info state (shipping, active, sleep).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "One of: shipping, active, sleep"}
            },
            "required": ["state"]
        }
    },
]


# ------------------------------------------------------------------ #
# Tool dispatch
# ------------------------------------------------------------------ #

def dispatch(name: str, args: dict) -> Any:
    board = get_board()

    if name == "obi_get_context":
        return board.get_context_info()

    elif name == "obi_list_devices":
        return board.list_devices()

    elif name == "obi_list_device_attrs":
        return board.list_device_attrs(args["device"])

    elif name == "obi_read_attr":
        value = board.read_device_attr(args["device"], args["attr"])
        return {"device": args["device"], "attr": args["attr"], "value": value}

    elif name == "obi_write_attr":
        new_val = board.write_device_attr(args["device"], args["attr"], args["value"])
        return {"device": args["device"], "attr": args["attr"], "written": args["value"], "readback": new_val}

    elif name == "obi_list_channels":
        return board.list_channels(args["device"])

    elif name == "obi_list_channel_attrs":
        return board.list_channel_attrs(args["device"], args["channel"])

    elif name == "obi_read_channel_attr":
        value = board.read_channel_attr(args["device"], args["channel"], args["attr"])
        return {"device": args["device"], "channel": args["channel"], "attr": args["attr"], "value": value}

    elif name == "obi_write_channel_attr":
        new_val = board.write_channel_attr(args["device"], args["channel"], args["attr"], args["value"])
        return {"device": args["device"], "channel": args["channel"], "attr": args["attr"], "written": args["value"], "readback": new_val}

    elif name == "obi_power_off":
        board.write_device_attr("max20360", "pwr_cmd", "PWR_OFF_CMD")
        return {"status": "PWR_OFF_CMD sent to MAX20360"}

    elif name == "obi_set_state":
        state = args["state"]
        new_val = board.write_device_attr("device_info", "state", state)
        return {"state_written": state, "readback": new_val}

    else:
        raise ValueError(f"Unknown tool: {name}")


# ------------------------------------------------------------------ #
# Main loop
# ------------------------------------------------------------------ #

def handle(request: dict):
    req_id = request.get("id")
    method = request.get("method", "")

    if method == "initialize":
        send({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "obi-mcp-server", "version": "1.0.0"}
            }
        })

    elif method == "tools/list":
        send({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS}
        })

    elif method == "tools/call":
        tool_name = request["params"]["name"]
        tool_args = request["params"].get("arguments", {})
        try:
            result = dispatch(tool_name, tool_args)
            ok(req_id, result)
        except Exception as e:
            err(req_id, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

    elif method == "notifications/initialized":
        pass  # no response needed

    else:
        err(req_id, f"Method not found: {method}", code=-32601)


def main():
    global _board_uri
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default=None, help="IIO URI (auto-detected if omitted)")
    args = parser.parse_args()
    _board_uri = args.uri

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            handle(request)
        except json.JSONDecodeError as e:
            err(None, f"JSON parse error: {e}")
        except Exception as e:
            err(None, f"Unhandled error: {e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
