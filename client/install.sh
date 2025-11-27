#!/bin/bash
set -e

echo "🚀 WebSocket Client Installation Script"
echo "========================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "❌ Please run as root (sudo ./install.sh)"
  exit 1
fi

# Configuration
INSTALL_USER=${INSTALL_USER:-kiosk}
CONFIG_DIR="/etc/ws-client"
LOG_DIR="/var/log/ws-client"
SERVICE_NAME="ws-client"

echo "📋 Configuration:"
echo "   User: $INSTALL_USER"
echo "   Config dir: $CONFIG_DIR"
echo "   Log dir: $LOG_DIR"
echo ""

# Create kiosk user if doesn't exist
if ! id "$INSTALL_USER" &>/dev/null; then
    echo "👤 Creating user: $INSTALL_USER"
    useradd -r -s /bin/bash -m "$INSTALL_USER"
else
    echo "✅ User $INSTALL_USER already exists"
fi

# Create directories
echo "📁 Creating directories..."
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOG_DIR"

# Set ownership
chown -R "$INSTALL_USER:$INSTALL_USER" "$CONFIG_DIR"
chown -R "$INSTALL_USER:$INSTALL_USER" "$LOG_DIR"

echo "✅ Directories created"
echo ""

# Install Python package
# Look for any version of wheel file in current directory
WHEEL_FILE=$(ls ws_client-*-py3-none-any.whl 2>/dev/null | head -1)

if [ -n "$WHEEL_FILE" ]; then
    echo "📦 Found wheel: $WHEEL_FILE"
    echo "📦 Installing package..."
    # Use --break-system-packages for modern distros (PEP 668)
    python3 -m pip install --upgrade --break-system-packages "$WHEEL_FILE"
    echo "✅ Package installed"
else
    echo "❌ Error: No wheel file found in current directory"
    echo ""
    echo "Please download the wheel file first:"
    echo "  wget https://github.com/korolkovko/ws-gateway-monorepo/releases/download/vX.X.X/ws_client-X.X.X-py3-none-any.whl"
    echo ""
    echo "Or check latest release:"
    echo "  https://github.com/korolkovko/ws-gateway-monorepo/releases/latest"
    exit 1
fi
echo ""

# Create configuration files
if [ ! -f "$CONFIG_DIR/.env" ]; then
    echo "⚙️  Creating default configuration..."
    cat > "$CONFIG_DIR/.env" << 'EOF'
# WebSocket Server Configuration
WS_SERVER_URL=wss://your-server.railway.app/ws
WS_TOKEN=your_jwt_token_here

# Routing Configuration (optional)
ROUTING_CONFIG_PATH=/etc/ws-client/routing_config.yaml

# Logging
LOG_LEVEL=INFO

# Health Check Server
HEALTH_CHECK_PORT=9091
EOF
    echo "✅ Created $CONFIG_DIR/.env"
else
    echo "✅ Configuration file already exists"
fi

if [ ! -f "$CONFIG_DIR/routing_config.yaml" ]; then
    cat > "$CONFIG_DIR/routing_config.yaml" << 'EOF'
routes:
  payment:
    url: "http://127.0.0.1:8011/api/v1/payment"
    timeout: 35

  fiscal:
    url: "http://127.0.0.1:8011/api/v1/fiscal"
    timeout: 35

  kds:
    url: "http://127.0.0.1:8012/api/v1/kds"
    timeout: 30

  print:
    url: "http://127.0.0.1:8013/api/v1/print"
    timeout: 20

default:
  url: "http://127.0.0.1:8080"
  timeout: 30
EOF
    echo "✅ Created $CONFIG_DIR/routing_config.yaml"
else
    echo "✅ Routing config already exists"
fi

# Set permissions
chmod 600 "$CONFIG_DIR/.env"
chmod 644 "$CONFIG_DIR/routing_config.yaml"
chown "$INSTALL_USER:$INSTALL_USER" "$CONFIG_DIR/.env"
chown "$INSTALL_USER:$INSTALL_USER" "$CONFIG_DIR/routing_config.yaml"

echo "✅ Configuration files copied"
echo ""

# Install systemd service
echo "🔧 Installing systemd service..."
cp ws-client.service "/etc/systemd/system/$SERVICE_NAME.service"
systemctl daemon-reload
echo "✅ Service installed"
echo ""

# Instructions
echo "✅ Installation complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Edit configuration:"
echo "      sudo nano $CONFIG_DIR/.env"
echo "      sudo nano $CONFIG_DIR/routing_config.yaml"
echo ""
echo "   2. Start service:"
echo "      sudo systemctl start $SERVICE_NAME"
echo ""
echo "   3. Enable auto-start:"
echo "      sudo systemctl enable $SERVICE_NAME"
echo ""
echo "   4. Check status:"
echo "      sudo systemctl status $SERVICE_NAME"
echo ""
echo "   5. View logs:"
echo "      sudo journalctl -u $SERVICE_NAME -f"
echo "      or"
echo "      sudo tail -f $LOG_DIR/proxy_*.log"
echo ""
echo "   6. Health check:"
echo "      curl http://localhost:9091/health"
echo ""
