#!/bin/bash

# Configuration: Update APP_DIR if your KylinOS username is different
APP_DIR="/root/workspace/locationmap/dashboard" 
VENV_DIR="$APP_DIR/venv"
PID_FILE="$APP_DIR/app.pid"
LOG_FILE="$APP_DIR/app.log"

cd $APP_DIR || exit 1

case "$1" in
    start)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo "App is already running (PID: $(cat $PID_FILE))"
        else
            echo "Starting Flask app on KylinOS..."
            source $VENV_DIR/bin/activate
            # Run in background and detach
            nohup flask run --host=0.0.0.0 --port=5000 > "$LOG_FILE" 2>&1 &
            echo $! > "$PID_FILE"
            echo "App started in background (PID: $(cat $PID_FILE))"
            echo "Logs are being written to $LOG_FILE"
        fi
        ;;
    stop)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            echo "Stopping Flask app (PID: $PID)..."
            kill $PID 2>/dev/null
            rm -f "$PID_FILE"
            echo "App stopped."
        else
            echo "PID file not found. Is the app running?"
        fi
        ;;
    status)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo "App is RUNNING (PID: $(cat $PID_FILE))"
        else
            echo "App is STOPPED"
        fi
        ;;
    *)
        echo "Usage: ./manage.sh {start|stop|status}"
        exit 1
        ;;
esac
