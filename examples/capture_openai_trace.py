#!/usr/bin/env python3
"""Example script to capture tool usage trace from OpenAI API.

This script demonstrates how to:
1. Call OpenAI's Responses API with function tools
2. Capture the tool usage trace
3. Save it in a format that Toolscore can evaluate (the response itself)

Requirements:
    pip install openai python-dotenv

Usage:
    python capture_openai_trace.py
"""

import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    from openai import OpenAI
except ImportError:
    print("Error: Required packages not installed.")
    print("Install them with: pip install openai python-dotenv")
    exit(1)

from toolscore import from_openai_responses

# Load environment variables from .env file
load_dotenv()

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: OPENAI_API_KEY not found in environment.")
    print("Create a .env file with: OPENAI_API_KEY=your-key-here")
    exit(1)

client = OpenAI(api_key=api_key)

# Define tools (functions) available to the model (Responses API format)
tools = [
    {
        "type": "function",
        "name": "make_file",
        "description": "Create a new file with specified content",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Name of the file to create"},
                "lines_of_text": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lines of text to write to the file",
                },
            },
            "required": ["filename", "lines_of_text"],
        },
    },
    {
        "type": "function",
        "name": "read_file",
        "description": "Read contents of a file",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Name of the file to read"}
            },
            "required": ["filename"],
        },
    },
]

# Task prompt
task = "Create a file called poem.txt with a two-line poem (roses are red, violets are blue), then read it back to verify."

print(f"Task: {task}\n")
print("Calling the OpenAI Responses API...")

response = client.responses.create(model="gpt-6-luna", input=task, tools=tools)

print(f"Response received. Model: {response.model}")

calls = from_openai_responses(response)
print(f"\nTool calls captured: {len(calls)}")
for call in calls:
    print(f"  - {call['tool']}({json.dumps(call['args'])})")

# Save the response as it is: Toolscore detects the Responses API format.
output_file = Path(__file__).parent / "my_trace_openai.json"
with output_file.open("w") as f:
    json.dump(response.model_dump(mode="json"), f, indent=2)

print(f"\n✓ Trace saved to: {output_file}")
print("\nTo evaluate this trace, run:")
print(f"  toolscore eval examples/gold_calls.json {output_file}")
print("\nOr use the Python API directly (no file needed):")
print("  from toolscore import evaluate")
print("  result = evaluate(expected=[...], actual=response)")
