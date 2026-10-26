# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for strategic model routing and Model Armor guardrail wiring."""

from __future__ import annotations

import pytest

from blob.agent import cluster_analyst, root_agent, wiki_curator
from blob.app_utils.guardrails import (
    MODEL_ARMOR_DEIDENTIFY_ENV,
    MODEL_ARMOR_TEMPLATE_ENV,
    build_guardrail_plugins,
)
from blob.app_utils.model_router import (
    COMPLEX_MODEL,
    FAST_MODEL,
    model_name_for_agent,
    tier_for_agent,
)

_TEMPLATE = "projects/test-project/locations/us-east1/templates/blob-guardrails"


def test_default_model_tiers() -> None:
    assert FAST_MODEL == "gemini-3.8-flash"
    assert COMPLEX_MODEL == "gemini-4-argon"


def test_agents_are_routed_by_role() -> None:
    # User-facing and simple tasks -> fast tier.
    assert root_agent.model.model == FAST_MODEL
    assert cluster_analyst.model.model == FAST_MODEL
    # Multi-episode synthesis and contradiction resolution -> complex tier.
    assert wiki_curator.model.model == COMPLEX_MODEL


def test_unknown_agent_defaults_to_fast_tier() -> None:
    assert tier_for_agent("something_new") == "fast"
    assert model_name_for_agent("something_new") == FAST_MODEL


def test_guardrails_disabled_without_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(MODEL_ARMOR_TEMPLATE_ENV, raising=False)
    assert build_guardrail_plugins() == []


def test_guardrails_enable_model_armor_deidentification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from google.adk.integrations.model_armor import ModelArmorPlugin

    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, _TEMPLATE)
    monkeypatch.delenv(MODEL_ARMOR_DEIDENTIFY_ENV, raising=False)

    plugins = build_guardrail_plugins()

    assert len(plugins) == 1
    plugin = plugins[0]
    assert isinstance(plugin, ModelArmorPlugin)
    config = plugin._config
    assert config.prompt_template_name == _TEMPLATE
    assert config.response_template_name == _TEMPLATE
    assert config.tool_output_template_name == _TEMPLATE
    assert config.deidentify_sensitive_data is True
    assert config.block_on_screening_failure is True


def test_guardrails_can_block_instead_of_deidentify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, _TEMPLATE)
    monkeypatch.setenv(MODEL_ARMOR_DEIDENTIFY_ENV, "false")

    (plugin,) = build_guardrail_plugins()

    assert plugin._config.deidentify_sensitive_data is False
