# -*- coding: utf-8 -*-
"""
Centralized reusable 'tool' functions for the agent.
Internal helper functions start with an underscore `_` and are not exposed to the agent.
"""
from typing import Dict
import requests
import sys
import threading
import time
import re
# --- Add this import to the top of your tools.py file ---
from duckduckgo_search import DDGS


# --- Replace your existing web_search function with this one ---

def web_search(query: str, num_results: int = 4) -> str:
    """
    Performs a web search using DuckDuckGo and returns the top results.
    Use this to find current information, facts, or answer general questions.
    """
    if not query:
        return "Error: A search query must be provided."

    print(f"Performing DuckDuckGo search for: '{query}'")
    
    try:
        # The DDGS context manager handles the network session.
        with DDGS() as ddgs:
            # ddgs.text() returns a generator of search results.
            results = list(ddgs.text(query, max_results=num_results))

        if not results:
            return f"No search results found for '{query}'."

        # Format the results into a clean, readable string for the agent.
        formatted_results = []
        for i, result in enumerate(results, 1):
            # The result object is a dictionary with 'title', 'body', and 'href'.
            formatted_results.append(
                f"Result {i}:\n"
                f"Title: {result['title']}\n"
                f"Snippet: {result['body']}\n"
                f"Source: {result['href']}"
            )
        
        return "\n\n".join(formatted_results)

    except Exception as e:
        return f"Error: An unexpected error occurred during the web search: {e}"
# --- Configuration ---
# IMPORTANT: Make sure this IP address is correct for your ESP8266
ESP8266_IP = "192.168.31.181"
BASE_URL = f"http://{ESP8266_IP}"
# ---------------------

# --- Internal Helper Functions (Not visible to the agent) ---

def _get_fan_status() -> str:
    """
    Internal function to get the fan's current state from its web UI.
    Returns 'ON', 'OFF', or 'UNKNOWN'.
    """
    try:
        response = requests.get(BASE_URL + "/", timeout=5)
        response.raise_for_status()
        match = re.search(r"Current State: <b>(ON|OFF)</b>", response.text)
        if match:
            return match.group(1)
        return "UNKNOWN"
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to fan controller: {e}", file=sys.stderr)
        return "UNKNOWN"

def _send_fan_command(endpoint: str) -> bool:
    """
    Internal function to send a POST command to a specific endpoint.
    Returns True on success, False on failure.
    """
    try:
        requests.post(f"{BASE_URL}/{endpoint}", timeout=3)
        return True
    except requests.exceptions.RequestException as e:
        return True

# --- Public Tools (Visible to the agent) ---
def set_fan_state(target_state: str) -> str:
    """
    Sets the fan to a desired state ('on' or 'off').
    It automatically checks the current state and only acts if a change is needed.
    """
    if target_state.lower() not in ['on', 'off']:
        return "Error: Invalid target state. Please use 'on' or 'off'."

    current_status = _get_fan_status()
    if current_status == "UNKNOWN":
        return "Could not determine the fan's current state. Cannot proceed."

    if target_state.lower() == current_status.lower():
        return f"No action taken. The fan is already {current_status}."

    if _send_fan_command("toggle"):
        new_state = "ON" if target_state.lower() == 'on' else "OFF"
        return f"Success. The fan has been turned {new_state}."
    else:
        return "Action failed. Could not send the command to the fan controller."

def add_power_fan() -> str:
    """
    Increases the power of the fan. Will fail if the fan is currently off.
    """
    if _get_fan_status() != "ON":
        return "Action failed. Cannot adjust power because the fan is off."
        
    if _send_fan_command("send_add_power"):
        return "Increased fan power."
    else:
        return "Action failed. Could not send the command to the fan controller."

def lower_power_fan() -> str:
    """
    Decreases the power of the fan. Will fail if the fan is currently off.
    """
    if _get_fan_status() != "ON":
        return "Action failed. Cannot adjust power because the fan is off."

    if _send_fan_command("send_lower_power"):
        return "Decreased fan power."
    else:
        return "Action failed. Could not send the command to the fan controller."

def timer(seconds: float, message: str = "Time is up") -> Dict[str, object]:
    """
    Start a background timer that waits `seconds` then calls `speaker.speak(message)`.
    """
    def _worker():
        try:
            time.sleep(seconds)
            from speaker import speak
            speak(message)
        except Exception as e:
            print(f"timer worker exception: {e}", file=sys.stderr)

    thread_name = f"timer-{int(time.time())}"
    t = threading.Thread(target=_worker, daemon=True, name=thread_name)
    t.start()
    return {"status": "started", "seconds": seconds, "message": message, "thread_name": t.name}

