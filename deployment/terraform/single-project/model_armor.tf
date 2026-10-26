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

# PII redaction and prompt safety with managed Google Cloud services:
#   Sensitive Data Protection (DLP) inspect + de-identify templates
#   -> referenced by a Model Armor template
#   -> enforced in the agent by ADK's ModelArmorPlugin (blob/app_utils/guardrails.py)
#      on prompts, responses, and tool outputs.
#
# Model Armor and the SDP templates it references must be in the same location.

locals {
  model_armor_location = var.region
  model_armor_template_name = (
    "projects/${var.project_id}/locations/${local.model_armor_location}/templates/${var.project_name}-guardrails"
  )
}

resource "google_project_service_identity" "model_armor_sa" {
  provider = google-beta
  project  = var.project_id
  service  = "modelarmor.googleapis.com"

  depends_on = [google_project_service.services]
}

# Model Armor calls SDP on the project's behalf to inspect and de-identify.
resource "google_project_iam_member" "model_armor_sa_dlp" {
  for_each = toset(["roles/dlp.user", "roles/dlp.reader"])

  project = var.project_id
  role    = each.value
  member  = google_project_service_identity.model_armor_sa.member
}

resource "google_data_loss_prevention_inspect_template" "pii" {
  parent       = "projects/${var.project_id}/locations/${local.model_armor_location}"
  template_id  = "${var.project_name}-pii-inspect"
  display_name = "${var.project_name} PII inspection"
  description  = "PII and credential info types screened by Model Armor."

  inspect_config {
    min_likelihood = "LIKELY"

    dynamic "info_types" {
      for_each = var.pii_info_types
      content {
        name = info_types.value
      }
    }
  }

  depends_on = [google_project_service.services]
}

resource "google_data_loss_prevention_deidentify_template" "pii" {
  parent       = "projects/${var.project_id}/locations/${local.model_armor_location}"
  template_id  = "${var.project_name}-pii-deidentify"
  display_name = "${var.project_name} PII de-identification"
  description  = "Replaces detected PII with its info type, e.g. [EMAIL_ADDRESS]."

  deidentify_config {
    info_type_transformations {
      transformations {
        primitive_transformation {
          replace_with_info_type_config = true
        }
      }
    }
  }

  depends_on = [google_project_service.services]
}

resource "google_model_armor_template" "guardrails" {
  location    = local.model_armor_location
  template_id = "${var.project_name}-guardrails"

  filter_config {
    sdp_settings {
      advanced_config {
        inspect_template    = google_data_loss_prevention_inspect_template.pii.id
        deidentify_template = google_data_loss_prevention_deidentify_template.pii.id
      }
    }

    pi_and_jailbreak_filter_settings {
      filter_enforcement = "ENABLED"
      confidence_level   = "MEDIUM_AND_ABOVE"
    }

    malicious_uri_filter_settings {
      filter_enforcement = "ENABLED"
    }
  }

  template_metadata {
    # Audit sanitize calls in Cloud Logging (findings only, not payloads).
    log_sanitize_operations = true
    log_template_operations = true
  }

  depends_on = [
    google_project_service.services,
    google_project_iam_member.model_armor_sa_dlp,
  ]
}
