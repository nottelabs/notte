# Notte profiles for Terraform

This original native provider manages durable Notte browser profiles through the existing API. It supports create, read, delete, import, and drift detection. It uses the unmodified HashiCorp Plugin Framework. Project and browser-pool management are unsupported.

The provider is source-distributed here and has not been published to the Terraform Registry. Use Go 1.27.2+ and Terraform 1.16.6 (the tested CLI version). Build with `go build -o bin/terraform-provider-notte .`. Copy `dev.tfrc.example` to a private `terraform.rc`, replace the plugin directory with your absolute `bin` path, and set `TF_CLI_CONFIG_FILE` to that file's absolute path. This uses Terraform's [development override](https://developer.hashicorp.com/terraform/cli/config/config-file#development-overrides-for-provider-developers); skip registry installation with `terraform init` for this local setup.

Set `NOTTE_API_KEY`, then use `examples/profile.tf` from your intended Terraform workspace. `NOTTE_API_URL` optionally selects another Notte API. The provider's optional `api_key` and `endpoint` fields override those variables; environment-based authentication keeps credentials out of configuration files.

Review `terraform plan` before applying changes through your usual review workflow. Import an existing profile with `terraform import notte_profile.automation PROFILE_ID`. Use the resulting `profile_id` with your browser automation.

Changing `name` replaces the profile because the API has no metadata-update operation. Deleting or replacing a profile removes its saved browser state. Use Terraform's `lifecycle.prevent_destroy` when you need to protect an important profile. Cookies, storage contents, authenticated browser URLs and API keys are not resource attributes.

`go test -race ./...` checks wire contracts and safe failure handling. `TERRAFORM_BIN=/path/to/terraform python -m unittest test_cli -v` runs actual native CLI lifecycle, import, replacement, drift and failure cases against an isolated loopback API fixture. With an explicit `NOTTE_API_URL`, `NOTTE_API_KEY` and `NOTTE_TERRAFORM_LIVE=1`, `go test -run '^TestLiveProfileWire$' -v .` checks an owned application profile's real create/get/delete lifecycle without applying live infrastructure.
