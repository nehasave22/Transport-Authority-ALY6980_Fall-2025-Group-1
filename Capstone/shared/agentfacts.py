
# shared/agentfacts.py
import os, time
def agentfacts_default(capabilities):
    return {
        "name": os.getenv("AGENT_NAME", "agent"),
        "version": os.getenv("AGENT_VERSION", "1.0.0"),
        "identity": {"id": os.getenv("AGENT_ID", "ulid-placeholder"), "owner": os.getenv("AGENT_OWNER", "neurona.ai")},
        "capabilities": capabilities,
        "endpoints": {"https": os.getenv("HTTP_PUBLIC_URL", "")},
        "auth": {"type": os.getenv("AUTH_TYPE", "none"), "issuer": os.getenv("AUTH_ISSUER", "")},
        "ttl_seconds": int(os.getenv("AGENTFACTS_TTL", "300")),
        "metadata": {"schema": "agentfacts/v1", "docs": os.getenv("AGENT_DOCS_URL", "")},
        "timestamp": int(time.time())
    }
