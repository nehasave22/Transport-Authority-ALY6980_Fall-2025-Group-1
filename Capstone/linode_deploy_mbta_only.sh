#!/bin/bash

# Deploy MBTA Agent ONLY (Separate Instance)
# Connects to existing NANDA Registry
# Usage: bash linode-deploy-mbta-agent-only.sh <MBTA_API_KEY> <LOCAL_PROJECT_PATH> <REGISTRY_URL> [REGION] [INSTANCE_TYPE]

set -e

MBTA_API_KEY="$1"
LOCAL_PROJECT_PATH="$2"
REGISTRY_URL="$3"
REGION="${4:-us-east}"
INSTANCE_TYPE="${5:-g6-standard-2}"  # 4GB for multi-agent system
ROOT_PASSWORD="${6:-}"

if [ -z "$MBTA_API_KEY" ] || [ -z "$LOCAL_PROJECT_PATH" ] || [ -z "$REGISTRY_URL" ]; then
    echo "❌ Usage: $0 <MBTA_API_KEY> <LOCAL_PROJECT_PATH> <REGISTRY_URL> [REGION] [INSTANCE_TYPE]"
    echo ""
    echo "Example:"
    echo "  $0 mbta-key-xxx . http://REGISTRY_IP:6900"
    echo ""
    echo "Parameters:"
    echo "  MBTA_API_KEY: Your MBTA API key"
    echo "  LOCAL_PROJECT_PATH: Path to Capstone directory (use . if already in folder)"
    echo "  REGISTRY_URL: Your registry URL (e.g., http://23.92.20.191:6900)"
    exit 1
fi

if [ ! -d "$LOCAL_PROJECT_PATH" ]; then
    echo "❌ Error: Path does not exist: $LOCAL_PROJECT_PATH"
    exit 1
fi

if [ -z "$ROOT_PASSWORD" ]; then
    ROOT_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
    echo "🔑 Generated root password: $ROOT_PASSWORD"
fi

FIREWALL_LABEL="mbta-agent-only"
SSH_KEY_LABEL="mbta-agent-key"
IMAGE_ID="linode/ubuntu22.04"
DEPLOYMENT_ID=$(date +%Y%m%d-%H%M%S)

echo "🚇 Deploying MBTA Agent (Separate Instance)"
echo "============================================"
echo "Deployment ID: $DEPLOYMENT_ID"
echo "Registry: $REGISTRY_URL"
echo ""

# Check Linode CLI
echo "[1/7] Checking Linode CLI..."
if ! linode-cli --version >/dev/null 2>&1; then
    echo "❌ Linode CLI not installed"
    exit 1
fi
echo "✅ Linode CLI ready"

# Package project
echo "[2/7] Packaging project..."
cd "$LOCAL_PROJECT_PATH"
TARBALL_NAME="mbta-agent-${DEPLOYMENT_ID}.tar.gz"
tar -czf "/tmp/$TARBALL_NAME" \
    --exclude='*.pyc' --exclude='__pycache__' --exclude='.git' \
    --exclude='.venv' --exclude='*.egg-info' --exclude='.env' \
    .
echo "✅ Packaged: $(du -h /tmp/$TARBALL_NAME | cut -f1)"

# Setup firewall (MBTA agent ports only)
echo "[3/7] Setting up firewall..."
FIREWALL_ID=$(linode-cli firewalls list --text --no-headers --format="id,label" | grep "$FIREWALL_LABEL" | cut -f1 || echo "")

INBOUND_RULES='[
    {"protocol": "TCP", "ports": "22", "addresses": {"ipv4": ["0.0.0.0/0"]}, "action": "ACCEPT"},
    {"protocol": "TCP", "ports": "6000", "addresses": {"ipv4": ["0.0.0.0/0"]}, "action": "ACCEPT"},
    {"protocol": "TCP", "ports": "8787", "addresses": {"ipv4": ["0.0.0.0/0"]}, "action": "ACCEPT"},
    {"protocol": "TCP", "ports": "16000", "addresses": {"ipv4": ["0.0.0.0/0"]}, "action": "ACCEPT"}
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
echo "[4/7] Setting up SSH key..."
if [ ! -f "${SSH_KEY_LABEL}.pub" ]; then
    ssh-keygen -t rsa -b 4096 -f "$SSH_KEY_LABEL" -N "" -C "mbta-$DEPLOYMENT_ID" >/dev/null 2>&1
fi
echo "✅ SSH key ready"

