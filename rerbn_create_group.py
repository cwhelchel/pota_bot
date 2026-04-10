#!/usr/bin/env python3
"""
Create a Vail ReRBN Callsign Group from a file.

Usage:
    python create_group.py --name my-group --file callsigns.txt \
        --creator-name "Brett KE9BOS" --creator-email "ke9bos@example.com"

Callsign file format (one callsign per line, blank lines and # comments ignored):
    W1AW
    K1TTT
    # This is a comment
    N3LLO

Notes:
    This file is AI generated and I expect there may be issues. But it created
    my group and saved the edit key as expected.

    This is just a utility file and not used by the main bot code at all.
    - Cainan
"""

import argparse
import json
import sys
import requests


BASE_URL = "https://vailrerbn.com/api/v1"


def load_callsigns(filepath: str) -> list[str]:
    """Read callsigns from a file, one per line. Ignores blank lines and comments."""
    callsigns = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            callsigns.append(line.upper())

    if not callsigns:
        print(f"ERROR: No callsigns found in '{filepath}'.", file=sys.stderr)
        sys.exit(1)

    if len(callsigns) > 500:
        print(f"ERROR: Too many callsigns ({len(callsigns)}). Maximum is 500.", file=sys.stderr)
        sys.exit(1)

    return callsigns


def create_group(
    name: str,
    callsigns: list[str],
    creator_name: str,
    creator_email: str,
    description: str = "",
) -> dict:
    """POST /groups to create a new callsign group."""
    payload = {
        "name": name,
        "callsigns": callsigns,
        "creator_name": creator_name,
        "creator_email": creator_email,
    }
    if description:
        payload["description"] = description

    response = requests.post(
        f"{BASE_URL}/groups",
        headers={"Content-Type": "application/json"},
        json=payload,
    )

    if response.status_code == 201:
        return response.json()

    # Handle known error codes
    error_messages = {
        400: "Bad request — check that your group name follows the naming rules and all fields are valid.",
        409: f"A group named '{name}' already exists. Choose a different name.",
        429: "The global group limit (1000) has been reached. Cannot create new groups right now.",
    }
    msg = error_messages.get(response.status_code, f"Unexpected error ({response.status_code})")
    try:
        detail = response.json()
        msg += f"\nServer response: {json.dumps(detail, indent=2)}"
    except Exception:
        msg += f"\nRaw response: {response.text}"

    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Create a Vail ReRBN callsign group from a file."
    )
    parser.add_argument(
        "--name", required=True,
        help="Group name: 3-50 chars, lowercase letters/numbers/hyphens (e.g. my-contest-team)",
    )
    parser.add_argument(
        "--file", required=True,
        help="Path to a text file with one callsign per line",
    )
    parser.add_argument(
        "--creator-name", required=True,
        help="Your name or callsign (visible publicly, max 100 chars)",
    )
    parser.add_argument(
        "--creator-email", required=True,
        help="Your email address (visible on group page)",
    )
    parser.add_argument(
        "--description", default="",
        help="Optional group description (max 200 chars)",
    )

    args = parser.parse_args()

    # Load callsigns from file
    print(f"Reading callsigns from '{args.file}'...")
    callsigns = load_callsigns(args.file)
    print(f"  Loaded {len(callsigns)} callsign(s): {', '.join(callsigns[:10])}"
          + (" ..." if len(callsigns) > 10 else ""))  # NOQA

    # Create the group
    print(f"\nCreating group '{args.name}'...")
    result = create_group(
        name=args.name,
        callsigns=callsigns,
        creator_name=args.creator_name,
        creator_email=args.creator_email,
        description=args.description,
    )

    group = result["group"]
    edit_key = result["edit_key"]

    print("\n✅ Group created successfully!")
    print(f"  Name:        {group['name']}")
    print(f"  Callsigns:   {group['callsign_count']}")
    print(f"  Created:     {group['created_at']}")
    if group.get("description"):
        print(f"  Description: {group['description']}")
    print(f"  URL:         https://vailrerbn.com/groups/{group['name']}")

    print("\n⚠️  SAVE YOUR EDIT KEY — shown only once:")
    print(f"  {edit_key}")
    print("\n  You will need this key to update or delete the group.")
    print("  If lost, contact ke9bos@pigletradio.org for recovery.")

    # Save edit key to a local file for safety
    key_file = f"{args.name}.editkey"
    with open(key_file, "w") as f:
        f.write(f"Group: {group['name']}\n")
        f.write(f"Edit key: {edit_key}\n")
    print(f"\n  Edit key also saved to: {key_file}")


if __name__ == "__main__":
    main()
