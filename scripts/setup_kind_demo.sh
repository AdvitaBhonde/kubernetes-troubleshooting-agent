#!/usr/bin/env bash
# Sets up a local KinD (Kubernetes in Docker) cluster and deploys sample failure scenarios
set -e

CLUSTER_NAME="k8s-troubleshooter-demo"

echo "Creating KinD cluster: $CLUSTER_NAME..."
kind create cluster --name "$CLUSTER_NAME" || true

echo "Applying broken demo workloads..."
kubectl apply -f k8s/demo-scenarios/

echo "Demo cluster ready! Run agent with:"
echo "export KUBECONFIG=~/.kube/config"
echo "python scripts/run_demo.py"
