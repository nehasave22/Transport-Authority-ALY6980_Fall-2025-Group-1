#!/bin/bash

# Deploy NANDA Registry ONLY (Separate Instance)
# Usage: bash linode_deploy_registry_only.sh <MONGODB_URL> [REGION] [INSTANCE_TYPE]

set -e

MONGODB_URL="$1"
REGION="${2:-us-east}"
INSTANCE_TYPE="${3:-g6-standard-1}"  # 2GB is enough for registry
ROOT_PASSWORD="${4:-}"

if [ -z "$MONGODB_URL" ]; then
    echo "❌ Usage: $0 <MONGODB_URL> [REGION] [INSTANCE_TYPE]"
    echo ""
    echo "Example:"
    echo "  $0 \"mongodb+srv://user:pass@cluster.mongodb.net/\""
    echo ""
    exit 1
fi

if [ -z "$ROOT_PASSWORD" ]; then
    ROOT_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
    echo "🔑 Generated root password: $ROOT_PASSWORD"
fi

FIREWALL_LABEL="nanda-registry-only"
SSH_KEY_LABEL="nanda-registry-key"
IMAGE_ID="linode/ubuntu22.04"
DEPLOYMENT_ID=$(date +%Y%m%d-%H%M%S)

echo "🗄️ Deploying NANDA Registry (Separate Instance)"
echo "================================================"
echo "Deployment ID: $DEPLOYMENT_ID"
echo ""

# Check Linode CLI
echo "[1/5] Checking Linode CLI..."
if ! linode-cli --version >/dev/null 2>&1; then
    echo "❌ Linode CLI not installed"
    exit 1
fi
echo "✅ Linode CLI ready"

# Setup firewall (Registry ports only)
echo "[2/5] Setting up firewall..."
FIREWALL_ID=$(linode-cli firewalls list --text --no-headers --format="id,label" | grep "$FIREWALL_LABEL" | cut -f1 || echo "")

INBOUND_RULES='[
    {"protocol": "TCP", "ports": "22", "addresses": {"ipv4": ["0.0.0.0/0"]}, "action": "ACCEPT"},
    {"protocol": "TCP", "ports": "6900", "addresses": {"ipv4": ["0.0.0.0/0"]}, "action": "ACCEPT"},
    {"protocol": "TCP", "ports": "8000", "addresses": {"ipv4": ["0.0.0.0/0"]}, "action": "ACCEPT"},
    {"protocol": "TCP", "ports": "9000", "addresses": {"ipv4": ["0.0.0.0/0"]}, "action": "ACCEPT"}
]'

if [ -z "$FIREWALL_ID" ]; then
    linode-cli firewalls create \
        --label "$FIREWALL_LABEL" \
        --rules.inbound_policy DROP \
        --rules.outbound_policy ACCEPT \
        --rules.inbound "$INBOUND_RULES" >/dev/null
    FIREWALL_ID=$(linode-cli firewalls list --text --no-headers --format="id,label" | grep "$FIREWALL_LABEL" | cut -f1)
    echo "✅ Created firewall"
else
    linode-cli firewalls rules-update "$FIREWALL_ID" --inbound "$INBOUND_RULES" >/dev/null 2>&1
    echo "✅ Using existing firewall"
fi

# Setup SSH key
echo "[3/5] Setting up SSH key..."
if [ ! -f "${SSH_KEY_LABEL}.pub" ]; then
    ssh-keygen -t rsa -b 4096 -f "$SSH_KEY_LABEL" -N "" -C "registry-$DEPLOYMENT_ID" >/dev/null 2>&1
fi
echo "✅ SSH key ready"

# Launch instance
echo "[4/5] Launching Linode..."
INSTANCE_ID=$(linode-cli linodes create \
    --type "$INSTANCE_TYPE" \
    --region "$REGION" \
    --image "$IMAGE_ID" \
    --label "nanda-registry-$DEPLOYMENT_ID" \
    --tags "NANDA-Registry" \
    --root_pass "$ROOT_PASSWORD" \
    --authorized_keys "$(cat ${SSH_KEY_LABEL}.pub)" \
    --firewall_id "$FIREWALL_ID" \
    --text --no-headers --format="id")
echo "✅ Instance ID: $INSTANCE_ID"

# Wait for running
echo "   Waiting for instance..."
while true; do
    STATUS=$(linode-cli linodes view "$INSTANCE_ID" --text --no-headers --format="status")
    [ "$STATUS" = "running" ] && break
    sleep 10
done

PUBLIC_IP=$(linode-cli linodes view "$INSTANCE_ID" --text --no-headers --format="ipv4")
echo "✅ Public IP: $PUBLIC_IP"

# Wait for SSH
echo "[5/5] Setting up registry..."
for i in {1..30}; do
    if ssh -i "$SSH_KEY_LABEL" -o StrictHostKeyChecking=no -o ConnectTimeout=5 "root@$PUBLIC_IP" "echo ready" >/dev/null 2>&1; then
        echo "✅ SSH ready"
        break
    fi
    sleep 10
done

