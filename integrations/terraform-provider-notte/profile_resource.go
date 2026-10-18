package main

import (
	"context"

	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/stringplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/types"
)

type profileResource struct{ client *apiClient }
type profileState struct {
	ID   types.String `tfsdk:"id"`
	Name types.String `tfsdk:"name"`
}

var _ resource.ResourceWithConfigure = (*profileResource)(nil)
var _ resource.ResourceWithImportState = (*profileResource)(nil)

func (*profileResource) Metadata(_ context.Context, req resource.MetadataRequest, resp *resource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_profile"
}
func (*profileResource) Schema(_ context.Context, _ resource.SchemaRequest, resp *resource.SchemaResponse) {
	resp.Schema = schema.Schema{Description: "A durable Notte browser profile. Changing its name replaces it; profile contents are managed by browser sessions, not Terraform.", Attributes: map[string]schema.Attribute{
		"id":   schema.StringAttribute{Computed: true, Description: "Stable Notte profile ID.", PlanModifiers: []planmodifier.String{stringplanmodifier.UseStateForUnknown()}},
		"name": schema.StringAttribute{Optional: true, Computed: true, Description: "Profile name. Changes require replacement because the API has no metadata-update operation.", PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace(), stringplanmodifier.UseStateForUnknown()}},
	}}
}
func (r *profileResource) Configure(_ context.Context, req resource.ConfigureRequest, resp *resource.ConfigureResponse) {
	if req.ProviderData == nil {
		return
	}
	client, ok := req.ProviderData.(*apiClient)
	if !ok {
		resp.Diagnostics.AddError("Invalid Notte provider", "Expected a configured Notte API client.")
		return
	}
	r.client = client
}
func (r *profileResource) Create(ctx context.Context, req resource.CreateRequest, resp *resource.CreateResponse) {
	var state profileState
	resp.Diagnostics.Append(req.Plan.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	var name *string
	if !state.Name.IsNull() && !state.Name.IsUnknown() {
		value := state.Name.ValueString()
		name = &value
	}
	created, err := r.client.create(ctx, name)
	if err != nil {
		resp.Diagnostics.AddError("Could not create Notte profile", err.Error())
		return
	}
	state.ID = types.StringValue(created.ID)
	state.Name = types.StringPointerValue(created.Name)
	resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
}
func (r *profileResource) Read(ctx context.Context, req resource.ReadRequest, resp *resource.ReadResponse) {
	var state profileState
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	current, err := r.client.get(ctx, state.ID.ValueString())
	if err != nil {
		resp.Diagnostics.AddError("Could not read Notte profile", err.Error())
		return
	}
	if current == nil {
		resp.State.RemoveResource(ctx)
		return
	}
	state.Name = types.StringPointerValue(current.Name)
	resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
}
func (*profileResource) Update(_ context.Context, _ resource.UpdateRequest, resp *resource.UpdateResponse) {
	resp.Diagnostics.AddError("Profile replacement required", "Notte does not support profile metadata updates. Change the name through a replacement plan.")
}
func (r *profileResource) Delete(ctx context.Context, req resource.DeleteRequest, resp *resource.DeleteResponse) {
	var state profileState
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	if err := r.client.delete(ctx, state.ID.ValueString()); err != nil {
		resp.Diagnostics.AddError("Could not delete Notte profile", err.Error())
	}
}
func (*profileResource) ImportState(ctx context.Context, req resource.ImportStateRequest, resp *resource.ImportStateResponse) {
	if !validID.MatchString(req.ID) {
		resp.Diagnostics.AddError("Invalid profile ID", "Import a stable Notte profile ID.")
		return
	}
	resource.ImportStatePassthroughID(ctx, path.Root("id"), req, resp)
}
