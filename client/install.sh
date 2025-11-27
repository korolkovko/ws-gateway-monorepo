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
if [ -f "dist/ws_client-1.0.0-py3-none-any.whl" ]; then
    echo "📦 Installing wheel package..."
    pip3 install --upgrade dist/ws_client-1.0.0-py3-none-any.whl
    echo "✅ Package installed"
else
    echo "⚠️  Wheel file not found. Building from source..."
    pip3 install build
    python3 -m build
    pip3 install --upgrade dist/ws_client-*.whl
    echo "✅ Package built and installed"
fi
echo ""

# Copy configuration files
if [ ! -f "$CONFIG_DIR/.env" ]; then
    echo "⚙️  Setting up configuration..."
    cp .env.example "$CONFIG_DIR/.env"
    echo "📝 Edit $CONFIG_DIR/.env with your settings"
else
    echo "✅ Configuration file already exists"
fi

if [ ! -f "$CONFIG_DIR/routing_config.yaml" ]; then
    cp routing_config.yaml.example "$CONFIG_DIR/routing_config.yaml"
    echo "📝 Edit $CONFIG_DIR/routing_config.yaml with your routes"
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
echo "      curl http://localhost:9090/health"
echo ""
