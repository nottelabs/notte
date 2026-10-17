package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

func TestProfileWireContract(t *testing.T) {
	name := "original"
	calls := []string{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-only" {
			t.Error("Missing API authentication")
		}
		calls = append(calls, r.Method+" "+r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		if r.Method == http.MethodDelete {
			_, _ = w.Write([]byte(`{"success":true}`))
			return
		}
		if r.Method == http.MethodPost {
			var body map[string]any
			if json.NewDecoder(r.Body).Decode(&body) != nil || len(body) != 1 || body["name"] != name {
				t.Error("Invalid profile create body")
			}
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"profile_id": "notte-profile-0123456789abcdef", "name": name, "cookies": "private-fixture-data"})
	}))
	defer server.Close()
	c, _ := newClient(server.URL, "test-only")
	p, err := c.create(context.Background(), &name)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = c.get(context.Background(), p.ID); err != nil {
		t.Fatal(err)
	}
	if err = c.delete(context.Background(), p.ID); err != nil {
		t.Fatal(err)
	}
	want := []string{"POST /profiles/create", "GET /profiles/notte-profile-0123456789abcdef", "DELETE /profiles/notte-profile-0123456789abcdef"}
	if strings.Join(calls, ",") != strings.Join(want, ",") {
		t.Fatalf("Unexpected wire paths: %v", calls)
	}
}

func TestProfileFailuresPreserveOwnershipAndHideDetails(t *testing.T) {
	for _, status := range []int{401, 403, 404, 429, 500} {
		t.Run(http.StatusText(status), func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(status)
				_, _ = w.Write([]byte("private-provider-detail test-only"))
			}))
			defer server.Close()
			c, _ := newClient(server.URL, "test-only")
			p, err := c.get(context.Background(), "valid-id")
			if status == 404 {
				if p != nil || err != nil {
					t.Fatal("Not-found must remove the missing resource")
				}
				return
			}
			if err == nil || strings.Contains(err.Error(), "private-provider-detail") || strings.Contains(err.Error(), "test-only") {
				t.Fatal("Expected safe failure diagnostics")
			}
		})
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { _, _ = w.Write([]byte(`{"success":false}`)) }))
	defer server.Close()
	c, _ := newClient(server.URL, "test-only")
	if c.delete(context.Background(), "valid-id") == nil {
		t.Fatal("Unconfirmed deletion cannot succeed")
	}
	if _, err := c.get(context.Background(), "../unowned"); err == nil {
		t.Fatal("Invalid IDs must be rejected")
	}
}

func TestClosedProfileTombstoneIsMissingButOtherBadRequestsFail(t *testing.T) {
	for _, kind := range []string{"ProfileAlreadyClosedError", "UnrelatedError", ""} {
		t.Run(kind, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.Header().Set("X-Error-Class", kind)
				w.WriteHeader(400)
			}))
			defer server.Close()
			client, _ := newClient(server.URL, "test-only")
			current, err := client.get(context.Background(), "valid-id")
			deleted := client.delete(context.Background(), "valid-id")
			if kind == "ProfileAlreadyClosedError" {
				if current != nil || err != nil || deleted != nil {
					t.Fatal("Closed tombstone must behave as a missing profile")
				}
			} else if err == nil || deleted == nil {
				t.Fatal("Unrelated HTTP400 cannot remove resource state")
			}
		})
	}
}

func TestClientRejectsCredentialRedirectsAndUnsafeOrigins(t *testing.T) {
	forwarded := false
	target := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { forwarded = true }))
	defer target.Close()
	redirect := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, target.URL, http.StatusTemporaryRedirect)
	}))
	defer redirect.Close()
	c, _ := newClient(redirect.URL, "test-only")
	if _, err := c.get(context.Background(), "valid-id"); err == nil || forwarded {
		t.Fatal("Credential-bearing requests must not follow redirects")
	}
	for _, endpoint := range []string{"http://example.com", "https://user:secret@example.com", "https://example.com?key=private", "https://example.com#private"} {
		if _, err := newClient(endpoint, "test-only"); err == nil {
			t.Fatal("Unsafe origin accepted")
		}
	}
}

func TestLiveProfileWire(t *testing.T) {
	if os.Getenv("NOTTE_TERRAFORM_LIVE") != "1" {
		t.Skip("Owned application-profile tests are opt-in")
	}
	if os.Getenv("NOTTE_API_URL") == "" || os.Getenv("NOTTE_API_KEY") == "" {
		t.Fatal("Choose the API and configure its test key")
	}
	c, err := newClient(os.Getenv("NOTTE_API_URL"), os.Getenv("NOTTE_API_KEY"))
	if err != nil {
		t.Fatal(err)
	}
	name := "terraform-integration-check-" + time.Now().UTC().Format("20060102T150405.000000000")
	p, err := c.create(context.Background(), &name)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := c.delete(context.Background(), p.ID); err != nil {
			t.Error(err)
		}
	})
	current, err := c.get(context.Background(), p.ID)
	if err != nil || current == nil || current.Name == nil || *current.Name != name {
		t.Fatal("Created profile did not round-trip")
	}
	if err := c.delete(context.Background(), p.ID); err != nil {
		t.Fatal(err)
	}
	current, err = c.get(context.Background(), p.ID)
	if err != nil || current != nil {
		t.Fatal("Owned profile deletion was not confirmed by GET")
	}
}
