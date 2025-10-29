#!/bin/bash
set -e

echo "🔧 Fixing permissions..."
# Fix permissions for mounted volume (run as root first)
sudo chown -R octo:octo "/home/octo/.Octo Browser" 2>/dev/null || true
sudo chmod -R 755 "/home/octo/.Octo Browser" 2>/dev/null || true

# Create necessary directories
mkdir -p "/home/octo/.Octo Browser/logs"
mkdir -p "/home/octo/.Octo Browser/tmp"
mkdir -p "/home/octo/.Octo Browser/profiles"

echo "🚀 Starting Xvfb..."
rm -f /tmp/.X1-lock
Xvfb :1 -ac -screen 0 "1920x1080x24" -nolisten tcp +extension GLX +render -noreset &
XVFB_PID=$!
echo "✅ Xvfb started with PID $XVFB_PID"

sleep 3

echo "🚀 Starting Octo Browser..."
OCTO_HEADLESS=1 /home/octo/browser/OctoBrowser.AppImage || {
    echo "❌ Octo Browser failed to start"
    kill $XVFB_PID
    exit 1
}

