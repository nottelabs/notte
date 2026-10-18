package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"
)

type apiClient struct {
	endpoint, key string
	http          *http.Client
}
type profile struct {
	ID   string  `json:"profile_id"`
	Name *string `json:"name"`
}
type apiError struct {
	status int
	kind   string
}

func (e *apiError) Error() string { return fmt.Sprintf("Notte API returned HTTP %d", e.status) }

var validID = regexp.MustCompile(`^[A-Za-z0-9_-]{1,200}$`)

func newClient(endpoint, key string) (*apiClient, error) {
	u, err := url.Parse(endpoint)
	if err != nil || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || (u.Scheme != "https" && !(u.Scheme == "http" && (u.Hostname() == "127.0.0.1" || u.Hostname() == "localhost" || u.Hostname() == "::1"))) {
		return nil, fmt.Errorf("Use an HTTPS Notte API endpoint, or HTTP loopback for local tests")
	}
	if strings.TrimSpace(key) == "" {
		return nil, fmt.Errorf("Set NOTTE_API_KEY or api_key")
	}
	return &apiClient{endpoint: strings.TrimRight(endpoint, "/"), key: key, http: &http.Client{Timeout: 30 * time.Second, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}}, nil
}

func (c *apiClient) request(ctx context.Context, method, path string, body any, result any) error {
	var data []byte
	var err error
	if body != nil {
		data, err = json.Marshal(body)
		if err != nil {
			return fmt.Errorf("Invalid Notte API request")
		}
	}
	req, err := http.NewRequestWithContext(ctx, method, c.endpoint+path, bytes.NewReader(data))
	if err != nil {
		return fmt.Errorf("Invalid Notte API request")
	}
	req.Header.Set("Authorization", "Bearer "+c.key)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-notte-request-origin", "terraform")
	response, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("Notte API request failed")
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return &apiError{status: response.StatusCode, kind: response.Header.Get("X-Error-Class")}
	}
	if result != nil {
		if err := json.NewDecoder(io.LimitReader(response.Body, 1<<20)).Decode(result); err != nil {
			return fmt.Errorf("Invalid Notte API response")
		}
	}
	return nil
}

func (c *apiClient) create(ctx context.Context, name *string) (*profile, error) {
	var result profile
	if err := c.request(ctx, http.MethodPost, "/profiles/create", map[string]any{"name": name}, &result); err != nil {
		return nil, err
	}
	if !validID.MatchString(result.ID) {
		return nil, fmt.Errorf("Notte returned an invalid profile ID")
	}
	return &result, nil
}
func (c *apiClient) get(ctx context.Context, id string) (*profile, error) {
	if !validID.MatchString(id) {
		return nil, fmt.Errorf("Invalid Notte profile ID")
	}
	var result profile
	err := c.request(ctx, http.MethodGet, "/profiles/"+url.PathEscape(id), nil, &result)
	if api, ok := err.(*apiError); ok && (api.status == 404 || (api.status == 400 && api.kind == "ProfileAlreadyClosedError")) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	if result.ID != id {
		return nil, fmt.Errorf("Notte returned a different profile ID")
	}
	return &result, nil
}
func (c *apiClient) delete(ctx context.Context, id string) error {
	if !validID.MatchString(id) {
		return fmt.Errorf("Invalid Notte profile ID")
	}
	var result struct {
		Success bool `json:"success"`
	}
	err := c.request(ctx, http.MethodDelete, "/profiles/"+url.PathEscape(id), nil, &result)
	if api, ok := err.(*apiError); ok && (api.status == 404 || (api.status == 400 && api.kind == "ProfileAlreadyClosedError")) {
		return nil
	}
	if err != nil {
		return err
	}
	if !result.Success {
		return fmt.Errorf("Notte did not confirm profile deletion")
	}
	return nil
}
