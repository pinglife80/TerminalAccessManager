# Stats Issues Fix Plan

## Issues Identified

### 1. Blacklist Page "Firewall Actual" Count is 0

* **Root Cause**: In `firewall_reconciliation_service.py`, the `reconcile()` method computes `firewall_ip_count` correctly but never saves the results to the Redis cache at "reconcile:latest" key.

* **Impact**: The Blacklist page (frontend) tries to read `firewall_ip_count` from the Redis cache but always gets `null`/0.

### 2. Terminal Management Page Non-Compliant Count < Blocked Count

* **Root Cause**:

  1. In the previous fix, we modified `terminal_service.py::get_stats()` to only count terminals where `compliance_status='non_compliant' AND status='blocked'` for the `non_compliant` stat.
  2. The `stats.blocked` value counts **distinct IPs** in the Blacklist table (active entries), which includes reconciliation entries without corresponding Terminal records.
  3. The `stats.non_compliant` value only counts Terminal records that are both non-compliant and blocked, so it will be smaller than `stats.blocked` when there are reconciliation entries without terminals.

## Fix Steps

### 1. Fix Blacklist Page Firewall Actual Count

* **File**: `/home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py`

* **Changes**:

  * Add code at the end of `reconcile()` method to save the reconciliation results to Redis cache with "reconcile:latest" key

  * Include `synced_at` timestamp in the payload

### 2. Fix Terminal Management Stats Discrepancy

* **File**: `/home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Terminals.tsx`

* **Changes**:

  * Update the "Non-Compliant" stat to use `stats.blocked` instead of `stats.non_compliant` to match what the Dashboard and Blacklist page display

  * The Dashboard already uses `stats.blocked` for the blocked count, so aligning Terminal page to do the same will keep all pages consistent

### 3. (Optional) Fix Backend Stats Calculation Clarity

* **File**: `/home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py`

* **Changes**:

  * Consider renaming the stats fields to be clearer if needed

  * Ensure that the stats explain the difference between non-compliant terminals and blocked IPs

## Expected Outcome

1. Blacklist page will show correct firewall actual blocked count
2. All pages (Dashboard, Terminal, Blacklist) will show the same blocked/non-compliant count
3. No more discrepancies between stats on different pages

