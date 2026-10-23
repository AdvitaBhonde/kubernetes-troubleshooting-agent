#!/usr/bin/env python3
"""Launcher script for AI Kubernetes Troubleshooting Agent in Demo Mode."""

import os
import sys
import webbrowser
import uvicorn

if __name__ == "__main__":
    os.environ["DEMO_MODE"] = "true"
    os.environ["AI_PROVIDER"] = "rules"

    print("=" * 70)
    print("  🚀 Starting AI-Powered Kubernetes Troubleshooting Agent")
    print("  Mode: DEMO SIMULATION (No live Kubernetes cluster required)")
    print("  Dashboard: http://localhost:8000")
    print("  Swagger API Docs: http://localhost:8000/docs")
    print("=" * 70)

    try:
        webbrowser.open("http://localhost:8000")
    except Exception:
        pass

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
