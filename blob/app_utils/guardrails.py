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

"""PII redaction and prompt-safety guardrails backed by Google Cloud Model Armor.

Instead of maintaining in-house regexes, Blob relies on the managed
Model Armor service. Its Sensitive Data Protection (SDP) filter finds PII and
replaces it with info-type tokens such as ``[EMAIL_ADDRESS]``, using the inspect
and de-identify templates provisioned in
``deployment/terraform/single-project/model_armor.tf``.

ADK's built-in ``ModelArmorPlugin`` screens three things:

* user prompts, before they reach Gemini,
* model responses, before they reach the user,
* tool outputs (for example memories recalled from the knowledge store), before
  they go back into the model context.

Plugins registered on the ``App`` also apply to ``AgentTool`` sub-agents, so one
plugin covers ``blob``, ``wiki_curator``, and ``cluster_analyst``.

Configuration:

* ``BLOB_MODEL_ARMOR_TEMPLATE`` — full template name,
  ``projects/{project}/locations/{location}/templates/{template}``. When unset
  (local dev, unit tests), no guardrail is installed.
* ``BLOB_MODEL_ARMOR_DEIDENTIFY`` — ``true`` (default) passes de-identified text
  through instead of blocking the whole turn when PII is the only finding.
"""

from __future__ import annotations

import logging
import os

from google.adk.plugins.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

MODEL_ARMOR_TEMPLATE_ENV = "BLOB_MODEL_ARMOR_TEMPLATE"
MODEL_ARMOR_DEIDENTIFY_ENV = "BLOB_MODEL_ARMOR_DEIDENTIFY"


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def build_guardrail_plugins() -> list[BasePlugin]:
    """Return the ADK plugins that enforce PII redaction and prompt safety.

    Returns an empty list when ``BLOB_MODEL_ARMOR_TEMPLATE`` is not configured.
    """
    template = os.environ.get(MODEL_ARMOR_TEMPLATE_ENV, "").strip()
    if not template:
        logger.info(
            "Model Armor guardrails disabled: %s is not set.",
            MODEL_ARMOR_TEMPLATE_ENV,
        )
        return []

    from google.adk.integrations.model_armor import (
        ModelArmorConfig,
        ModelArmorPlugin,
    )

    config = ModelArmorConfig(
        prompt_template_name=template,
        response_template_name=template,
        tool_output_template_name=template,
        deidentify_sensitive_data=_env_flag(MODEL_ARMOR_DEIDENTIFY_ENV, True),
        # Fail closed: if Model Armor cannot be reached, do not let unscreened
        # content through.
        block_on_screening_failure=True,
    )
    logger.info("Model Armor guardrails enabled with template %s.", template)
    return [ModelArmorPlugin(config=config)]
