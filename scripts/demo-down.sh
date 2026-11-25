#!/usr/bin/env bash
# Removes the demonstration cluster.
set -euo pipefail
kind delete cluster --name shopping
