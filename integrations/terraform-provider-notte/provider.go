package main

import (
	"context"
	"os"

	"github.com/hashicorp/terraform-plugin-framework/datasource"
	"github.com/hashicorp/terraform-plugin-framework/provider"
	"github.com/hashicorp/terraform-plugin-framework/provider/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/types"
)

type notteProvider struct{}
type providerConfig struct {
	APIKey   types.String `tfsdk:"api_key"`
	Endpoint types.String `tfsdk:"endpoint"`
}

func (*notteProvider) Metadata(_ context.Context, _ provider.MetadataRequest, resp *provider.MetadataResponse) {
	resp.TypeName = "notte"
	resp.Version = "0.1.0-dev"
}
func (*notteProvider) Schema(_ context.Context, _ provider.SchemaRequest, resp *provider.SchemaResponse) {
	resp.Schema = schema.Schema{Description: "Manage durable Notte profiles.", Attributes: map[string]schema.Attribute{
		"api_key":  schema.StringAttribute{Optional: true, Sensitive: true, Description: "Notte API key; defaults to NOTTE_API_KEY."},
		"endpoint": schema.StringAttribute{Optional: true, Description: "Notte API origin; defaults to NOTTE_API_URL or https://api.notte.cc."},
	}}
}
func (*notteProvider) Configure(ctx context.Context, req provider.ConfigureRequest, resp *provider.ConfigureResponse) {
	var config providerConfig
	resp.Diagnostics.Append(req.Config.Get(ctx, &config)...)
	if resp.Diagnostics.HasError() {
		return
	}
	if config.APIKey.IsUnknown() || config.Endpoint.IsUnknown() {
		resp.Diagnostics.AddError("Unknown provider configuration", "API key and endpoint must be known before using Notte resources.")
		return
	}
	key, endpoint := os.Getenv("NOTTE_API_KEY"), os.Getenv("NOTTE_API_URL")
	if !config.APIKey.IsNull() {
		key = config.APIKey.ValueString()
	}
	if !config.Endpoint.IsNull() {
		endpoint = config.Endpoint.ValueString()
	}
	if endpoint == "" {
		endpoint = "https://api.notte.cc"
	}
	client, err := newClient(endpoint, key)
	if err != nil {
		resp.Diagnostics.AddError("Invalid Notte configuration", err.Error())
		return
	}
	resp.ResourceData = client
}
func (*notteProvider) Resources(context.Context) []func() resource.Resource {
	return []func() resource.Resource{func() resource.Resource { return &profileResource{} }}
}
func (*notteProvider) DataSources(context.Context) []func() datasource.DataSource { return nil }
