terraform {
  required_providers {
    notte = {
      source = "nottelabs/notte"
    }
  }
}

provider "notte" {}

resource "notte_profile" "automation" {
  name = "automation"
}

output "profile_id" {
  value = notte_profile.automation.id
}
