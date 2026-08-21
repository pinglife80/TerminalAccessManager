from typing import Any, Dict, Optional, Tuple
import asyncio
from datetime import datetime, timedelta
from enum import Enum

import httpx
from loguru import logger

from app.core.config import settings

# TAM system identifier prefix for Sangfor AF blacklist descriptions.
# This prefix is used to distinguish TAM-managed blacklist entries from
# entries created by other AF features (IPS, WAF, manual, etc.).
# Only entries with this prefix will be managed (deleted) by TAM.
TAM_DESCRIPTION_PREFIX = "TAM"

# Sangfor AF API base path (all endpoints start with /api)
API_PREFIX = "/api"

# Global cache for SangforService instances to reuse connections
_service_cache: Dict[str, 'SangforService'] = {}
_cache_lock = asyncio.Lock()
_token_expiry: Dict[str, datetime] = {}

# Firewall operation types
class FirewallOperationType(Enum):
    BLOCK = "block"
    UNBLOCK = "unblock"

# Maximum concurrent connections to Sangfor AF
MAX_CONCURRENT_OPERATIONS = 3


class SangforService:
    """Service for interacting with Sangfor AF API.

    Uses the Sangfor AF 8.0+ whitelist/blacklist API for permanent IP blocking,
    instead of the temporary blockip API. This ensures:
    - Permanent blocking (no expiration)
    - Unique description with TAM prefix for identification
    - Safe deletion: only TAM-managed entries are removed

    Authentication flow (per AF8.0.75.md section 2.1):
    1. POST /api/v1/namespaces/public/login with JSON credentials
    2. Server returns token in response body: {"data": {"loginResult": {"token": "..."}}}
    3. Token is sent via Cookie header on subsequent requests
    4. Token expires after 10 minutes of inactivity (configurable on AF)
    5. Use keepalive API to refresh token before expiry

    API URL format (per AF8.0.75.md section 1.2):
    - Single resource: /api/v1/namespaces/@namespace/resource
    - Batch resource:  /api/batch/v1/namespaces/@namespace/resource
    """

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        verify_ssl: bool = True,
        ca_bundle: str = "",
    ):
        self.base_url = (base_url or settings.SANGFOR_BASE_URL or "").rstrip("/")
        self.username = username or settings.SANGFOR_USERNAME or ""
        self.password = password or settings.SANGFOR_PASSWORD or ""
        self.token = None
        self.session = None
        self._verify_ssl = verify_ssl
        self._ca_bundle = ca_bundle
        self._authenticating = False
        self._connection_pool_limits = httpx.Limits(
            max_connections=5,
            max_keepalive_connections=3,
            keepalive_expiry=300,
        )
        self._operation_queue: asyncio.Queue[Tuple[FirewallOperationType, str, str, str]] = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_OPERATIONS)
        self._queue_running = False

    def _get_verify_setting(self) -> bool | str:
        """Get SSL verification setting."""
        if self._ca_bundle:
            return self._ca_bundle
        if not self._verify_ssl:
            return False
        if settings.SANGFOR_CA_BUNDLE:
            return settings.SANGFOR_CA_BUNDLE
        return True

    def _create_client(self, **kwargs) -> httpx.AsyncClient:
        """Create an httpx AsyncClient with common settings and connection pooling."""
        defaults = {
            "verify": self._get_verify_setting(),
            "timeout": 30.0,
            "follow_redirects": True,
            "limits": self._connection_pool_limits,
        }
        defaults.update(kwargs)
        return httpx.AsyncClient(**defaults)

    async def _get_session(self) -> httpx.AsyncClient:
        """Get or create HTTP session with authentication"""
        if not self.session:
            self.session = self._create_client(
                headers={'Content-Type': 'application/json'}
            )
        if not self.token:
            await self._authenticate()
        return self.session

    async def _authenticate(self):
        """Authenticate with Sangfor AF API (section 2.1).

        POST /api/v1/namespaces/public/login
        Body: {"name": username, "password": password}
        Response: {"code": 0, "data": {"loginResult": {"token": "..."}}}
        """
        if self._authenticating:
            raise RuntimeError("Already authenticating - possible recursive auth loop")

        self._authenticating = True
        try:
            if not self.session:
                self.session = self._create_client(
                    headers={'Content-Type': 'application/json'}
                )
            
            login_url = f"{self.base_url}{API_PREFIX}/v1/namespaces/public/login"
            logger.debug(f"Authenticating with Sangfor AF: {login_url}")

            response = await self.session.post(
                login_url,
                json={"name": self.username, "password": self.password}
            )

            if response.status_code in (301, 302, 303, 307, 308):
                redirect_location = response.headers.get('location', 'unknown')
                raise ConnectionError(
                    f"Sangfor AF login endpoint returned redirect "
                    f"({response.status_code}) to '{redirect_location}'. "
                    f"The API URL may be incorrect. "
                    f"Expected: {login_url}"
                )

            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                raise ConnectionError(
                    f"Sangfor AF login failed: code={data.get('code')}, "
                    f"message={data.get('message', 'unknown')}"
                )

            # Parse token from response
            login_data = data.get("data", {})
            login_result = login_data.get("loginResult", {})
            token = login_result.get("token")

            if not token:
                raise ValueError(
                    f"Unexpected Sangfor AF login response: missing token. "
                    f"Response: {str(data)[:500]}"
                )

            self.token = token

            self.session.cookies.set('token', self.token)

            logger.info("Successfully authenticated with Sangfor API")

        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Cannot connect to Sangfor AF at {self.base_url}: {str(e)}. "
                f"Verify the base URL, network connectivity, and firewall port."
            )
        except httpx.ConnectTimeout:
            raise ConnectionError(
                f"Connection timeout to Sangfor AF at {self.base_url}. "
                f"The firewall may be unreachable or the port is blocked."
            )
        except httpx.TooManyRedirects as e:
            raise ConnectionError(
                f"Too many redirects connecting to Sangfor AF at {self.base_url}. "
                f"Ensure base_url uses HTTPS. Detail: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Failed to authenticate with Sangfor API: {str(e)}")
            raise
        finally:
            self._authenticating = False

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make an API request with automatic re-authentication on 401."""
        session = await self._get_session()
        response = await session.request(method, url, **kwargs)

        if response.status_code == 401:
            logger.warning("Sangfor AF token expired, re-authenticating...")
            self.token = None
            session = await self._get_session()
            response = await session.request(method, url, **kwargs)

        return response

    async def _request_with_backoff(self, method: str, url: str, max_retries: int = 3, **kwargs) -> httpx.Response:
        """Make API request with exponential backoff for transient errors.

        Wraps _request_with_retry so that 401 re-authentication is handled first,
        then backoff applies if the request still fails with a transient error
        (connection errors, timeouts, or 5xx server errors).
        """
        import asyncio
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return await self._request_with_retry(method, url, **kwargs)
            except (ConnectionError, TimeoutError, httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
                if attempt < max_retries:
                    wait = min(2 ** attempt, 10)  # 1s, 2s, 4s (capped at 10s)
                    logger.warning(
                        f"Sangfor API request failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {wait}s: {str(e)}"
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        f"Sangfor API request failed after {max_retries + 1} attempts: {str(e)}"
                    )
                    raise
            except httpx.HTTPStatusError as e:
                # 5xx server errors are retryable, 4xx client errors are not
                if e.response.status_code >= 500 and attempt < max_retries:
                    wait = min(2 ** attempt, 10)
                    logger.warning(
                        f"Sangfor API server error {e.response.status_code} "
                        f"(attempt {attempt + 1}/{max_retries + 1}), retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)
                else:
                    raise

        raise last_error  # Should not reach here, but just in case

    # ------------------------------------------------------------------
    # Blacklist (permanent blocking via whiteblacklist API)
    # ------------------------------------------------------------------

    # Characters forbidden in Sangfor AF description field
    # Per AF error: 不能包含\f\n\r\t\v`~!#$%^&*+=\\|{};:\"',/<>?这些特殊字符
    _FORBIDDEN_DESC_CHARS = set('\f\n\r\t\v`~!#$%^&*+=\\|{};:"\',/<>?')

    @classmethod
    def _sanitize_description(cls, text: str) -> str:
        """Remove forbidden characters from description text for Sangfor AF."""
        return ''.join(c for c in text if c not in cls._FORBIDDEN_DESC_CHARS)

    @classmethod
    def _make_description(cls, source_tag: str = "", reason: str = "") -> str:
        """Build a unique description for TAM-managed blacklist entries.

        Format: TAM-{source_tag}-{reason}
        Example: TAM-lab-Auto-blocked non-compliant

        Uses hyphens as separators (colons are forbidden by Sangfor AF).
        All forbidden characters are stripped from the final string.

        This prefix is critical for idempotent operations:
        - Before adding: check if entry already exists with TAM prefix
        - Before deleting: verify entry has TAM prefix to avoid deleting
          non-TAM entries created by AF's own security features
        """
        parts = [TAM_DESCRIPTION_PREFIX]
        if source_tag:
            parts.append(source_tag)
        if reason:
            parts.append(reason)
        raw = "-".join(parts)
        return cls._sanitize_description(raw)

    @staticmethod
    def is_tam_managed_entry(description: str) -> bool:
        """Check if a blacklist entry was created by TAM system.

        Only TAM-managed entries should be deleted by the unblock operation.
        This prevents accidentally removing entries created by AF's IPS/WAF/etc.
        """
        return bool(description and description.startswith(TAM_DESCRIPTION_PREFIX))

    async def block_ip(
        self,
        ip_list: list[str],
        block_time: str = "",
        source_tag: str = "",
        reason: str = "Auto-blocked",
    ) -> dict[str, Any]:
        """Block IP addresses via Sangfor AF blacklist API (permanent).

        Uses the whiteblacklist API (section 8.1.3) instead of blockip API.
        This provides permanent blocking with a TAM-prefixed description
        for safe identification and management.

        Idempotency: Before adding, checks if the IP already exists in the
        blacklist with TAM prefix. Skips if already present.

        Args:
            ip_list: List of IP addresses to block
            block_time: Ignored (kept for API compatibility, blacklist is permanent)
            source_tag: Data source tag for description identification
            reason: Block reason for description
        """
        results = {"blocked": [], "skipped": [], "errors": []}

        for ip in ip_list:
            try:
                # Idempotency check: skip if already blocked by TAM
                existing = await self._find_blacklist_entry(ip)
                if existing and self.is_tam_managed_entry(existing.get("description", "")):
                    logger.info(f"IP {ip} already in AF blacklist (TAM-managed), skipping")
                    results["skipped"].append(ip)
                    continue

                # Add to blacklist via whiteblacklist API
                description = self._make_description(source_tag, reason)
                response = await self._request_with_backoff(
                    "POST",
                    f"{self.base_url}{API_PREFIX}/v1/namespaces/public/whiteblacklist",
                    json={
                        "url": ip,
                        "type": "BLACK",
                        "description": description,
                        "enable": True,
                    }
                )

                if response.status_code == 409:
                    # Entry already exists (conflict)
                    logger.info(f"IP {ip} already in AF blacklist, skipping")
                    results["skipped"].append(ip)
                    continue

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as http_err:
                    # Log response body to help diagnose 400/4xx errors
                    # (session issues, rate limiting, parameter errors, etc.)
                    body = (http_err.response.text or "")[:500]
                    logger.error(
                        f"AF blacklist API returned HTTP {http_err.response.status_code} "
                        f"for block_ip {ip}: body={body}"
                    )
                    raise
                data = response.json()

                if data.get("code") == 0:
                    logger.info(f"Blocked IP {ip} on Sangfor AF (blacklist, desc={description})")
                    results["blocked"].append(ip)
                else:
                    error_msg = data.get("message", "unknown error")
                    logger.error(f"Failed to block IP {ip} on Sangfor AF: {error_msg}")
                    results["errors"].append({"ip": ip, "error": error_msg})

            except Exception as e:
                logger.error(f"Error blocking IP {ip} on Sangfor AF: {str(e)}")
                results["errors"].append({"ip": ip, "error": str(e)})

        # Return format compatible with existing callers
        success = len(results["blocked"]) > 0 or len(results["skipped"]) > 0
        return {
            "code": 0 if success else 1,
            "message": f"Blocked {len(results['blocked'])}, skipped {len(results['skipped'])}, errors {len(results['errors'])}",
            "data": results,
        }

    async def unblock_ip(self, ip_list: list[dict[str, str]]) -> dict[str, Any]:
        """Unblock IP addresses via Sangfor AF blacklist API.

        Uses the whiteblacklist DELETE API (section 8.1.5) to remove by IP.
        Only removes entries that were created by TAM (have TAM: prefix in description).

        Idempotency: If the IP is not in the blacklist or is not TAM-managed,
        the operation is skipped safely.

        Args:
            ip_list: List of dicts, e.g. [{"srcIP": "192.168.1.1"}]
                     (kept for API compatibility with existing callers)
        """
        results = {"unblocked": [], "skipped": [], "errors": []}

        for item in ip_list:
            ip = item.get("srcIP", "")
            if not ip:
                continue

            try:
                # Safety check: only delete TAM-managed entries
                existing = await self._find_blacklist_entry(ip)
                if not existing:
                    logger.info(f"IP {ip} not in AF blacklist, skipping unblock")
                    results["skipped"].append(ip)
                    continue

                if not self.is_tam_managed_entry(existing.get("description", "")):
                    logger.warning(
                        f"IP {ip} in AF blacklist but NOT TAM-managed "
                        f"(desc='{existing.get('description', '')}'), skipping unblock"
                    )
                    results["skipped"].append(ip)
                    continue

                # Delete via whiteblacklist API
                response = await self._request_with_backoff(
                    "DELETE",
                    f"{self.base_url}{API_PREFIX}/v1/namespaces/public/whiteblacklist/{ip}"
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") == 0:
                    logger.info(f"Unblocked IP {ip} on Sangfor AF (removed from blacklist)")
                    results["unblocked"].append(ip)
                else:
                    error_msg = data.get("message", "unknown error")
                    logger.error(f"Failed to unblock IP {ip} on Sangfor AF: {error_msg}")
                    results["errors"].append({"ip": ip, "error": error_msg})

            except Exception as e:
                logger.error(f"Error unblocking IP {ip} on Sangfor AF: {str(e)}")
                results["errors"].append({"ip": ip, "error": str(e)})

        success = len(results["unblocked"]) > 0
        return {
            "code": 0 if success else 1,
            "message": f"Unblocked {len(results['unblocked'])}, skipped {len(results['skipped'])}, errors {len(results['errors'])}",
            "data": results,
        }

    async def _find_blacklist_entry(self, ip: str) -> dict[str, Any] | None:
        """Find a blacklist entry by IP address.

        Uses the whiteblacklist search API (section 8.1.1) with the IP
        as search keyword to find the entry.

        Returns the entry dict if found, None otherwise.
        """
        try:
            response = await self._request_with_backoff(
                "GET",
                f"{self.base_url}{API_PREFIX}/v1/namespaces/public/whiteblacklist",
                params={
                    "type": "BLACK",
                    "url": ip,
                    "_length": 10,
                }
            )
            response.raise_for_status()
            data = response.json()

            if data.get("code") == 0:
                items = data.get("data", {}).get("items", [])
                for item in items:
                    if item.get("url") == ip:
                        return item
            return None

        except Exception as e:
            logger.warning(f"Error searching AF blacklist for {ip}: {str(e)}")
            return None

    async def get_blocked_ips(self, search: str = "") -> dict[str, Any]:
        """Get list of blocked IPs from Sangfor AF blacklist.

        Uses the whiteblacklist API (section 8.1.1) with type=BLACK.
        Optionally filter by search keyword.
        """
        try:
            params = {"type": "BLACK", "_length": 200}
            if search:
                params["_search"] = search

            response = await self._request_with_backoff(
                "GET",
                f"{self.base_url}{API_PREFIX}/v1/namespaces/public/whiteblacklist",
                params=params
            )
            response.raise_for_status()

            result = response.json()
            if not isinstance(result, dict):
                logger.error(f"get_blocked_ips returned unexpected type: {type(result).__name__}")
                return {"code": -1, "data": {"items": []}}

            # Log abnormal responses to help diagnose empty/error lists
            if result.get("code") != 0:
                logger.warning(
                    f"get_blocked_ips returned non-zero code={result.get('code')}, "
                    f"message={result.get('message', 'unknown')}, raw={(response.text or '')[:500]}"
                )
            else:
                items = result.get("data", {}).get("items", [])
                if not items:
                    logger.warning(
                        f"get_blocked_ips returned 0 items "
                        f"(raw={(response.text or '')[:300]})"
                    )

            return result

        except Exception as e:
            logger.error(f"Failed to get blocked IPs: {str(e)}")
            raise

    async def keepalive(self) -> bool:
        """Refresh token timestamp to prevent expiration (section 2.3).

        GET /api/v1/namespaces/public/keepalive

        Should be called periodically (e.g., every 5 minutes) to keep
        the session alive during long-running operations.
        """
        try:
            response = await self._request_with_backoff(
                "GET",
                f"{self.base_url}{API_PREFIX}/v1/namespaces/public/keepalive"
            )
            response.raise_for_status()
            data = response.json()
            return data.get("code") == 0
        except Exception as e:
            logger.warning(f"Sangfor AF keepalive failed: {str(e)}")
            return False

    async def test_connection(self) -> dict[str, Any]:
        """Test connection to Sangfor AF by authenticating.

        Returns dict with 'success', 'message', and optional 'details'.
        """
        try:
            async with self._create_client() as client:
                login_url = f"{self.base_url}{API_PREFIX}/v1/namespaces/public/login"
                response = await client.post(
                    login_url,
                    json={"name": self.username, "password": self.password}
                )

                if response.status_code in (301, 302, 303, 307, 308):
                    redirect_location = response.headers.get('location', 'unknown')
                    return {
                        "success": False,
                        "message": (
                            f"Login endpoint returned redirect ({response.status_code}) "
                            f"to '{redirect_location}'. The API URL may be incorrect. "
                            f"Ensure base_url is correct (e.g., https://10.8.116.1:888) "
                            f"and the AF firmware version supports REST API."
                        ),
                    }

                response.raise_for_status()
                data = response.json()

                if data.get("code") != 0:
                    return {
                        "success": False,
                        "message": (
                            f"Sangfor AF login failed: code={data.get('code')}, "
                            f"message={data.get('message', 'unknown')}. "
                            f"Check username and password."
                        ),
                    }

                login_data = data.get("data", {})
                login_result = login_data.get("loginResult", {})
                token = login_result.get("token")

                if not token:
                    return {
                        "success": False,
                        "message": (
                            f"Login response missing token. "
                            f"Response: {str(data)[:300]}"
                        ),
                    }

                role = login_data.get("role", "unknown")
                return {
                    "success": True,
                    "message": "Sangfor AF connection successful",
                    "details": {
                        "role": role,
                        "token_valid": True,
                    },
                }

        except httpx.ConnectError as e:
            return {
                "success": False,
                "message": (
                    f"Cannot connect to {self.base_url}: {str(e)}. "
                    f"Verify the base URL and network connectivity."
                ),
            }
        except httpx.ConnectTimeout:
            return {
                "success": False,
                "message": (
                    f"Connection timeout to {self.base_url}. "
                    f"The firewall may be unreachable."
                ),
            }
        except httpx.TooManyRedirects as e:
            return {
                "success": False,
                "message": (
                    f"Redirect loop connecting to {self.base_url}. "
                    f"Ensure base_url uses HTTPS. Detail: {str(e)}"
                ),
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "message": (
                    f"HTTP {e.response.status_code} from Sangfor AF. "
                    f"Check username/password. Detail: {str(e)}"
                ),
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Sangfor AF connection failed: {str(e)}",
            }

    @classmethod
    async def get_cached_service(
        cls,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        verify_ssl: bool = True,
        ca_bundle: str = "",
    ) -> 'SangforService':
        """Get or create a cached SangforService instance to reuse connections.
        
        This prevents creating multiple authenticated sessions to the same firewall,
        which can exceed the firewall's concurrent user limit.
        """
        url_key = (base_url or settings.SANGFOR_BASE_URL or "").rstrip("/")
        
        async with _cache_lock:
            if url_key in _service_cache:
                service = _service_cache[url_key]
                
                if service.token:
                    expiry = _token_expiry.get(url_key)
                    if expiry and datetime.now() < expiry:
                        logger.debug(f"Reusing cached SangforService for {url_key}")
                        return service
                    
                    await service.keepalive()
                    _token_expiry[url_key] = datetime.now() + timedelta(minutes=8)
                    return service
            
            service = cls(
                base_url=base_url,
                username=username,
                password=password,
                verify_ssl=verify_ssl,
                ca_bundle=ca_bundle,
            )
            
            try:
                await service._authenticate()
                _service_cache[url_key] = service
                _token_expiry[url_key] = datetime.now() + timedelta(minutes=8)
                logger.info(f"Created new cached SangforService for {url_key}")
            except Exception as e:
                logger.error(f"Failed to authenticate SangforService for {url_key}, not caching: {e}")
                raise
            
            return service

    async def close(self):
        """Close the HTTP session and remove from cache"""
        url_key = self.base_url
        self._queue_running = False
        
        if self.session:
            await self.session.aclose()
            self.session = None
            self.token = None
        
        async with _cache_lock:
            if url_key in _service_cache:
                del _service_cache[url_key]
            if url_key in _token_expiry:
                del _token_expiry[url_key]

    def enqueue_operation(self, op_type: FirewallOperationType, ip: str, source_tag: str = "", reason: str = ""):
        """Enqueue a firewall operation for async processing."""
        self._operation_queue.put_nowait((op_type, ip, source_tag, reason))
        if not self._queue_running:
            self._queue_running = True
            asyncio.create_task(self._process_queue())

    async def _process_queue(self):
        """Process the operation queue with concurrency control."""
        while self._queue_running or not self._operation_queue.empty():
            try:
                op_type, ip, source_tag, reason = await asyncio.wait_for(
                    self._operation_queue.get(), timeout=5.0
                )
                
                async with self._semaphore:
                    try:
                        if op_type == FirewallOperationType.BLOCK:
                            await self._execute_block(ip, source_tag, reason)
                        elif op_type == FirewallOperationType.UNBLOCK:
                            await self._execute_unblock(ip)
                    except Exception as e:
                        logger.error(f"Failed to process {op_type.value} operation for {ip}: {str(e)}")
                
                self._operation_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing operation queue: {str(e)}")

    async def _execute_block(self, ip: str, source_tag: str, reason: str):
        """Execute a single block operation with retry."""
        for attempt in range(3):
            try:
                existing = await self._find_blacklist_entry(ip)
                if existing and self.is_tam_managed_entry(existing.get("description", "")):
                    logger.info(f"IP {ip} already blocked by TAM, skipping")
                    return

                description = self._make_description(source_tag, reason)
                response = await self._request_with_backoff(
                    "POST",
                    f"{self.base_url}{API_PREFIX}/v1/namespaces/public/whiteblacklist",
                    json={
                        "url": ip,
                        "type": "BLACK",
                        "description": description,
                        "enable": True,
                    }
                )

                if response.status_code == 409:
                    logger.info(f"IP {ip} already in AF blacklist, skipping")
                    return

                response.raise_for_status()
                data = response.json()

                if data.get("code") == 0:
                    logger.info(f"Blocked IP {ip} on Sangfor AF (blacklist)")
                else:
                    logger.error(f"Failed to block IP {ip}: {data.get('message', 'unknown')}")
                return
            except Exception as e:
                if attempt < 2:
                    wait = 2 ** attempt
                    logger.warning(f"Block operation for {ip} failed (attempt {attempt+1}/3), retrying in {wait}s: {str(e)}")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Block operation for {ip} failed after 3 attempts: {str(e)}")

    async def _execute_unblock(self, ip: str):
        """Execute a single unblock operation with retry."""
        for attempt in range(3):
            try:
                existing = await self._find_blacklist_entry(ip)
                if not existing:
                    logger.info(f"IP {ip} not in AF blacklist, skipping unblock")
                    return

                if not self.is_tam_managed_entry(existing.get("description", "")):
                    logger.warning(f"IP {ip} not TAM-managed, skipping unblock")
                    return

                response = await self._request_with_backoff(
                    "DELETE",
                    f"{self.base_url}{API_PREFIX}/v1/namespaces/public/whiteblacklist/{ip}"
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") == 0:
                    logger.info(f"Unblocked IP {ip} on Sangfor AF")
                else:
                    logger.error(f"Failed to unblock IP {ip}: {data.get('message', 'unknown')}")
                return
            except Exception as e:
                if attempt < 2:
                    wait = 2 ** attempt
                    logger.warning(f"Unblock operation for {ip} failed (attempt {attempt+1}/3), retrying in {wait}s: {str(e)}")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Unblock operation for {ip} failed after 3 attempts: {str(e)}")
