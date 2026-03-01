# Manual Acceptance Runbooks

This document contains reproducible manual acceptance tests for features that cannot be fully automated in CI due to environment requirements (Docker availability, real LLM integration, etc.).

## Environment Setup

Before running any acceptance tests:

```bash
# 1. Start the application
docker compose up -d

# 2. Verify the server is running
curl http://localhost:8080/health

# 3. Access admin dashboard
open http://localhost:8080/admin/
# Login with password: admin
```

---

## Test Suite: HITL WebSocket Roundtrip

**Environment:** Any (Docker or local)
**Type:** Manual
**Priority:** Critical

### Test Case: HITL-001 - Approve Request via Admin Dashboard

**Steps:**
1. Open admin dashboard at `http://localhost:8080/admin/`
2. Login with admin password
3. Navigate to "HITL Queue" page
4. In a separate terminal, trigger a HITL-requiring operation:
   ```bash
   curl -X POST http://localhost:8080/api/tools/fs/write \
     -H "Content-Type: application/json" \
     -d '{"path": "test.conf", "content": "test content"}'
   ```
5. Verify a new request appears in the queue within 2 seconds
6. Click "Approve" on the request
7. Verify the request status changes to "Approved"
8. Verify the file was created in the workspace

**Expected Result:** Request appears in real-time, can be approved, and operation completes.

**Pass Criteria:**
- [ ] Request appears within 2 seconds
- [ ] Approve button works
- [ ] Status updates correctly
- [ ] File is created

### Test Case: HITL-002 - Reject Request via Admin Dashboard

**Steps:**
1. Open HITL Queue page
2. Trigger a HITL-requiring operation:
   ```bash
   curl -X POST http://localhost:8080/api/tools/shell/execute \
     -H "Content-Type: application/json" \
     -d '{"command": "echo test"}'
   ```
3. Verify request appears
4. Click "Reject" on the request
5. Verify the request status changes to "Rejected"
6. Verify the original API call returns an error

**Expected Result:** Request can be rejected and operation is blocked.

**Pass Criteria:**
- [ ] Request appears
- [ ] Reject button works
- [ ] Status updates to "Rejected"
- [ ] API call returns error

### Test Case: HITL-003 - Browser Notification

