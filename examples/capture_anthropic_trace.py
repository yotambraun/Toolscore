#!/usr/bin/env python3
"""Example script to capture tool usage trace from Anthropic API.

This script demonstrates how to:
1. Call Anthropic's Claude API with tool use
2. Capture the tool usage trace
3. Save it in a format that Toolscore can evaluate

Requirements:
    pip install anthropic python-dotenv

Usage:
    python capture_anthropic_trace.py
"""

import json
import os
from pathlib import Path

try:
    from anthropic import Anthropic
    from dotenv import load_dotenv
except ImportError:
    print("Error: Required packages not installed.")
    print("Install them with: pip install anthropic python-dotenv")
    exit(1)

# Load environment variables from .env file
load_dotenv()

# Initialize Anthropic client
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    print("Error: ANTHROPIC_API_KEY not found in environment.")
    print("Create a .env file with: ANTHROPIC_API_KEY=your-key-here")
    exit(1)

client = Anthropic(api_key=api_key)

# Define tools available to Claude
tools = [
    {
        "name": "make_file",
        "description": "Create a new file with specified content",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name of the file to create"
                },
                "lines_of_text": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lines of text to write to the file"
                }
            },
            "required": ["filename", "lines_of_text"]
        }
    },
    {
        "name": "read_file",
        "description": "Read contents of a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name of the file to read"
                }
            },
            "required": ["filename"]
        }
    }
]

# Task prompt
task = "Create a file called poem.txt with a two-line poem (roses are red, violets are blue), then read it back to verify."

print(f"Task: {task}\n")
print("Calling Anthropic API...")

# Make API call with tool use
message = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    tools=tools,
    messages=[
        {"role": "user", "content": task}
    ]
)

print(f"Response received. Model: {message.model}")

# Extract tool calls from response
trace = []

# Add assistant message with tool use
if message.content:
    tool_uses = [block for block in message.content if block.type == "tool_use"]

    if tool_uses:
        trace.append({
            "role": "assistant",
            "content": message.content,
            "stop_reason": message.stop_reason
        })

        print(f"\nTool calls captured: {len(tool_uses)}")
        for tool_use in tool_uses:
            print(f"  - {tool_use.name}({json.dumps(tool_use.input)})")

        # Simulate tool results (in real scenario, you'd execute the tools)
        tool_results = []
        for tool_use in tool_uses:
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": json.dumps({"success": True, "result": "Tool executed"})
            })

        # Add tool results as user message
        trace.append({
            "role": "user",
            "content": tool_results
        })
    else:
        print("\nNo tool calls were made by the model.")
        trace.append({
            "role": "assistant",
            "content": message.content,
            "stop_reason": message.stop_reason
        })

# Save trace to file
output_file = Path(__file__).parent / "my_trace_anthropic.json"
with open(output_file, "w") as f:
    json.dump(trace, f, indent=2)

print(f"\n✓ Trace saved to: {output_file}")
print(f"\nTo evaluate this trace, run:")
print(f"  tool-scorer eval examples/gold_calls.json {output_file} --format anthropic")
