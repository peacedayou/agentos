#!/usr/bin/env bash
cd "$(dirname "$0")"
echo "=== AgentOS ==="; echo "1. Nouvelle mission"; echo "2. Conversation"; echo "3. Mode système (daemon)"
read -rp "Choix : " c
case $c in
  1) read -rp "Mission : " m; python3 -m agentos run "$m";;
  2) python3 -m agentos chat;;
  3) python3 -m agentos daemon;;
esac
