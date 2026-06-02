#!/usr/bin/env python3
"""
OBI Agent — CLI version.
Run directly in VSCode terminal. No server needed.

Usage:
    python agent/agent.py
    python agent/agent.py --uri serial:COM11,230400,8n1n
"""

import sys
import os
import json
import argparse
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()
import os
import anthropic

sys.path.insert(0, str(Path(__file__).parent))
from iio_tools import OBIBoard, find_obi_uri

MODEL = "claude-sonnet-4-6"

PORTKEY_BASE_URL = "https://api.portkey.ai"

TOOLS = [
    {
        "name": "obi_get_context",
        "description": "Get OBI board connection info and context attributes.",
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
        "description": "Write a value to a device attribute. Check *_available attrs first.",
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
            "properties": {"device": {"type": "string"}},
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
                "channel": {"type": "string"}
            },
            "required": ["device", "channel"]
        }
    },
    {
        "name": "obi_read_channel_attr",
        "description": "Read a single channel attribute.",
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
        "description": "Write a channel attribute.",
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
        "description": "Power off the OBI board via MAX20360 PWR_OFF_CMD.",
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

SYSTEM_PROMPT = """You are the OBI Agent — an AI assistant for the Analog Devices On-Body Injector development platform.

You have direct control over the OBI board connected via USB serial (tinyiiod on MAX32655/Zephyr RTOS).

Devices: device_info (state/versions), max20360 (PMIC/battery/LEDs/haptic), adxl367 (low-g accel), adxl371 (high-g accel), max22216 (DC motor), tmc5262 (stepper), max40109 (pressure), maxm86161 (optical PPG), ad5940 (impedance), ad7746 (capacitance), max30210-onboard (temp), max31331 (RTC), max98361 (audio), ad4130 (ADC), tmc5221, ds2477, maxq1065.

MAX20360 LED color mapping (do not guess — use this):
- led0 = RED
- led1 = GREEN
- led2 = BLUE

- Always check *_available attributes before writing
- For power-off: obi_power_off
- For state: obi_set_state
- Be concise and show results clearly"""


def run_tool(board: OBIBoard, name: str, args: dict) -> str:
    try:
        if name == "obi_get_context":
            result = board.get_context_info()
        elif name == "obi_list_devices":
            result = board.list_devices()
        elif name == "obi_list_device_attrs":
            result = board.list_device_attrs(args["device"])
        elif name == "obi_read_attr":
            val = board.read_device_attr(args["device"], args["attr"])
            result = {"value": val}
        elif name == "obi_write_attr":
            new_val = board.write_device_attr(args["device"], args["attr"], args["value"])
            result = {"written": args["value"], "readback": new_val}
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
    return json.dumps(result, indent=2)


def main():
    parser = argparse.ArgumentParser(description="OBI Agent CLI")
    parser.add_argument("--uri", default=None, help="IIO URI (auto-detected if omitted)")
    args_cli = parser.parse_args()

    print("OBI Agent — On-Body Injector Development Platform")
    print("=" * 50)

    print("Searching for OBI board...", end=" ", flush=True)
    try:
        board = OBIBoard(args_cli.uri)
        print(f"Found: {board.uri}")
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    client = anthropic.Anthropic(
        api_key=os.environ["PORTKEY_API_KEY"],
        base_url=PORTKEY_BASE_URL,
        default_headers={
            "x-portkey-api-key": os.environ["PORTKEY_API_KEY"],
            "x-portkey-virtual-key": os.environ["PORTKEY_VIRTUAL_KEY"],
        },
    )
    history = []

    print("\nType your question or command. Ctrl+C to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print("Exiting.")
            break

        history.append({"role": "user", "content": user_input})

        messages = history.copy()

        # Agentic loop
        while True:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            text_parts = []
            tool_uses = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)

            if not tool_uses:
                final_text = "".join(text_parts)
                print(f"\nAgent: {final_text}\n")
                history.append({"role": "assistant", "content": final_text})
                break

            # Show thinking text if any
            if text_parts:
                print(f"\nAgent: {''.join(text_parts)}")

            # Execute tools
            tool_results = []
            for tu in tool_uses:
                print(f"  [tool] {tu.name}({json.dumps(tu.input)})")
                result = run_tool(board, tu.name, tu.input)
                # Print a short preview
                preview = result[:200] + ("..." if len(result) > 200 else "")
                print(f"  [result] {preview}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result,
                })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    main()
