package main

import (
	"context"
	"log"

	"github.com/hashicorp/terraform-plugin-framework/provider"
	"github.com/hashicorp/terraform-plugin-framework/providerserver"
)

func main() {
	if err := providerserver.Serve(context.Background(), func() provider.Provider { return &notteProvider{} }, providerserver.ServeOpts{Address: "registry.terraform.io/nottelabs/notte"}); err != nil {
		log.Fatal("Could not start the Notte provider")
	}
}
