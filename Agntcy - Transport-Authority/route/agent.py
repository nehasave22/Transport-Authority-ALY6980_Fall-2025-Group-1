# Copyright AGNTCY Contributors (https://github.com/agntcy)
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import TypedDict
import requests
import os 

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from ioa_observe.sdk.decorators import agent, graph

from common.llm import get_llm

logger = logging.getLogger("mbta.route_agent.graph")

class State(TypedDict):
    prompt: str
    error_type: str
    error_message: str
    route_notes: str

@agent(name="route_agent")
class RouteAgent:
    def __init__(self):
        self.ROUTE_NODE = "RouteNode"
        self._agent = self.build_graph()

    @graph(name="route_graph")
    def build_graph(self) -> StateGraph:
        graph_builder = StateGraph(State)
        graph_builder.add_node(self.ROUTE_NODE, self.route_node)
        graph_builder.add_edge(START, self.ROUTE_NODE)
        graph_builder.add_edge(self.ROUTE_NODE, END)
        return graph_builder.compile()

    async def route_node(self, state: State):
        """Fetch and format MBTA routes."""
        user_prompt = state.get("prompt")
        logger.debug(f"Received user prompt: {user_prompt}")
        
        # Extract route from prompt using LLM
        system_prompt = (
            "Extract the MBTA route from this query if mentioned. "
            "Routes: Red, Orange, Blue, Green, Green-B, Green-C, Green-D, Green-E. "
            "Respond with ONLY the route name or 'none' if not specified."
        )
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        response = get_llm().invoke(messages)
        route = response.content.strip()
        route = None if route.lower() == 'none' else route
        
        # Fetch routes from MBTA API
        try:
            mbta_key = os.getenv("MBTA_API_KEY")
            if not mbta_key:
                return {
                    "error_type": "config_error",
                    "error_message": "MBTA_API_KEY not configured"
                }
            
            params = {
                "api_key": mbta_key,
                "sort": "-updated_at",
                "page[limit]": "5",
                "filter[lifecycle]": "NEW,ONGOING,UPDATE"
            }
            
            if route:
                params["filter[route]"] = route
            
            logger.info(f"Fetching routes for route: {route}")
            
            r = requests.get(
                "https://api-v3.mbta.com/routes",
                params=params,
                timeout=10
            )
            r.raise_for_status()
            
            data = r.json()
            routes = data.get("data", [])
            
            if not routes:
                route_text = f"No current routes for {route}." if route else "No current routes."
                return {"route_notes": route_text}
            
            # Format routes with LLM
            route_summaries = []
            for route in routes[:3]:
                attrs = route.get("attributes", {})
                route_summaries.append({
                    "header": attrs.get("header", ""),
                    "severity": attrs.get("severity", ""),
                    "effect": attrs.get("effect", "")
                })
            
            format_prompt = (
                f"Format these MBTA routes concisely for riders:\n"
                f"{route_summaries}\n"
                f"Route: {route or 'all lines'}\n"
                f"Provide a brief, helpful summary."
            )
            
            messages = [
                SystemMessage(content="You are an MBTA service assistant."),
                HumanMessage(content=format_prompt)
            ]
            formatted = get_llm().invoke(messages)
            
            return {"route_notes": formatted.content}
            
        except Exception as e:
            logger.error(f"Error fetching routes: {e}")
            return {
                "error_type": "api_error",
                "error_message": f"Error getting routes: {str(e)}"
            }

    async def ainvoke(self, input: str) -> dict:
        """
        Sends a user input string to the agent asynchronously and returns the result.

        Args:
            input (str): A user prompt describing MBTA routes.

        Returns:
            dict: A response dictionary, typically containing either:
                - "route_notes" with the LLM's generated profile, or
                - An error message if parsing or context extraction failed.
        """
        # build graph if not already built
        if not hasattr(self, '_agent'):
            self._agent = self.build_graph()
        return await self._agent.ainvoke({"prompt": input})