// Compiled into notte-cli's internal/auth package (through `go test -overlay`)
// by tests/sdk/test_cli_keyring_contract.py, so keys are stored by the CLI's
// own keyring code rather than by a reimplementation of its format.
package auth

import (
	"encoding/json"
	"os"
	"testing"
)

type contractOp struct {
	Op     string `json:"op"`
	APIURL string `json:"api_url"`
	Key    string `json:"key"`
	Value  string `json:"value"`
}

func TestSDKContractWriter(t *testing.T) {
	path := os.Getenv("NOTTE_SDK_CONTRACT_PLAN")
	if path == "" {
		t.Skip("NOTTE_SDK_CONTRACT_PLAN is not set")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var ops []contractOp
	if err := json.Unmarshal(data, &ops); err != nil {
		t.Fatal(err)
	}
	for _, op := range ops {
		t.Setenv("NOTTE_API_URL", op.APIURL)
		switch op.Op {
		case "set_api_key":
			err = SetKeyringAPIKey(op.Value)
		case "delete_api_key":
			// Cleanup of keys that may not exist.
			_ = DeleteKeyringAPIKey()
			err = nil
		case "set_secret":
			err = SetKeyringSecret(op.Key, op.Value)
		case "delete_secret":
			err = DeleteKeyringSecret(op.Key)
		default:
			t.Fatalf("unknown op %q", op.Op)
		}
		if err != nil {
			t.Fatalf("%s %s%s: %v", op.Op, op.APIURL, op.Key, err)
		}
	}
}