# Launch instance
echo "[5/7] Launching Linode..."
INSTANCE_ID=$(linode-cli linodes create \
    --type "$INSTANCE_TYPE" \
    --region "$REGION" \
    --image "$IMAGE_ID" \
    --label "mbta-agent-$DEPLOYMENT_ID" \
    --tags "MBTA-Agent" \
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
echo "[6/7] Waiting for SSH..."
for i in {1..30}; do
    if ssh -i "$SSH_KEY_LABEL" -o StrictHostKeyChecking=no -o ConnectTimeout=5 "root@$PUBLIC_IP" "echo ready" >/dev/null 2>&1; then
        echo "✅ SSH ready"
        break
    fi
    sleep 10
done

# Upload
echo "   Uploading project..."
scp -i "$SSH_KEY_LABEL" -o StrictHostKeyChecking=no "/tmp/$TARBALL_NAME" "root@$PUBLIC_IP:/tmp/"
echo "✅ Files uploaded"

# Setup MBTA agent
echo "[7/7] Setting up MBTA agent (10-15 minutes)..."

ssh -i "$SSH_KEY_LABEL" -o StrictHostKeyChecking=no "root@$PUBLIC_IP" bash << ENDSSH
set -e
exec > /var/log/mbta-setup.log 2>&1

echo "=== MBTA Agent Setup Started ==="
date

# Install packages
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git supervisor

# Create ubuntu user
if ! id -u ubuntu >/dev/null 2>&1; then
    useradd -m -s /bin/bash ubuntu
    mkdir -p /home/ubuntu/.ssh
    cp /root/.ssh/authorized_keys /home/ubuntu/.ssh/authorized_keys 2>/dev/null || true
    chown -R ubuntu:ubuntu /home/ubuntu/.ssh
    chmod 700 /home/ubuntu/.ssh
    chmod 600 /home/ubuntu/.ssh/authorized_keys 2>/dev/null || true
fi

# Extract MBTA project
cd /home/ubuntu
mkdir -p mbta-agent
cd mbta-agent
tar -xzf /tmp/$TARBALL_NAME
chown -R ubuntu:ubuntu /home/ubuntu/mbta-agent

# Create venv and install
sudo -u ubuntu python3 -m venv .venv
sudo -u ubuntu bash -c "source .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"

# Fix Capstone imports
sed -i 's/from Capstone\./from /g' /home/ubuntu/mbta-agent/agents/*/main.py

# Clone NANDA NEST
cd /home/ubuntu
sudo -u ubuntu git clone -b nov-5-demo https://github.com/DataWorksAI-com/NEST.git nanda-nest
cd nanda-nest
sudo -u ubuntu bash -c "source /home/ubuntu/mbta-agent/.venv/bin/activate && pip install -e ."

# Create corrected A2A adapter
cat > /home/ubuntu/mbta-agent/nanda_a2a_adapter.py << 'A2AEOF'
#!/usr/bin/env python3
import os, sys, requests
sys.path.insert(0, os.path.dirname(__file__))

try:
    from nanda_core.core.adapter import NANDA
    NANDA_AVAILABLE = True
except ImportError:
    NANDA_AVAILABLE = False

class MBTAMCPBridge:
    def __init__(self, chat_backend_url: str = "http://localhost:8787"):
        self.chat_backend_url = chat_backend_url
    
    def process_message(self, message: str, conversation_id: str) -> str:
        try:
            response = requests.post(
                f"{self.chat_backend_url}/chat",
                json={"messages": [{"role": "user", "content": message}]},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                messages = data.get("messages", [])
                if messages:
                    return messages[-1].get("content", "No response")
                return "No response"
            return f"Error: {response.status_code}"
        except Exception as e:
            return f"Error: {str(e)}"

def main():
    if not NANDA_AVAILABLE:
        return
    
    agent_id = os.getenv("AGENT_ID", "mbta-mcp-agent")
    port = int(os.getenv("A2A_PORT", "6000"))
    registry_url = os.getenv("REGISTRY_URL")
    public_url = os.getenv("PUBLIC_URL")
    
    bridge = MBTAMCPBridge()
    agent_logic = lambda msg, conv_id: bridge.process_message(msg, conv_id)
    
    nanda = NANDA(
        agent_id=agent_id,
        agent_logic=agent_logic,
        port=port,
        registry_url=registry_url,
        public_url=public_url,
        enable_telemetry=False
    )
    
    print(f"🚀 A2A ready: http://0.0.0.0:{port}/a2a")
    nanda.start()

if __name__ == "__main__":
    main()
A2AEOF

chmod +x /home/ubuntu/mbta-agent/nanda_a2a_adapter.py

# Create NANDA wrapper
cat > /home/ubuntu/mbta-nanda-wrapper.py << 'WRAPEOF'
#!/usr/bin/env python3
import os, sys, uuid, requests
sys.path.insert(0, '/home/ubuntu/nanda-nest')
from nanda_core.core.adapter import NANDA

def create_logic(backend):
    def logic(msg, conv_id):
        try:
            r = requests.post(f"{backend}/chat", json={"messages": [{"role": "user", "content": msg}]}, timeout=30)
            if r.status_code == 200:
                msgs = r.json().get("messages", [])
                return msgs[-1].get("content", "No response") if msgs else "No response"
            return f"Error: {r.status_code}"
        except Exception as e:
            return f"Error: {str(e)}"
    return logic

def main():
    base = os.getenv("AGENT_ID", "mbta-transit-agent")
    agent_id = f"{base}-{uuid.uuid4().hex[:6]}"
    print(f"Generated agent_id: {agent_id}")
    
    nanda = NANDA(
        agent_id=agent_id,
        agent_logic=create_logic("http://localhost:8787"),
        port=int(os.getenv("PORT", "16000")),
        registry_url=os.getenv("REGISTRY_URL"),
        public_url=os.getenv("PUBLIC_URL"),
        enable_telemetry=False
    )
    print(f"🚀 NANDA ready: http://0.0.0.0:16000/a2a")
    nanda.start()

if __name__ == "__main__":
    main()
WRAPEOF

chmod +x /home/ubuntu/mbta-nanda-wrapper.py

# Create supervisor configs
cat > /etc/supervisor/conf.d/mbta_alerts.conf << 'SUP1'
[program:mbta_alerts]
command=/home/ubuntu/mbta-agent/.venv/bin/python -m uvicorn agents.alerts.main:app --host 0.0.0.0 --port 8781
directory=/home/ubuntu/mbta-agent
user=ubuntu
autostart=true
autorestart=true
stderr_logfile=/var/log/mbta_alerts.err.log
stdout_logfile=/var/log/mbta_alerts.out.log
environment=PYTHONPATH="/home/ubuntu/mbta-agent",MBTA_API_KEY="$MBTA_API_KEY"
SUP1

cat > /etc/supervisor/conf.d/mbta_planner.conf << 'SUP2'
[program:mbta_planner]
command=/home/ubuntu/mbta-agent/.venv/bin/python -m uvicorn agents.planner.main:app --host 0.0.0.0 --port 8782
directory=/home/ubuntu/mbta-agent
user=ubuntu
autostart=true
autorestart=true
stderr_logfile=/var/log/mbta_planner.err.log
stdout_logfile=/var/log/mbta_planner.out.log
environment=PYTHONPATH="/home/ubuntu/mbta-agent",MBTA_API_KEY="$MBTA_API_KEY"
SUP2

cat > /etc/supervisor/conf.d/mbta_stopfinder.conf << 'SUP3'
[program:mbta_stopfinder]
command=/home/ubuntu/mbta-agent/.venv/bin/python -m uvicorn agents.stopfinder.main:app --host 0.0.0.0 --port 8783
directory=/home/ubuntu/mbta-agent
user=ubuntu
autostart=true
autorestart=true
stderr_logfile=/var/log/mbta_stopfinder.err.log
stdout_logfile=/var/log/mbta_stopfinder.out.log
environment=PYTHONPATH="/home/ubuntu/mbta-agent",MBTA_API_KEY="$MBTA_API_KEY"
SUP3

cat > /etc/supervisor/conf.d/mbta_chat.conf << 'SUP4'
[program:mbta_chat]
command=/home/ubuntu/mbta-agent/.venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port 8787
directory=/home/ubuntu/mbta-agent
user=ubuntu
autostart=true
autorestart=true
stderr_logfile=/var/log/mbta_chat.err.log
stdout_logfile=/var/log/mbta_chat.out.log
environment=PYTHONPATH="/home/ubuntu/mbta-agent",ALERTS_AGENT_URL="http://localhost:8781",PLANNER_AGENT_URL="http://localhost:8782",STOPFINDER_AGENT_URL="http://localhost:8783",MBTA_API_KEY="$MBTA_API_KEY"
SUP4

cat > /etc/supervisor/conf.d/mbta_a2a.conf << SUP5
[program:mbta_a2a]
command=/home/ubuntu/mbta-agent/.venv/bin/python nanda_a2a_adapter.py
directory=/home/ubuntu/mbta-agent
user=ubuntu
autostart=true
autorestart=true
stderr_logfile=/var/log/mbta_a2a.err.log
stdout_logfile=/var/log/mbta_a2a.out.log
environment=PYTHONPATH="/home/ubuntu/mbta-agent:/home/ubuntu/nanda-nest",AGENT_ID="mbta-mcp-agent",A2A_PORT="6000",REGISTRY_URL="$REGISTRY_URL",PUBLIC_URL="http://$PUBLIC_IP:6000",CHAT_BACKEND_URL="http://localhost:8787"
SUP5

cat > /etc/supervisor/conf.d/mbta_nanda_wrapper.conf << SUP6
[program:mbta_nanda_wrapper]
command=/home/ubuntu/mbta-agent/.venv/bin/python /home/ubuntu/mbta-nanda-wrapper.py
directory=/home/ubuntu
user=ubuntu
autostart=true
autorestart=true
stderr_logfile=/var/log/mbta_nanda_wrapper.err.log
stdout_logfile=/var/log/mbta_nanda_wrapper.out.log
environment=PYTHONPATH="/home/ubuntu/nanda-nest",AGENT_ID="mbta-transit-agent",REGISTRY_URL="$REGISTRY_URL",PUBLIC_URL="http://$PUBLIC_IP:16000",PORT="16000",MBTA_BACKEND_URL="http://localhost:8787"
SUP6

# Start services
systemctl enable supervisor
systemctl start supervisor
supervisorctl reread
supervisorctl update
sleep 30

echo "=== MBTA Agent Setup Complete ==="
supervisorctl status

echo ""
echo "MBTA Agent URLs:"
echo "  Chat UI: http://$PUBLIC_IP:8787"
echo "  A2A: http://$PUBLIC_IP:6000/a2a"
echo "  NANDA: http://$PUBLIC_IP:16000/a2a"
ENDSSH

# Cleanup
rm "/tmp/$TARBALL_NAME"

# Get agent ID from wrapper logs
echo ""
echo "Getting agent ID..."
sleep 5
AGENT_ID=$(ssh -i "$SSH_KEY_LABEL" -o StrictHostKeyChecking=no "root@$PUBLIC_IP" "tail /var/log/mbta_nanda_wrapper.out.log | grep 'Generated agent_id' | tail -1 | cut -d' ' -f3" || echo "")

echo ""
echo "🎉 MBTA Agent Deployed!"
echo "======================="
echo "Instance ID: $INSTANCE_ID"
echo "Public IP: $PUBLIC_IP"
echo "Root Password: $ROOT_PASSWORD"
echo "Agent ID: $AGENT_ID"
echo ""
echo "🌐 URLs:"
echo "  Chat UI:      http://$PUBLIC_IP:8787"
echo "  API Docs:     http://$PUBLIC_IP:8787/docs"
echo "  A2A Direct:   http://$PUBLIC_IP:6000/a2a"
echo "  NANDA Wrapper: http://$PUBLIC_IP:16000/a2a"
echo ""
echo "🧪 Test MBTA Agent:"
echo "curl http://$PUBLIC_IP:8787/chat -X POST -H 'Content-Type: application/json' \\"
echo "  -d '{\"messages\":[{\"role\":\"user\",\"content\":\"routes\"}]}'"
echo ""
echo "curl http://$PUBLIC_IP:16000/a2a -X POST -H 'Content-Type: application/json' \\"
echo "  -d '{\"content\":{\"text\":\"test\",\"type\":\"text\"},\"role\":\"user\",\"conversation_id\":\"t1\"}'"
echo ""
echo "📝 Register Agent with Registry:"
echo "================================"
echo ""
echo "ssh -i $SSH_KEY_LABEL root@$PUBLIC_IP"
echo ""
echo "# Create AgentFacts"
echo "curl -X POST http://$REGISTRY_URL/api/agent-facts -H 'Content-Type: application/json' \\"
echo "  -d '{"
echo "    \"agent_name\": \"${AGENT_ID//-/_}\","
echo "    \"username\": \"${AGENT_ID//-/_}\","
echo "    \"description\": \"Real-time MBTA transit information\","
echo "    \"capabilities\": {\"modalities\": [\"text\"], \"streaming\": false, \"batch\": true},"
echo "    \"endpoints\": {"
echo "      \"static\": [\"http://$PUBLIC_IP:16000\"],"
echo "      \"a2a\": \"http://$PUBLIC_IP:16000/a2a\","
echo "      \"chat\": \"http://$PUBLIC_IP:8787/chat\""
echo "    },"
echo "    \"skills\": [{"
echo "      \"id\": \"transit_alerts\","
echo "      \"description\": \"MBTA alerts\","
echo "      \"inputModes\": [\"text\"],"
echo "      \"outputModes\": [\"text\"]"
echo "    }]"
echo "  }'"
echo ""
echo "# Register Agent"
echo "curl -X POST $REGISTRY_URL/register -H 'Content-Type: application/json' \\"
echo "  -d '{"
echo "    \"agent_id\": \"$AGENT_ID\","
echo "    \"agent_url\": \"http://$PUBLIC_IP:16000\","
echo "    \"description\": \"Real-time MBTA transit information agent\","
echo "    \"capabilities\": [\"transit_alerts\", \"route_information\", \"trip_planning\"],"
echo "    \"domain\": \"transportation\""
echo "  }'"
echo ""
echo "🔑 SSH: ssh -i $SSH_KEY_LABEL root@$PUBLIC_IP"
echo "🛑 Delete: linode-cli linodes delete $INSTANCE_ID"