**Steps:**
1. Grant notification permission in browser for the admin site
2. Open a different tab (don't watch HITL Queue)
3. Trigger a HITL-requiring operation
4. Verify a browser notification appears

**Expected Result:** Browser notification shows pending HITL count.

**Pass Criteria:**
- [ ] Notification permission requested
- [ ] Notification appears when HITL request created
- [ ] Notification shows correct count

---

## Test Suite: Audit Log WebSocket Streaming

**Environment:** Any
**Type:** Manual
**Priority:** High

### Test Case: AUDIT-001 - Real-time Audit Log Updates

**Steps:**
1. Open Audit Log page in admin dashboard
2. Note the "Live" indicator in the header (green WiFi icon)
3. Execute a tool operation:
   ```bash
   curl -X POST http://localhost:8080/api/tools/fs/read \
     -H "Content-Type: application/json" \
     -d '{"path": "README.md"}'
   ```
4. Verify the new log entry appears within 2 seconds (without page refresh)

**Expected Result:** Log entries appear in real-time via WebSocket.

**Pass Criteria:**
- [ ] "Live" indicator shows green
- [ ] New log appears without refresh
- [ ] Timestamp is correct

### Test Case: AUDIT-002 - Polling Fallback

**Steps:**
1. Open browser DevTools (Network tab)
2. Filter for "ws" (WebSocket) connections
3. Close the WebSocket connection manually (or block via firewall)
4. Verify the indicator changes to "Polling" (yellow refresh icon)
5. Execute a tool operation
6. Verify logs still update (within 5 seconds)

**Expected Result:** Falls back to polling when WebSocket unavailable.

**Pass Criteria:**
- [ ] Indicator shows "Polling" when WebSocket disconnected
- [ ] Logs still update
- [ ] Reconnection attempts visible in console

---

## Test Suite: Container Log Viewer

**Environment:** Docker required
**Type:** Manual
**Priority:** Medium

### Test Case: CONTAINER-001 - List Containers

**Steps:**
1. Open Containers page in admin dashboard
2. Verify containers are listed
3. Verify status badges are correct (Running=green, Exited=red)

**Expected Result:** Container list shows all Docker containers.

**Pass Criteria:**
- [ ] Containers page loads
- [ ] Container list populated
- [ ] Status badges correct colors

### Test Case: CONTAINER-002 - View Container Logs

**Steps:**
1. Click on a running container
2. Verify logs appear in the viewer
3. Change "Last N" dropdown to 200
4. Click refresh button
5. Verify logs update

**Expected Result:** Can view and refresh container logs.

**Pass Criteria:**
- [ ] Logs load when container selected
- [ ] Dropdown changes log count
- [ ] Refresh button works

### Test Case: CONTAINER-003 - Docker Unavailable Handling

**Steps:**
1. Stop Docker daemon: `sudo systemctl stop docker`
2. Refresh Containers page
3. Verify error message appears
4. Start Docker: `sudo systemctl start docker`
5. Refresh and verify containers load

**Expected Result:** Graceful error handling when Docker unavailable.

**Pass Criteria:**
- [ ] Error message displayed
- [ ] No page crash
- [ ] Recovery when Docker restarts

---

## Test Suite: Tool Explorer OpenAPI Contract

**Environment:** Any
**Type:** Manual
**Priority:** High

### Test Case: TOOL-001 - Tool List Accuracy

**Steps:**
1. Open Tool Explorer page
2. Count total tools shown
3. Fetch OpenAPI spec: `curl http://localhost:8080/openapi.json | jq '.paths | keys | map(select(startswith("/api/tools/"))) | length'`
4. Verify counts match (or tool count <= OpenAPI paths due to sub-app duplication)

**Expected Result:** Tool count matches OpenAPI tool endpoints.

**Pass Criteria:**
- [ ] Tools listed
- [ ] Count matches or is less than OpenAPI paths
- [ ] Categories are correct

### Test Case: TOOL-002 - Schema Population

**Steps:**
1. Open Tool Explorer
2. Click on "fs_read" tool
3. Verify Input Schema shows actual schema (not empty `{}`)
4. Verify fields like `path` are visible in schema

**Expected Result:** Schemas are populated with actual field definitions.

**Pass Criteria:**
- [ ] Schema not empty
- [ ] Field names visible
- [ ] Types shown

### Test Case: TOOL-003 - HITL Indicators

**Steps:**
1. Open Tool Explorer
2. Find a tool marked as "Requires HITL" (yellow shield icon)
3. Find a tool marked as "Auto-Approved" (green checkmark)
4. Verify counts in stats cards match

**Expected Result:** HITL indicators accurately reflect policy configuration.

**Pass Criteria:**
- [ ] Some tools show HITL badge
- [ ] Some tools show Auto-Approved badge
- [ ] Stats cards show correct counts

---

## Test Suite: Admin Dashboard Responsiveness

**Environment:** Any
**Type:** Manual
**Priority:** Medium

### Test Case: MOBILE-001 - Mobile Layout

**Steps:**
1. Open admin dashboard in browser
2. Open DevTools and toggle device toolbar
3. Set to iPhone 12 Pro (390x844)
4. Navigate through all pages
5. Verify:
   - Sidebar collapses to hamburger menu
   - Cards stack vertically
   - Tables scroll horizontally
   - Buttons remain clickable

**Expected Result:** Dashboard is usable on mobile devices.

**Pass Criteria:**
- [ ] Hamburger menu works
- [ ] All pages accessible
- [ ] Tables scroll
- [ ] Buttons clickable

### Test Case: MOBILE-002 - Touch Interactions

**Steps:**
1. On a touch device (or Chrome touch emulation):
2. Open HITL Queue
3. Swipe/scroll through the list
4. Tap Approve/Reject buttons
5. Verify touch targets are adequate (44x44px minimum)

**Expected Result:** Touch interactions work correctly.

**Pass Criteria:**
- [ ] Scroll works
- [ ] Buttons respond to tap
- [ ] No accidental double-taps

---

## Test Suite: MCP Protocol

**Environment:** MCP Client required (Claude Desktop, etc.)
**Type:** Manual
**Priority:** Critical

### Test Case: MCP-001 - Tool Discovery

**Steps:**
1. Configure Claude Desktop to use AnyIDE MCP endpoint
2. Start a conversation
3. Ask: "What tools do you have available?"
4. Verify all 8 tool categories are listed

**Expected Result:** All tools discoverable via MCP.

**Pass Criteria:**
- [ ] Tools listed in Claude
- [ ] Categories correct
- [ ] Descriptions visible

### Test Case: MCP-002 - Tool Execution

**Steps:**
1. In Claude Desktop with AnyIDE configured:
2. Ask: "Read the README.md file from the workspace"
3. Verify Claude can execute fs_read tool
4. Verify file contents are returned

**Expected Result:** Tools executable via MCP.

**Pass Criteria:**
- [ ] Tool execution successful
- [ ] Results returned
- [ ] No errors

### Test Case: MCP-003 - HITL via MCP

**Steps:**
1. In Claude Desktop, ask to write to a .conf file
2. Verify HITL request appears in admin dashboard
3. Approve the request
4. Verify Claude receives confirmation

**Expected Result:** HITL workflow works through MCP.

**Pass Criteria:**
- [ ] HITL request created
- [ ] Request visible in dashboard
- [ ] Approval propagates to MCP client

---

## CI Integration Notes

These tests should be run:
- **On every release** (all tests)
- **Before merging to main** (critical tests only)
- **Nightly** (environment-dependent tests)

### Critical Tests (run before merge):
- HITL-001, HITL-002
- AUDIT-001
- TOOL-001, TOOL-002
- MCP-001, MCP-002

### Environment-Dependent Tests (run nightly):
- CONTAINER-001, CONTAINER-002, CONTAINER-003
- MCP-001, MCP-002, MCP-003 (requires MCP client)

### Tagging in CI

```yaml
# Example GitHub Actions tagging
- name: Run critical acceptance tests
  if: github.event_name == 'push'
  run: ./scripts/run-acceptance-tests.sh --critical

- name: Run all acceptance tests (nightly)
  if: github.event_name == 'schedule'
  run: ./scripts/run-acceptance-tests.sh --all
```

---

## Test Results Template

| Test ID | Date | Tester | Status | Notes |
|---------|------|--------|--------|-------|
| HITL-001 | YYYY-MM-DD | @name | PASS/FAIL | |
| HITL-002 | YYYY-MM-DD | @name | PASS/FAIL | |
| HITL-003 | YYYY-MM-DD | @name | PASS/FAIL | |
| AUDIT-001 | YYYY-MM-DD | @name | PASS/FAIL | |
| AUDIT-002 | YYYY-MM-DD | @name | PASS/FAIL | |
| CONTAINER-001 | YYYY-MM-DD | @name | PASS/FAIL | |
| CONTAINER-002 | YYYY-MM-DD | @name | PASS/FAIL | |
| CONTAINER-003 | YYYY-MM-DD | @name | PASS/FAIL | |
| TOOL-001 | YYYY-MM-DD | @name | PASS/FAIL | |
| TOOL-002 | YYYY-MM-DD | @name | PASS/FAIL | |
| TOOL-003 | YYYY-MM-DD | @name | PASS/FAIL | |
| MOBILE-001 | YYYY-MM-DD | @name | PASS/FAIL | |
| MOBILE-002 | YYYY-MM-DD | @name | PASS/FAIL | |
| MCP-001 | YYYY-MM-DD | @name | PASS/FAIL | |
| MCP-002 | YYYY-MM-DD | @name | PASS/FAIL | |
| MCP-003 | YYYY-MM-DD | @name | PASS/FAIL | |