# Setup registry
ssh -i "$SSH_KEY_LABEL" -o StrictHostKeyChecking=no "root@$PUBLIC_IP" bash << ENDSSH
set -e
exec > /var/log/registry-setup.log 2>&1

echo "=== Registry Setup Started ==="
apt-get update -y
apt-get install -y python3 python3-venv python3-pip supervisor

# Create ubuntu user
if ! id -u ubuntu >/dev/null 2>&1; then
    useradd -m -s /bin/bash ubuntu
    mkdir -p /home/ubuntu/.ssh
    cp /root/.ssh/authorized_keys /home/ubuntu/.ssh/authorized_keys 2>/dev/null || true
    chown -R ubuntu:ubuntu /home/ubuntu/.ssh
    chmod 700 /home/ubuntu/.ssh
    chmod 600 /home/ubuntu/.ssh/authorized_keys 2>/dev/null || true
fi

# Create registry directory WITH CORRECT OWNERSHIP
cd /home/ubuntu
sudo -u ubuntu mkdir -p nanda-registry
cd nanda-registry

# Create venv AS UBUNTU USER
sudo -u ubuntu python3 -m venv .venv
sudo -u ubuntu bash -c "source .venv/bin/activate && pip install --upgrade pip && pip install fastapi pymongo uvicorn"

# Create Registry Server
cat > agentIndex.py << 'REGEOF'
from fastapi import FastAPI, HTTPException
from pymongo import MongoClient
from datetime import datetime
from typing import Optional
import os

app = FastAPI(title="Private NANDA Registry")
ATLAS_URL = os.getenv("ATLAS_URL")
index_client = MongoClient(ATLAS_URL)
index_db = index_client.nanda_private_registry
agents = index_db.agents

try:
    agents.create_index("agent_id", unique=True, sparse=True)
except: pass

@app.get("/")
def root():
    return {"message": "Private NANDA Registry", "status": "running", "version": "1.0"}

