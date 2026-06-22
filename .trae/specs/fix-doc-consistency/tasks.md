# Tasks

- [ ] Task 1: Fix api.md — 6 changes
  - [ ] 1.1: Line 909: Change `"status": "unfrozen"` to `"status": "unblocked"`
  - [ ] 1.2: Lines 2449-2450: Change rate limit defaults from `60` to `120` and `5` to `10`
  - [ ] 1.3: Lines 858-864: Add `mac_address` query parameter to unblock endpoint table
  - [ ] 1.4: Lines 1132-1178: Add deprecation notice to `POST /blacklist/` section
  - [ ] 1.5: Add new section for `POST /data-sources/{id}/disable-preview` endpoint
  - [ ] 1.6: Line 3: Update version header from `v3.2.0-r10` to `v3.2.0-r11`

- [ ] Task 2: Fix RBAC.md — 5 changes
  - [ ] 2.1: Line 153: Change `blacklist:write` description from "添加/解封黑名单条目" to "解封黑名单条目"
  - [ ] 2.2: Line 531: Add deprecation note to `POST /blacklist/` endpoint mapping
  - [ ] 2.3: Add delete-preview endpoint permission mappings (3 entries, all `datasource:read`)
  - [ ] 2.4: Add disable-preview endpoint permission mapping (`datasource:read`)
  - [ ] 2.5: Line 705: Change "封禁终端" to "解封终端" in Blacklist page row
  - [ ] 2.6: Update version header from `v3.2.0-r10` to `v3.2.0-r11`

- [ ] Task 3: Fix datasource-lifecycle.md — 3 changes
  - [ ] 3.1: Add 7 new API endpoint entries to section 13.1-13.4 tables (3 delete-preview, 1 disable-preview, 3 related)
  - [ ] 3.2: Lines 1166, 1176: Change `datasource:delete` to `datasource:write`
  - [ ] 3.3: Line 1194: Change `baseline:delete` to `baseline:write`
  - [ ] 3.4: Update version header from `v3.2.0-r10` to `v3.2.0-r11`

- [ ] Task 4: Fix architecture.md — 1 change
  - [ ] 4.1: Line 197: Change block action for `unknown + unblocked` state from "查看 + 加白名单（含comment）+ 封锁（含确认+comment）" to "查看 + 加白名单（含comment）"
  - [ ] 4.2: Update version header from `v3.2.0-r10` to `v3.2.0-r11`

- [ ] Task 5: Fix backend.md — 3 changes
  - [ ] 5.1: Line 653: Add `mac_address` parameter to `unblock_ip()` function signature
  - [ ] 5.2: Lines 256-257: Change rate limit defaults from `60`/`5` to `120`/`10`
  - [ ] 5.3: Lines 984-985: Change rate limit defaults from `60`/`5` to `120`/`10`
  - [ ] 5.4: Update version header from `v3.2.0-r10` to `v3.2.0-r11`

- [ ] Task 6: Fix branding.md — 2 changes
  - [ ] 6.1: Lines 344-346: Remove SVG from file format table, add XSS risk note
  - [ ] 6.2: Update version header from `v3.2.0-r8` to `v3.2.0-r11`

- [ ] Task 7: Fix frontend/docs/implementation.md — 3 changes
  - [ ] 7.1: Line 372: Remove "添加黑名单条目" description line
  - [ ] 7.2: Line 596: Remove `POST /api/v1/blacklist/` integration point
  - [ ] 7.3: Update version header from `v3.2.0-r10` to `v3.2.0-r11`

- [ ] Task 8: Fix production-readiness-assessment.md — 4 changes
  - [ ] 8.1: Add logging-guide.md and git-workflow-guide.md to document inventory table
  - [ ] 8.2: Fix version alignment in document inventory table
  - [ ] 8.3: Line 572: Change `.env VERSION=2.0.0` to `VERSION=3.2.0`
  - [ ] 8.4: Update version header from `v3.2.0-r10` to `v3.2.0-r11`

- [ ] Task 9: Fix version headers across remaining docs — 6 files
  - [ ] 9.1: deployment.md: Update version from `v3.2.0-r8` to `v3.2.0-r11`
  - [ ] 9.2: manage-sh-reference.md: Update version from `v3.2.0-r8` to `v3.2.0-r11`
  - [ ] 9.3: logging-guide.md: Update version from `v3.2.0-r8` to `v3.2.0-r11`
  - [ ] 9.4: git-workflow-guide.md: Update version from `v1.0` to `v3.2.0-r11`
  - [ ] 9.5: database.md: Update version from `v3.2.0-r10` to `v3.2.0-r11`
  - [ ] 9.6: changelog.md: Add version header if missing, ensure v3.2.0-r11 tracking
  - [ ] 9.7: release-notes.md: Add v3.2.0-r11 section with disable-preview and doc consistency entries

# Task Dependencies
- Tasks 1-9 are independent of each other and can be executed in parallel
- Task 9 (version headers) should be verified after all other tasks complete to ensure consistency
