# Copyright AGNTCY Contributors (https://github.com/agntcy)
# SPDX-License-Identifier: Apache-2.0

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill)

from config.config import ROUTE_AGENT_HOST, ROUTE_AGENT_PORT

AGENT_SKILL = AgentSkill(
    id="get_routes",
    name="Get MBTA Routes",
    description="Returns MBTA service routes.",
    tags=["mbta", "transit", "routes"],
    examples=[
        "Can you provide directions to go from Framingham to Norwood?",
        "How to get to Cambridge from Kenmore?",
        "Is there a way to go to Newton from Cambridge?",
    ]
)

AGENT_CARD = AgentCard(
    name='MBTA Routes Service',
    id='mbta-routes-agent',
    description='An AI agent that provides MBTA service routes.',
    url='',
    version='1.0.0',
    defaultInputModes=["text"],
    defaultOutputModes=["text"],
    capabilities=AgentCapabilities(streaming=True),
    skills=[AGENT_SKILL],
    supportsAuthenticatedExtendedCard=False,
)