# Quick Troubleshooting Guide

Common scenarios and quick-fixes when running the Kubernetes Troubleshooting Agent.

---

## 1. Local Development & Demo Mode

### Q: I don't have a Kubernetes cluster running. Can I test the agent?
**Yes.** The agent includes an automatic **Demo Mode**. If no `KUBECONFIG` file or cluster is found, the agent starts in simulation mode with realistic failure scenarios:
- Payment processor in `CrashLoopBackOff`
- Web frontend in `ImagePullBackOff`
- Machine learning worker `OOMKilled` (Exit code 137)
- Spark analytics pod stuck in `Pending` due to insufficient memory
- Auth gateway failing liveness probe
- Internal service with missing endpoints

Simply run:
```bash
python scripts/run_demo.py
```
Or start via uvicorn:
```bash
uvicorn app.main:app --port 8000
```

---

## 2. Connecting to a Live Cluster

### Minikube
```bash
minikube start
kubectl config current-context  # Verify context points to minikube
export KUBECONFIG=~/.kube/config
python -m uvicorn app.main:app --port 8000
```

### Kind (Kubernetes in Docker)
```bash
kind create cluster --name dev-cluster
kubectl cluster-info --context kind-dev-cluster
python -m uvicorn app.main:app --port 8000
```

---

## 3. Configuring AI Providers

### Offline Mode (Default)
No setup required. The local rule-based engine generates high-fidelity reports instantly with zero API charges.

### AWS Bedrock
Set environment variables:
```bash
export AI_PROVIDER=bedrock
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
```
*Note: If AWS credentials are missing or the call fails, the agent automatically falls back to rule-based analysis.*

### OpenAI
```bash
export AI_PROVIDER=openai
export OPENAI_API_KEY=your_api_key
export OPENAI_MODEL=gpt-4o-mini
```
