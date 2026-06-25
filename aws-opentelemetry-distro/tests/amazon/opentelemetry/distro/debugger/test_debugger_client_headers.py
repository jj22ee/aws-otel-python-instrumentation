# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the DI client's environment-resolution headers.

The DI client forwards the pod-owned environment inputs (k8s namespace, explicit
deployment environment) to the CloudWatch agent proxy as request headers, so the
agent can resolve the same aws.local.environment that Application Signals uses.
"""
import unittest
from unittest.mock import MagicMock, patch

from amazon.opentelemetry.distro.debugger._debugger_client import DebuggerClient


def _client_with_resource(attributes):
    """Build a DebuggerClient whose OTel Resource exposes the given attributes."""
    client = DebuggerClient(probe_poll_interval=600, breakpoint_poll_interval=60, api_url="http://localhost:2000")
    provider = MagicMock()
    provider.resource.attributes = attributes
    return client, provider


class TestDebuggerClientHeaders(unittest.TestCase):
    def test_namespace_resolved_from_resource(self):
        client, provider = _client_with_resource({"k8s.namespace.name": "default"})
        with patch(
            "amazon.opentelemetry.distro.debugger._debugger_client.trace.get_tracer_provider",
            return_value=provider,
        ):
            self.assertEqual("default", client.namespace)

    def test_namespace_empty_when_absent(self):
        client, provider = _client_with_resource({"service.name": "svc"})
        with patch(
            "amazon.opentelemetry.distro.debugger._debugger_client.trace.get_tracer_provider",
            return_value=provider,
        ):
            self.assertEqual("", client.namespace)

    def test_environment_headers_include_namespace_and_explicit_env(self):
        client, provider = _client_with_resource(
            {"k8s.namespace.name": "default", "deployment.environment.name": "sample-env"}
        )
        with patch(
            "amazon.opentelemetry.distro.debugger._debugger_client.trace.get_tracer_provider",
            return_value=provider,
        ):
            headers = client._environment_headers()
        self.assertEqual("default", headers["X-Aws-K8s-Namespace"])
        self.assertEqual("sample-env", headers["X-Aws-Deployment-Environment"])

    def test_environment_headers_omit_namespace_when_absent(self):
        client, provider = _client_with_resource({"deployment.environment.name": "sample-env"})
        with patch(
            "amazon.opentelemetry.distro.debugger._debugger_client.trace.get_tracer_provider",
            return_value=provider,
        ):
            headers = client._environment_headers()
        self.assertNotIn("X-Aws-K8s-Namespace", headers)
        self.assertEqual("sample-env", headers["X-Aws-Deployment-Environment"])

    def test_environment_headers_omit_env_when_unresolved(self):
        # No deployment.environment* on the resource -> environment property returns
        # "UnknownEnvironment", which must NOT be forwarded as a real value.
        client, provider = _client_with_resource({"k8s.namespace.name": "default"})
        with patch(
            "amazon.opentelemetry.distro.debugger._debugger_client.trace.get_tracer_provider",
            return_value=provider,
        ):
            headers = client._environment_headers()
        self.assertEqual("default", headers["X-Aws-K8s-Namespace"])
        self.assertNotIn("X-Aws-Deployment-Environment", headers)

    def test_environment_headers_empty_for_non_k8s_no_env(self):
        client, provider = _client_with_resource({"service.name": "svc"})
        with patch(
            "amazon.opentelemetry.distro.debugger._debugger_client.trace.get_tracer_provider",
            return_value=provider,
        ):
            headers = client._environment_headers()
        self.assertEqual({}, headers)


if __name__ == "__main__":
    unittest.main()
