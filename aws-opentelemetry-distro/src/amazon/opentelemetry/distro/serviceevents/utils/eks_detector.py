# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""EXPERIMENT: SDK-side EKS detection, ported from the CloudWatch agent's eksdetector.

Mirrors amazon-cloudwatch-agent/translator/util/eksdetector/eksdetector.go so the SDK can
decide the eks: vs k8s: Environment prefix from the SAME runtime signal the agent uses,
instead of trusting an operator-injected cloud.platform value (which is driven by the static
Helm .Values.k8sMode and is wrong for native K8s when left at its EKS default).

Detection (matching the agent, cached once per process):
  1. Fast path: IRSA / Pod Identity env vars
       AWS_WEB_IDENTITY_TOKEN_FILE contains "eks.amazonaws.com"  -> EKS
       AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE contains "eks-pod-identity" -> EKS
  2. Fallback: parse the in-cluster ServiceAccount token JWT, read the "iss" claim,
       and check whether it contains "eks" (case-insensitive).

Known gaps (shared with the agent's detector): custom/BYO OIDC issuers on EKS whose URL
lacks "eks" -> false negative; a self-managed cluster whose issuer URL contains "eks" ->
false positive; token not mounted/readable -> treated as non-EKS.
"""
import base64
import binascii
import json
import os

_SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"

_cached_is_eks = None  # process-wide memoization, mirroring the agent's once.Do


def _check_env_vars() -> bool:
    if "eks.amazonaws.com" in os.environ.get("AWS_WEB_IDENTITY_TOKEN_FILE", ""):
        return True
    if "eks-pod-identity" in os.environ.get("AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE", ""):
        return True
    return False


def _get_issuer() -> str:
    """Read the SA token and return its JWT 'iss' claim, or '' on any failure."""
    try:
        with open(_SA_TOKEN_PATH, "r", encoding="utf-8") as handle:
            token = handle.read().strip()
    except OSError:
        return ""
    if not token:
        return ""
    parts = token.split(".")
    if len(parts) < 2:
        return ""
    payload = parts[1]
    # JWT uses base64url without padding; restore padding for the stdlib decoder.
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload)
        claims = json.loads(decoded)
    except (binascii.Error, ValueError):
        return ""
    issuer = claims.get("iss")
    return issuer if isinstance(issuer, str) else ""


def is_eks() -> bool:
    """Return True if this process appears to run on EKS (cached after first call)."""
    global _cached_is_eks
    if _cached_is_eks is not None:
        return _cached_is_eks
    result = False
    if _check_env_vars():
        result = True
    else:
        issuer = _get_issuer()
        result = bool(issuer) and "eks" in issuer.lower()
    _cached_is_eks = result
    return result
