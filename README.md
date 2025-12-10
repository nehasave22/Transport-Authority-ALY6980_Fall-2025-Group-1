

# 🚇 **Multi-Agent Architecture for Decentralized Transit Systems**

*Distributed Registry + MCP Server + MBTA Agents + A2A Communication*

---

## 📌 **Overview**

This project implements a **fully decentralized, multi-agent architecture** for public transit systems.
It provides:

* A **central registry** for autonomous transit agents
* A **metadata service** (AgentFacts)
* A production-ready **MCP server** for LLM + agent integration
* A full **MBTA agent stack** (Alerts, Route Planner, Stop Finder)
* Support for **agent-to-agent (A2A) communication**
* Automated **Linode deployments** for production
* Built-in examples for **Anthropic Claude MCP integration**

This architecture supports scalable, discoverable, self-organizing agents that interact through standardized interfaces and can be accessed by LLMs.

---


# 🧩 **Core Components**

### 1️⃣ **NANDA Registry Server**

Handles:

* Agent registration
* Agent search
* Agent metadata linking
* A2A communication URL discovery
* MongoDB persistence

Runs on: **Port 6900**

---

### 2️⃣ **AgentFacts Server**

Stores rich metadata for agents:

* Skills
* Supported modalities
* Certifications
* Performance scores

Runs on: **Port 8000**

---

### 3️⃣ **MCP Server (FastMCP)**

Provides Model Context Protocol tools:

* `register_agent`
* `search_agents`
* `list_agents`
* `update_agent`
* `delete_agent`
* `get_agent_facts`

Accessible by: **Anthropic Claude**, **NEST**, and any MCP client
Runs on: **9090** or SSE/stdio mode

---

### 4️⃣ **MBTA Multi-Agent System**

Includes:

| Agent         | Port  | Responsibility         |
| ------------- | ----- | ---------------------- |
| Alerts Agent  | 8781  | Real-time MBTA alerts  |
| Route Planner | 8782  | Pathfinding + routing  |
| Stop Finder   | 8783  | Stop lookup by geo/ID  |
| Chat Backend  | 8787  | Unified chat interface |
| A2A Wrapper   | 16000 | A2A protocol adapter   |

---

# 🚀 **Linode Deployment**

Two automated deployment scripts:

### **1. Registry Only Deployment**

```
linode_deploy_registry_only.sh "<MONGODB_ATLAS_URL>"
```

Creates:

* Registry (6900)
* AgentFacts API (8000)
* MCP Server (9090)
* Firewall
* Supervisor-managed services

---

### **2. MBTA Agents Deployment**

```
linode-deploy-mbta-agent-only.sh <MBTA_API_KEY> <LOCAL_PROJECT_PATH> <REGISTRY_URL>
```

Creates:

* Alerts (8781)
* Planner (8782)
* StopFinder (8783)
* Chat Backend (8787)
* A2A Wrapper (6000/16000)
* Secure firewall
* Supervisor-managed backend

---

# 📚 **Examples (Anthropic Claude Integration)**

Located under:

```
examples/
```

### **Stage 01 – Regex Extraction**

Manual agent lookup
(`@agent-name` pattern)

### **Stage 02 – Native MCP Tool Calling (Recommended)**

Claude automatically calls registry tools

### **Stage 03 – A2A Multi-Agent Communication**

Claude coordinates registry lookup + A2A call

### **Stage 04 – External MCP Server**

Production: HTTP/SSE MCP server with multiple clients

Each stage includes:

* Code examples
* Architecture diagrams
* Flow explanations
* QuickStart guides

---

# 🧪 **Health Checks**

```
curl http://<IP>:6900/health
curl http://<IP>:8000/health
curl http://<IP>:9090/health
curl http://<IP>:8787/health
```

---

# 🔧 **Environment Variables**

```
export ATLAS_URL="mongodb+srv://..."
export ANTHROPIC_API_KEY="sk-ant-..."
export MBTA_API_KEY="..."
```

---

# 📦 **Project Structure**

```
/
├── src/
│   ├── agentIndex.py           # Registry API
│   ├── agentFactsServer.py     # AgentFacts API
│   ├── agent_mcp.py            # MCP Server
│
├── agents/
│   ├── alerts/main.py
│   ├── planner/main.py
│   ├── stopfinder/main.py
│
├── server/
│   ├── app.py                  # Chat backend
│
├── examples/
│   ├── 01_regex_extraction/
│   ├── 02_mcp_tool_calling/
│   ├── 03_a2a_agent_communication/
│   ├── 04_external_mcp_server/
│
├── deploy/
│   ├── linode_deploy_registry_only.sh
│   ├── linode-deploy-mbta-agent-only.sh
│
└── requirements.txt
```

---

# 🧠 **Key Capabilities**

### ✔ Fully decentralized multi-agent framework

### ✔ MCP-native tool discovery

### ✔ A2A communication protocol support

### ✔ MBTA multi-agent integration

### ✔ One-command Linode deployment

### ✔ Supervisor-managed microservices

### ✔ Registry + Facts + UI + MCP in one cluster

### ✔ Real-time, production-ready architecture

---

# 🤝 **Contributing**

Pull requests welcome!
Add new agents, MCP tools, or deployment modules.

---



# 📌 **Final: Project Name**

### 🎯 **Multi-Agent Architecture for Decentralized Transit Systems**

