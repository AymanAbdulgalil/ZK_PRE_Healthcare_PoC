#!/bin/sh
set -e

# Remove any old deployment file: the healthcheck must pass only after this run deploys.
rm -f /app/deployments/AccessControl.json

echo "[ledger] starting Hardhat node on 0.0.0.0:8545 ..."
npx hardhat node --hostname 0.0.0.0 --port 8545 &
NODE_PID=$!

echo "[ledger] waiting for RPC to accept connections..."
until curl -s -o /dev/null -X POST \
  -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' \
  http://127.0.0.1:8545
do
  sleep 1
done

echo "[ledger] RPC is up, deploying AccessControl.sol ..."
npx hardhat run scripts/deploy.js --network localhost

echo "[ledger] ready -- deployment info at /app/deployments/AccessControl.json"

# Container lifecycle follows the node.
wait "$NODE_PID"
