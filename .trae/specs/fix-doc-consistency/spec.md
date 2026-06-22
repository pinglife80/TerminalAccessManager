# Fix Documentation Consistency Spec

## Why
Multiple documentation files across the TerminalAccessManager project contain outdated terminology, missing API endpoints, incorrect default values, and inconsistent version numbers following recent code changes (blacklist page redesign, MAC-precise unblock, rate limit updates, SVG deprecation, disable-preview endpoint, permission code renames).

## What Changes
- **api.md**: Fix `unfrozen` → `unblocked` in example response; update rate limit defaults from 60/5 to 120/10; add `mac_address` query parameter to unblock endpoint; add deprecation notice to `POST /blacklist/`; add new `POST /data-sources/{id}/disable-preview` section; update version to v3.2.0-r11
- **RBAC.md**: Change `blacklist:write` description from "添加/解封" to "解封"; add deprecation note to `POST /blacklist/` endpoint mapping; add delete-preview and disable-preview endpoint permission mappings; change Blacklist page "封禁终端" to "解封终端"; update version to v3.2.0-r11
- **datasource-lifecycle.md**: Add 7 new API endpoint entries (delete-preview × 3, disable-preview, and related); change `datasource:delete` → `datasource:write` (2 places); change `baseline:delete` → `baseline:write`; update version to v3.2.0-r11
- **architecture.md**: Change block action for `unknown + unblocked` state from available to "—" (disabled); update version to v3.2.0-r11
- **backend.md**: Add `mac_address` parameter to `unblock_ip()` function signature; update rate limit defaults from 60/5 to 120/10 (2 places); update version to v3.2.0-r11
- **branding.md**: Remove SVG from file format recommendations, add XSS risk note; update version from v3.2.0-r8 to v3.2.0-r11
- **implementation.md**: Remove "添加黑名单条目" description line; remove `POST /api/v1/blacklist/` integration point; update version to v3.2.0-r11
- **production-readiness-assessment.md**: Add logging-guide.md and git-workflow-guide.md to document inventory table; fix version alignment in table; change `VERSION=2.0.0` to `VERSION=3.2.0`; update version to v3.2.0-r11
- **Version header updates (Task 20)**: Update version headers to `v3.2.0-r11` with date `2026-06-16` in: deployment.md (r8→r11), manage-sh-reference.md (r8→r11), logging-guide.md (r8→r11), git-workflow-guide.md (v1.0→r11), database.md (r10→r11), changelog.md (add version if missing), release-notes.md (update TBD + add disable-preview entry)

## Impact
- Affected docs: api.md, RBAC.md, datasource-lifecycle.md, architecture.md, backend.md, branding.md, implementation.md, production-readiness-assessment.md, deployment.md, manage-sh-reference.md, logging-guide.md, git-workflow-guide.md, database.md, changelog.md, release-notes.md
- No code changes required — documentation-only changes

## ADDED Requirements

### Requirement: Disable-Preview API Documentation
The API documentation SHALL include a new section for `POST /data-sources/{id}/disable-preview` endpoint that documents the disable preview functionality for data sources.

#### Scenario: User reads API docs for disable-preview
- **WHEN** user navigates to the data source section of api.md
- **THEN** they find documentation for `POST /data-sources/{id}/disable-preview` with request/response format

### Requirement: Delete-Preview and Disable-Preview Permission Mappings
RBAC.md and datasource-lifecycle.md SHALL document the permission mappings for delete-preview endpoints (`datasource:read`) and disable-preview endpoint (`datasource:read`).

#### Scenario: User checks permissions for preview endpoints
- **WHEN** user looks up endpoint-permission mappings
- **THEN** delete-preview and disable-preview endpoints are listed with `datasource:read` permission

## MODIFIED Requirements

### Requirement: Blacklist Write Permission Description
`blacklist:write` permission description SHALL be "解封黑名单条目" (not "添加/解封黑名单条目"), reflecting the removal of manual add functionality.

### Requirement: Unblock Endpoint Documentation
The `POST /terminals/unblock/{ip_address}` endpoint documentation SHALL include the `mac_address` query parameter for MAC-precise unblocking.

### Requirement: Rate Limit Defaults
All documentation referencing rate limit defaults SHALL show `rate_limit_per_minute: 120` and `auth_rate_limit_per_minute: 10` (not 60/5).

### Requirement: Terminal Status Terminology
All documentation SHALL use `unblocked` (not `unfrozen`) for terminal status.

### Requirement: Permission Codes for Delete Operations
Delete operations for data sources and bindings SHALL use `datasource:write` permission (not `datasource:delete`). Delete operations for compliance baselines SHALL use `baseline:write` permission (not `baseline:delete`).

### Requirement: Unknown Status Block Action
The operation button matrix in architecture.md SHALL show block action as disabled ("—") for terminals with `unknown` compliance status and `unblocked` block status.

### Requirement: SVG Deprecation in Branding
The branding.md file format recommendations SHALL NOT include SVG. A note SHALL be added about XSS risk with SVG uploads.

### Requirement: Document Version Consistency
All documentation files SHALL have version header `v3.2.0-r11` with date `2026-06-16`.

## REMOVED Requirements

### Requirement: Manual Blacklist Add Documentation
**Reason**: The manual add blacklist feature has been removed from the Blacklist management page. Block operations are now unified under Terminal management.
**Migration**: POST /blacklist/ endpoint documentation receives a deprecation notice; implementation.md references to blacklist add are removed.
