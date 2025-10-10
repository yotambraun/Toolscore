#!/usr/bin/env python3
"""Example script to capture tool usage trace from OpenAI API.

This script demonstrates how to:
1. Call OpenAI's function calling API
2. Capture the tool usage trace
3. Save it in a format that Toolscore can evaluate

Requirements:
    pip install openai python-dotenv

Usage:
    python capture_openai_trace.py
"""

import json
import os
from pathlib import Path

try:
    from openai import OpenAI
    from dotenv import load_dotenv
except ImportError:
    print("Error: Required packages not installed.")
    print("Install them with: pip install openai python-dotenv")
    exit(1)

# Load environment variables from .env file
load_dotenv()

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: OPENAI_API_KEY not found in environment.")
    print("Create a .env file with: OPENAI_API_KEY=your-key-here")
    exit(1)

client = OpenAI(api_key=api_key)

# Define tools (functions) available to the model
tools = [
    {
        "type": "function",
        "function": {
            "name": "make_file",
            "description": "Create a new file with specified content",
            "parameters": {
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
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read contents of a file",
            "parameters": {
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
    }
]

# Task prompt
task = "Create a file called poem.txt with a two-line poem (roses are red, violets are blue), then read it back to verify."

print(f"Task: {task}\n")
print("Calling OpenAI API...")

# Make API call with function calling
messages = [{"role": "user", "content": task}]

response = client.chat.completions.create(
    model="gpt-4",
    messages=messages,
    tools=tools,
    tool_choice="auto"
)

print(f"Response received. Model: {response.model}")

# Extract tool calls from response
trace = []

# Add assistant message with tool calls
assistant_message = response.choices[0].message
if assistant_message.tool_calls:
    trace.append({
        "role": "assistant",
        "content": assistant_message.content,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments
                }
            }
            for tc in assistant_message.tool_calls
        ]
    })

    print(f"\nTool calls captured: {len(assistant_message.tool_calls)}")
    for tc in assistant_message.tool_calls:
        print(f"  - {tc.function.name}({tc.function.arguments})")

    # Simulate tool results (in real scenario, you'd execute the tools)
    for tc in assistant_message.tool_calls:
        trace.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "name": tc.function.name,
            "content": json.dumps({"success": True, "result": "Tool executed"})
        })
else:
    print("\nNo tool calls were made by the model.")
    trace.append({
        "role": "assistant",
        "content": assistant_message.content
    })

# Save trace to file
output_file = Path(__file__).parent / "my_trace_openai.json"
with open(output_file, "w") as f:
    json.dump(trace, f, indent=2)

print(f"\n✓ Trace saved to: {output_file}")
print(f"\nTo evaluate this trace, run:")
print(f"  tool-scorer eval examples/gold_calls.json {output_file} --format openai")
