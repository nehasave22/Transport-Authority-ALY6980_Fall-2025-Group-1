# Copyright AGNTCY Contributors (https://github.com/agntcy)
# SPDX-License-Identifier: Apache-2.0

import os
from dotenv import load_dotenv

load_dotenv()  # Automatically loads from `.env` or `.env.local`

DEFAULT_MESSAGE_TRANSPORT = os.getenv("DEFAULT_MESSAGE_TRANSPORT", "SLIM")
TRANSPORT_SERVER_ENDPOINT = os.getenv("TRANSPORT_SERVER_ENDPOINT", "http://localhost:46357")
ALERT_AGENT_HOST = os.getenv("ALERT_AGENT_HOST", "localhost")
ALERT_AGENT_PORT = int(os.getenv("ALERT_AGENT_PORT", "9999"))
ROUTE_AGENT_HOST = os.getenv("ROUTE_AGENT_HOST", "localhost")
ROUTE_AGENT_PORT = int(os.getenv("ROUTE_AGENT_PORT", "9998"))
STOP_FINDER_AGENT_HOST = os.getenv("STOP_FINDER_AGENT_HOST", "localhost")
STOP_FINDER_AGENT_PORT = int(os.getenv("STOP_FINDER_AGENT_PORT", "9997"))
EXCHANGE_AGENT_HOST = os.getenv("EXCHANGE_AGENT_HOST", "localhost")
EXCHANGE_AGENT_PORT = int(os.getenv("EXCHANGE_FINDER_AGENT_PORT", "9996"))
LLM_PROVIDER = os.getenv("LLM_PROVIDER")
LOGGING_LEVEL = os.getenv("LOGGING_LEVEL", "INFO").upper()
