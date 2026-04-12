#!/bin/bash
# Background में Scanner (main.py) चलाएं
python main.py &

# Foreground में Bot Manager (premium_bot_manager.py) चलाएं
python premium_bot_manager.py
