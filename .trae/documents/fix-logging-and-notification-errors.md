# Fix: Loguru `<module>` ValueError + Notification Worker SMTP Auth Error

## Summary

Two backend errors to fix:

1. **Loguru** **`ValueError: Tag '<module>' interpreted as a color directive`** — triggered when loguru logs from module-level code (e.g., `main.py` L843 Prometheus metrics log). The `{function}` field contains `<module>` for module-level code, and loguru's colorizer parses the angle brackets as HTML-like color tags.
2. **Notification worker SMTP auth error** — "invalid username-password pair or user is disabled" is an SMTP server authentication rejection. The credentials configured in DB/.env are being rejected by the SMTP server. This is a **configuration issue**, but the code should handle it better: detect auth errors specifically, skip futile retries, and log an actionable message.

***

## Current State Analysis

### Issue 1: Loguru `<module>` colorizer crash

* [logging\_config.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/core/logging_config.py) L58-64: `_log_format()` uses `<cyan>{function}</cyan>` in the colored format string.

* Loguru colorizes the **final substituted output** (not just the format template). When `{function}` is replaced with `<module>`, the colorizer sees `<module>` and tries to interpret it as a color tag → `ValueError`.

* Triggered by any module-level `logger.*()` call, e.g., [main.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py) L843: `logger.info("Prometheus metrics enabled at /metrics and /metrics/custom")` (inside a module-level `try/except`).

* The JSON file handler (`_json_format`) is unaffected because `colorize=False` for file output.

### Issue 2: Notification worker SMTP auth error

Error flow:

1. `EmailSender._send_via_smtp()` ([email\_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/email_service.py) L426-445) calls `server.login(self.username, self.password)` → SMTP server raises `smtplib.SMTPAuthenticationError` with message "invalid username-password pair or user is disabled".
2. `EmailSender.send()` (L396-398) catches it via `except Exception` and wraps in `EmailSendError` — **no distinction between auth failure and other send errors**.
3. `EmailChannel.send()` ([email\_channel.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/notification_channels/email_channel.py) L246-273) catches per-recipient errors, returns `NotificationResult(success=False, error_code="SEND_ERROR")`.
4. `NotificationWorkers._deliver_notification()` ([notification\_workers.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/notification_workers.py) L342-349) sees failure and **schedules a retry** — which is futile for auth errors since credentials won't change between retries.

Key findings:

* The email password in `system_config` is stored as **plaintext** (no encryption/decryption), despite the config description saying "stored encrypted in DB" ([config\_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/config_service.py) L208). This is a misleading description, not a code bug.

* The auth error is genuinely from the SMTP server rejecting the configured credentials. Common cause: using account password instead of authorization code (授权码) for Chinese email providers (QQ, 163, etc.).

***

## Proposed Changes

### Change 1: Fix loguru `<module>` colorizer crash

**File:** [backend/app/core/logging\_config.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/core/logging_config.py)

**What:** Add a patcher function that sanitizes the `function` field in log records before formatting, replacing angle brackets with square brackets. Register it via `logger.configure(patcher=...)` in `setup_logging()`.

**Why:** Loguru's colorizer parses the final substituted output for `<tag>` patterns. Python uses `<module>` as the function name for module-level code, which gets misinterpreted as a color tag. The patcher sanitizes this before the colorizer sees it.

**How:**

* Add a `_patcher(record)` function:

  ```python
  def _patcher(record) -> None:
      """Sanitize dynamic fields to prevent loguru colorizer errors.

      Python uses '<module>' as the function name for module-level code.
      Loguru's colorizer interprets '<module>' as a color directive tag
      and raises ValueError. Replace angle brackets with square brackets.
      """
      fn = record.get("function")
      if fn and isinstance(fn, str) and "<" in fn:
          record["function"] = fn.replace("<", "[").replace(">", "]")
  ```

* In `setup_logging()`, after `logger.remove()` and before adding handlers, call:

  ```python
  logger.configure(patcher=_patcher)
  ```

* This changes `<module>` → `[module]` in console output, which is visually similar and safe.

### Change 2: Detect SMTP auth errors and skip futile retries

**File:** [backend/app/services/email\_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/email_service.py)

**What:** In `EmailSender.send()` (L375-398), catch `smtplib.SMTPAuthenticationError` separately from other exceptions and raise `EmailSendError` with a distinct marker (e.g., prefix `"AUTH_ERROR:"` in the message) so downstream code can detect it.

**Why:** Currently all send errors are wrapped uniformly as `EmailSendError`. The notification worker can't distinguish auth failures (permanent, retrying is pointless) from transient errors (network timeout, server busy).

**How:** In the `except Exception as e:` block at L396-398, add a specific check:

```python
except smtplib.SMTPAuthenticationError as e:
    logger.error(f"SMTP authentication failed: {e}")
    raise EmailSendError(f"AUTH_ERROR: SMTP authentication failed - check username/password or use authorization code (授权码) for Chinese email providers. Server response: {e}")
except Exception as e:
    logger.error(f"Email sending failed: {type(e).__name__}: {e}")
    raise EmailSendError(f"Failed to send email: {str(e)}")
```

Need to add `import smtplib` at the top of the `send()` method or at module level (it's already imported inside `_send_via_smtp`, so add it at the `send` method scope or import at module level).

**File:** [backend/app/services/notification\_channels/email\_channel.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/notification_channels/email_channel.py)

**What:** In the global config path (L246-273), detect `AUTH_ERROR:` prefix in the error message and set `error_code="AUTH_ERROR"` instead of `"SEND_ERROR"`.

**How:** In the per-recipient loop, check `last_error`:

```python
except Exception as single_err:
    last_error = str(single_err)
    if "AUTH_ERROR:" in last_error:
        logger.error(f"SMTP auth failed for {recipient}: check SMTP credentials in Email Settings")
    else:
        logger.error(f"Failed to send email to {recipient}: {single_err}")
```

And in the failure result (L267-273):

```python
error_code = "AUTH_ERROR" if (last_error and "AUTH_ERROR:" in last_error) else "SEND_ERROR"
return NotificationResult(
    success=False,
    message=f"Send failed: {last_error or 'unknown error'}",
    channel=self.channel_type,
    event_id=event.id if event else None,
    error_code=error_code,
)
```

**File:** [backend/app/services/notification\_workers.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/notification_workers.py)

**What:** In `_deliver_notification()` (L335-349), when `success` is False, check if `result.error_code == "AUTH_ERROR"`. If so, skip retry scheduling and log a clear warning instead.

**Why:** Retrying with the same bad credentials wastes resources and spams the log. Auth errors are permanent until the user fixes the SMTP configuration.

**How:** Modify the failure branch (L341-349):

```python
if success:
    if rule and rule.suppress_enabled:
        await rules_engine.set_suppression(
            event_type, channel_name, rule.suppress_window
        )
    await notification_logger.log_sent(event, channel_name, result)
elif result and result.error_code == "AUTH_ERROR":
    # Auth errors are permanent — don't retry, just log
    logger.warning(
        f"Skipping retry for {channel_name}: SMTP auth failed. "
        f"Fix email credentials in Settings → Email Settings."
    )
    await notification_logger.log_failed(
        event, channel_name, result, retry_count
    )
else:
    if retry_count < MAX_RETRIES:
        await self._schedule_retry(
            payload, channel_name, result, retry_count
        )
    else:
        await notification_logger.log_failed(
            event, channel_name, result, retry_count
        )
```

### Change 3: Fix misleading config description (trivial)

**File:** [backend/app/services/config\_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/config_service.py) L208

**What:** Update the `email_password` config description from "stored encrypted in DB" to "stored in DB" since there's no encryption applied.

```python
{"key": "email_password", "value": "", "category": "email",
 "value_type": "string", "description": "SMTP authentication password (use authorization code/授权码 for QQ/163)",
 "is_readonly": False},
```

***

## Assumptions & Decisions

1. **Loguru patcher approach**: Chose `logger.configure(patcher=...)` over alternatives (ANSI codes, `colorize=False`) because it's minimal, targeted, and preserves all existing color output. Only the `function` field is sanitized.
2. **`[module]`** **instead of removing brackets**: Replacing `<` → `[` and `>` → `]` keeps the visual style consistent and readable.
3. **AUTH\_ERROR detection via message prefix**: Using a `"AUTH_ERROR:"` string prefix in `EmailSendError` message is the simplest way to propagate the error type through the existing call chain without adding new exception classes or changing return types. The `NotificationResult.error_code` field already exists and is the right place for this.
4. **Not implementing password encryption**: The "stored encrypted in DB" description is misleading, but implementing actual encryption is out of scope for this fix. Just correcting the description.
5. **The actual SMTP auth failure is a configuration issue**: The code changes improve error handling and user guidance, but the user still needs to configure correct SMTP credentials (or authorization code) in Settings → Email Settings.

***

## Verification Steps

1. **Loguru fix**: After rebuild, check that module-level log lines (e.g., "Prometheus metrics enabled...") appear in console output with `[module]` instead of `<module>`, and no `ValueError` is raised.
2. **SMTP auth error handling**:

   * Trigger a notification with bad SMTP credentials configured.

   * Verify the error is logged with `AUTH_ERROR` code and a clear message about checking credentials.

   * Verify NO retry is scheduled (check that "Scheduled retry #N" log does NOT appear for auth errors).

   * Verify other (transient) errors still trigger retries as before.
3. **Run existing tests**: `cd backend && python -m pytest tests/test_notification_service.py -v` to ensure notification service tests still pass.
4. **Rebuild and smoke test**: Rebuild the backend container and verify it starts without loguru errors.