@app.post("/register")
def register_agent(agent_data: dict):
    if not agent_data.get("agent_id"):
        raise HTTPException(status_code=400, detail="agent_id required")
    if not agent_data.get("agent_url"):
        raise HTTPException(status_code=400, detail="agent_url required")
    PUBLIC_IP = os.getenv("PUBLIC_IP", "localhost")
    agent_dict = {
        "agent_id": agent_data["agent_id"],
        "agent_url": agent_data["agent_url"],
        "description": agent_data.get("description", "NANDA agent"),
        "capabilities": agent_data.get("capabilities", ["chat"]),
        "domain": agent_data.get("domain", "general"),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    clean_username = agent_dict["agent_id"].replace("-", "_")
    agent_dict["agentFactsURL"] = f"http://{PUBLIC_IP}:8000/@{clean_username}.json"
    try:
        result = agents.insert_one(agent_dict)
        print(f"✅ Registered agent: {agent_dict['agent_id']}")
        return {"status": "success", "agent_id": agent_dict["agent_id"], "id": str(result.inserted_id)}
    except Exception as e:
        if "duplicate" in str(e):
            raise HTTPException(status_code=400, detail="Agent already exists")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/list")
def list_agents():
    agent_list = list(agents.find({}, {"_id": 0}))
    return {"agents": agent_list, "count": len(agent_list)}

@app.get("/search")
def search_agents(q: Optional[str] = None, domain: Optional[str] = None):
    query = {}
    if q:
        query["\\\$or"] = [
            {"agent_id": {"\\\$regex": q, "\\\$options": "i"}},
            {"description": {"\\\$regex": q, "\\\$options": "i"}}
        ]
    if domain:
        query["domain"] = domain
    results = list(agents.find(query, {"_id": 0}))
    return {"agents": results, "count": len(results)}

@app.get("/lookup/{agent_id}")
def get_agent(agent_id: str):
    agent = agents.find_one({"agent_id": agent_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent

@app.put("/update/{agent_id}")
def update_agent(agent_id: str, update_data: dict):
    update_data["updated_at"] = datetime.utcnow()
    result = agents.update_one({"agent_id": agent_id}, {"\\\$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Agent not found")
    print(f"✅ Updated agent: {agent_id}")
    return {"status": "success", "modified": result.modified_count > 0}

@app.delete("/agents/{agent_id}")
def delete_agent(agent_id: str):
    result = agents.delete_one({"agent_id": agent_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Agent not found")
    print(f"🗑️ Deleted agent: {agent_id}")
    return {"status": "success", "deleted": True}

@app.get("/health")
def health_check():
    try:
        index_client.admin.command('ping')
        agent_count = agents.count_documents({})
        return {"status": "healthy", "mongodb": "connected", "agents": agent_count}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=6900)
REGEOF

# Create AgentFacts Server
cat > agentFactsServer.py << 'FACTEOF'
from fastapi import FastAPI, HTTPException
from pymongo import MongoClient
import os

app = FastAPI(title="Private AgentFacts Server")
ATLAS_URL = os.getenv("ATLAS_URL")
client = MongoClient(ATLAS_URL)
db = client.nanda_private_registry
facts = db.agent_facts

try:
    facts.create_index("agent_name", unique=True)
except: pass

@app.post("/api/agent-facts")
def create_agent_facts(agent_facts: dict):
    try:
        result = facts.insert_one(agent_facts)
        print(f"✅ Created AgentFacts: {agent_facts.get('agent_name')}")
        return {"status": "success", "id": str(result.inserted_id)}
    except Exception as e:
        if "duplicate" in str(e):
            agent_name = agent_facts.get("agent_name")
            facts.update_one(
                {"agent_name": agent_name},
                {"\\\$set": agent_facts}
            )
            print(f"✅ Updated AgentFacts: {agent_name}")
            return {"status": "success", "message": "updated"}
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/@{username}.json")
def get_agent_facts(username: str):
    fact = facts.find_one({"agent_name": username}, {"_id": 0})
    if not fact:
        raise HTTPException(status_code=404, detail="AgentFacts not found")
    return fact

@app.get("/list")
def list_agent_facts():
    all_facts = list(facts.find({}, {"_id": 0}))
    return {"agent_facts": all_facts, "count": len(all_facts)}

@app.get("/health")
def health_check():
    try:
        client.admin.command('ping')
        facts_count = facts.count_documents({})
        return {"status": "healthy", "mongodb": "connected", "agent_facts": facts_count}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
FACTEOF

chown -R ubuntu:ubuntu /home/ubuntu/nanda-registry

# Create supervisor configs
cat > /etc/supervisor/conf.d/registry.conf << SUP1
[program:registry]
command=/home/ubuntu/nanda-registry/.venv/bin/python agentIndex.py
directory=/home/ubuntu/nanda-registry
user=ubuntu
autostart=true
autorestart=true
stderr_logfile=/var/log/registry.err.log
stdout_logfile=/var/log/registry.out.log
environment=ATLAS_URL="$MONGODB_URL",PUBLIC_IP="$PUBLIC_IP"
SUP1

cat > /etc/supervisor/conf.d/agentfacts.conf << SUP2
[program:agentfacts]
command=/home/ubuntu/nanda-registry/.venv/bin/python agentFactsServer.py
directory=/home/ubuntu/nanda-registry
user=ubuntu
autostart=true
autorestart=true
stderr_logfile=/var/log/agentfacts.err.log
stdout_logfile=/var/log/agentfacts.out.log
environment=ATLAS_URL="$MONGODB_URL"
SUP2




# Start services
systemctl enable supervisor
systemctl start supervisor
supervisorctl reread
supervisorctl update
sleep 10

echo "=== Registry Setup Complete ==="
supervisorctl status

echo ""
echo "Registry URLs:"
echo "  Registry API: http://$PUBLIC_IP:6900"
echo "  AgentFacts: http://$PUBLIC_IP:8000"
ENDSSH

echo ""
echo "Verifying services started..."
sleep 10

REGISTRY_STATUS=$(ssh -i "$SSH_KEY_LABEL" -o StrictHostKeyChecking=no "root@$PUBLIC_IP" "supervisorctl status registry | grep RUNNING" || echo "FAILED")
FACTS_STATUS=$(ssh -i "$SSH_KEY_LABEL" -o StrictHostKeyChecking=no "root@$PUBLIC_IP" "supervisorctl status agentfacts | grep RUNNING" || echo "FAILED")

if [[ "$REGISTRY_STATUS" == "FAILED" ]] || [[ "$FACTS_STATUS" == "FAILED" ]]; then
    echo "⚠️  Warning: Services may not have started properly"
    echo "📋 Check status: ssh -i $SSH_KEY_LABEL root@$PUBLIC_IP 'supervisorctl status'"
    echo "🔧 Manual fix commands:"
    echo "  ssh -i $SSH_KEY_LABEL root@$PUBLIC_IP"
    echo "  cd /home/ubuntu && chown -R ubuntu:ubuntu nanda-registry"
    echo "  supervisorctl restart registry agentfacts"
else
    echo "✅ All services verified running"
fi

echo ""
echo "🎉 Registry Deployed Successfully!"
echo "=================================="
echo "Instance ID: $INSTANCE_ID"
echo "Public IP: $PUBLIC_IP"
echo "Root Password: $ROOT_PASSWORD"
echo ""
echo "🌐 URLs:"
echo "  Registry API:  http://$PUBLIC_IP:6900"
echo "  AgentFacts:    http://$PUBLIC_IP:8000"
echo "  Health Check:  http://$PUBLIC_IP:6900/health"
echo "  List Agents:   http://$PUBLIC_IP:6900/list"
echo ""
echo "🧪 Test:"
echo "curl http://$PUBLIC_IP:6900/health"
echo "curl http://$PUBLIC_IP:8000/health"
echo ""
echo "📝 Save this registry URL for agent deployment:"
echo "REGISTRY_URL=http://$PUBLIC_IP:6900"
echo ""
echo "🔑 SSH: ssh -i $SSH_KEY_LABEL root@$PUBLIC_IP"
echo "🛑 Delete: linode-cli linodes delete $INSTANCE_ID"