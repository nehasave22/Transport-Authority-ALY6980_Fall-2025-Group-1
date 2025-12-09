#!/usr/bin/env python3
"""
MCP Server for MBTA Transit Information
Exposes MBTA capabilities to Claude via Model Context Protocol
"""

import asyncio
import os
from typing import Any
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp import types
import requests
import json

# MBTA API Configuration
MBTA_API_KEY = os.getenv("MBTA_API_KEY", "")
MBTA_BASE_URL = "https://api-v3.mbta.com"

# Load local data
def load_json(filename):
    try:
        with open(f"data/{filename}", "r") as f:
            return json.load(f)
    except:
        return {}

ALIASES = load_json("aliases.json")
TRANSFERS = load_json("transfers.json")

# Initialize MCP Server
server = Server("mbta-transit-mcp")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List all available MBTA tools that Claude can use.
    """
    return [
        types.Tool(
            name="get_mbta_alerts",
            description="Get real-time service alerts for MBTA lines. Returns current delays, suspensions, and service changes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "route": {
                        "type": "string",
                        "description": "MBTA route (Red, Orange, Blue, Green-B, Green-C, Green-D, Green-E, or leave empty for all)",
                        "enum": ["Red", "Orange", "Blue", "Green-B", "Green-C", "Green-D", "Green-E", ""]
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="get_mbta_routes",
            description="List all available MBTA subway routes with their details.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="find_mbta_stop",
            description="Find a MBTA stop by name or keyword. Returns stop information including ID and location.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Stop name or keyword to search for (e.g., 'Park Street', 'Kendall', 'Downtown')"
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="get_stop_predictions",
            description="Get real-time arrival predictions for a specific MBTA stop.",
            inputSchema={
                "type": "object",
                "properties": {
                    "stop_id": {
                        "type": "string",
                        "description": "MBTA stop ID (e.g., 'place-pktrm' for Park Street, 'place-knncl' for Kenmore)"
                    },
                    "route": {
                        "type": "string",
                        "description": "Optional: Filter by specific route (Red, Orange, Blue, etc.)"
                    }
                },
                "required": ["stop_id"]
            }
        ),
        types.Tool(
            name="plan_mbta_trip",
            description="Plan a trip between two MBTA stations. Returns route suggestions with transfers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "string",
                        "description": "Starting station name (e.g., 'Park Street', 'Kendall')"
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination station name (e.g., 'Harvard', 'Government Center')"
                    }
                },
                "required": ["origin", "destination"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any] | None
) -> list[types.TextContent]:
    """
    Handle tool calls from Claude.
    """
    
    if name == "get_mbta_alerts":
        route = arguments.get("route", "") if arguments else ""
        alerts = await get_alerts(route)
        return [types.TextContent(type="text", text=alerts)]
    
    elif name == "get_mbta_routes":
        routes = await get_routes()
        return [types.TextContent(type="text", text=routes)]
    
    elif name == "find_mbta_stop":
        if not arguments or "query" not in arguments:
            return [types.TextContent(type="text", text="Error: query parameter required")]
        stop_info = await find_stop(arguments["query"])
        return [types.TextContent(type="text", text=stop_info)]
    
    elif name == "get_stop_predictions":
        if not arguments or "stop_id" not in arguments:
            return [types.TextContent(type="text", text="Error: stop_id required")]
        predictions = await get_predictions(arguments["stop_id"], arguments.get("route"))
        return [types.TextContent(type="text", text=predictions)]
    
    elif name == "plan_mbta_trip":
        if not arguments or "origin" not in arguments or "destination" not in arguments:
            return [types.TextContent(type="text", text="Error: origin and destination required")]
        trip_plan = await plan_trip(arguments["origin"], arguments["destination"])
        return [types.TextContent(type="text", text=trip_plan)]
    
    else:
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

# Tool Implementation Functions

async def get_alerts(route: str = "") -> str:
    """Get MBTA alerts"""
    try:
        url = f"{MBTA_BASE_URL}/alerts"
        params = {}
        if route:
            params["filter[route]"] = route
        
        headers = {}
        if MBTA_API_KEY:
            headers["x-api-key"] = MBTA_API_KEY
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        alerts = data.get("data", [])
        
        if not alerts:
            return f"✅ No active alerts for {route if route else 'MBTA system'}"
        
        result = []
        for alert in alerts[:5]:  # Limit to 5 most recent
            attrs = alert.get("attributes", {})
            header = attrs.get("header", "Alert")
            effect = attrs.get("effect", "Unknown")
            severity = attrs.get("severity", 0)
            
            result.append(f"⚠️ {header}\n   Effect: {effect} (Severity: {severity})")
        
        return "\n\n".join(result)
        
    except Exception as e:
        return f"❌ Error fetching alerts: {str(e)}"

async def get_routes() -> str:
    """List all MBTA routes"""
    try:
        url = f"{MBTA_BASE_URL}/routes"
        params = {"filter[type]": "0,1"}  # Subway only
        
        headers = {}
        if MBTA_API_KEY:
            headers["x-api-key"] = MBTA_API_KEY
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        routes = data.get("data", [])
        
        result = ["🚇 MBTA Subway Routes:\n"]
        for route in routes:
            attrs = route.get("attributes", {})
            name = attrs.get("long_name", "Unknown")
            route_id = route.get("id", "")
            color = attrs.get("color", "")
            
            result.append(f"• {name} (ID: {route_id})")
        
        return "\n".join(result)
        
    except Exception as e:
        return f"❌ Error fetching routes: {str(e)}"

async def find_stop(query: str) -> str:
    """Find a stop by name"""
    try:
        # Check aliases first
        normalized = query.lower().strip()
        if normalized in ALIASES:
            actual_name = ALIASES[normalized]
            query = actual_name
        
        url = f"{MBTA_BASE_URL}/stops"
        params = {"filter[route_type]": "0,1", "filter[name]": query}
        
        headers = {}
        if MBTA_API_KEY:
            headers["x-api-key"] = MBTA_API_KEY
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        stops = data.get("data", [])
        
        if not stops:
            return f"❌ No stops found matching '{query}'"
        
        result = [f"🚉 Found {len(stops)} stop(s):\n"]
        for stop in stops[:5]:
            attrs = stop.get("attributes", {})
            name = attrs.get("name", "Unknown")
            stop_id = stop.get("id", "")
            
            result.append(f"• {name}\n  ID: {stop_id}")
        
        return "\n\n".join(result)
        
    except Exception as e:
        return f"❌ Error finding stop: {str(e)}"

async def get_predictions(stop_id: str, route: str = None) -> str:
    """Get arrival predictions for a stop"""
    try:
        url = f"{MBTA_BASE_URL}/predictions"
        params = {"filter[stop]": stop_id, "sort": "arrival_time"}
        
        if route:
            params["filter[route]"] = route
        
        headers = {}
        if MBTA_API_KEY:
            headers["x-api-key"] = MBTA_API_KEY
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        predictions = data.get("data", [])
        
        if not predictions:
            return f"📭 No upcoming arrivals for stop {stop_id}"
        
        result = [f"🚇 Upcoming arrivals at {stop_id}:\n"]
        for pred in predictions[:5]:
            attrs = pred.get("attributes", {})
            arrival = attrs.get("arrival_time", "Unknown")
            direction = attrs.get("direction_id", 0)
            status = attrs.get("status", "")
            
            dir_text = "Inbound" if direction == 1 else "Outbound"
            result.append(f"• {arrival} - {dir_text} ({status})")
        
        return "\n".join(result)
        
    except Exception as e:
        return f"❌ Error getting predictions: {str(e)}"

async def plan_trip(origin: str, destination: str) -> str:
    """Plan a trip between two stations"""
    # This would connect to your existing planner agent
    # For now, return a simple message
    try:
        # In production, call your planner at localhost:8782
        response = requests.get(
            "http://localhost:8782/plan",
            params={"origin": origin, "destination": destination},
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json().get("text", "Route found")
        else:
            return f"Could not plan trip from {origin} to {destination}"
            
    except Exception as e:
        return f"❌ Error planning trip: {str(e)}"

async def main():
    """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mbta-transit-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())