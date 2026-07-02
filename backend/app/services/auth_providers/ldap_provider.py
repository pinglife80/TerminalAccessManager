"""
LDAP Authentication Provider for TerminalAccessManager.

Supports Active Directory and OpenLDAP authentication.
"""

import re
import ssl
from typing import Any
from loguru import logger

from app.services.auth_providers.base import AuthProviderBase, AuthProviderType, AuthResult

try:
    import ldap3
    from ldap3 import ALL_ATTRIBUTES, Connection, Server, Tls
    from ldap3.core.exceptions import LDAPBindError, LDAPException
    LDAP_AVAILABLE = True
except ImportError:
    ldap3 = None
    ALL_ATTRIBUTES = []
    Connection = None
    Server = None
    Tls = None
    LDAPBindError = Exception
    LDAPException = Exception
    LDAP_AVAILABLE = False


def escape_ldap_special_chars(value: str) -> str:
    """Escape special characters in LDAP filter values"""
    special_chars = {
        '\\': '\\5c',
        '*': '\\2a',
        '(': '\\28',
        ')': '\\29',
        '"': '\\22',
        '=': '\\3d',
        '<': '\\3c',
        '>': '\\3e',
        ',': '\\2c',
        '+': '\\2b',
        '-': '\\2d',
        '.': '\\2e',
        '/': '\\2f',
        ':': '\\3a',
    }
    result = []
    for char in value:
        if char in special_chars:
            result.append(special_chars[char])
        elif ord(char) < 32 or ord(char) > 126:
            result.append(f'\\{ord(char):02x}')
        else:
            result.append(char)
    return ''.join(result)


def validate_username(username: str) -> bool:
    """Validate username against allowed characters"""
    return bool(re.match(r'^[a-zA-Z0-9_.@-]+$', username))


class LDAPProvider(AuthProviderBase):
    """
    LDAP authentication provider.

    Supports:
    - Active Directory
    - OpenLDAP
    - LDAPS (LDAP over SSL)
    - StartTLS
    """

    provider_type = AuthProviderType.LDAP
    provider_name = "LDAP"

    def _validate_config(self) -> None:
        """Validate LDAP configuration"""
        required_fields = ["server"]
        for field in required_fields:
            if field not in self.config or not self.config[field]:
                raise ValueError(f"LDAP provider requires '{field}' configuration")

    async def authenticate(self, username: str, password: str) -> AuthResult:
        """Authenticate user against LDAP server"""
        logger.info(f"LDAP authentication attempt for username: {username}")

        if not LDAP_AVAILABLE:
            logger.error("LDAP module not available - ldap3 package not installed")
            return self.build_auth_result(
                success=False,
                error_message="LDAP module not available",
                message="Failed",
            )

        if not username or not password:
            logger.warning("LDAP authentication failed: username or password empty")
            return self.build_auth_result(
                success=False,
                error_message="Username and password are required",
            )

        try:
            server = self._build_server()
            use_ssl = self.config.get("use_ssl", False)
            logger.debug(f"LDAP server built: {server.host}:{server.port}, use_ssl={use_ssl}")

            user_dn = self._search_user_dn(username)
            logger.debug(f"Found user DN: {user_dn}")

            conn = Connection(
                server,
                user=user_dn,
                password=password,
                auto_bind=True,
                raise_exceptions=True,
            )
            logger.info(f"LDAP bind successful for user: {username} (DN: {user_dn})")

            user_info = self._get_user_info_from_ldap(conn, user_dn)
            logger.debug(f"Retrieved user info: email={user_info.get('email')}")

            conn.unbind()

            if not self._is_user_active(user_info):
                logger.warning(f"LDAP user account is disabled: {username}")
                return self.build_auth_result(
                    success=False,
                    error_message="User account is disabled",
                )

            logger.info(f"LDAP authentication successful for user: {username}")
            return self.build_auth_result(
                success=True,
                username=username,
                email=user_info.get("email"),
                provider_user_id=user_dn,
                message="Success",
            )

        except LDAPBindError:
            logger.warning(f"LDAP bind failed for user: {username} - invalid credentials or DN")
            return self.build_auth_result(
                success=False,
                error_message="Invalid credentials",
                message="Failed",
            )
        except LDAPException as e:
            logger.error(f"LDAP exception for user {username}: {str(e)}")
            return self.build_auth_result(
                success=False,
                error_message=f"LDAP error: {str(e)}",
                message="Failed",
            )
        except ValueError as e:
            logger.error(f"LDAP configuration error for user {username}: {str(e)}")
            return self.build_auth_result(
                success=False,
                error_message=str(e),
                message="Failed",
            )
        except Exception as e:
            logger.error(f"Unexpected error during LDAP authentication for user {username}: {str(e)}")
            return self.build_auth_result(
                success=False,
                error_message=f"Authentication failed: {str(e)}",
                message="Failed",
            )

    def _build_server(self, get_info: bool = True) -> Server:
        """Build LDAP server configuration"""
        server_host = self.config["server"]
        server_port = self.config.get("port", 389)
        use_ssl = self.config.get("use_ssl", False)
        use_starttls = self.config.get("use_starttls", False)

        tls_config = None
        if use_ssl or use_starttls:
            tls_config = Tls(
                validate=ssl.CERT_NONE if self.config.get("skip_cert_verify", False) else ssl.CERT_REQUIRED,
                version=ssl.PROTOCOL_TLS,
            )

        server_info = ldap3.ALL if get_info else ldap3.NONE

        server = Server(
            server_host,
            port=server_port,
            use_ssl=use_ssl,
            tls=tls_config,
            get_info=server_info,
        )

        return server

    def _search_user_dn(self, username: str) -> str:
        """Search for user DN in LDAP directory"""
        if not validate_username(username):
            logger.warning(f"Invalid username format for search: {username}")
            raise ValueError("Invalid username format")

        user_search_base = self.config.get("user_search_base", "")
        user_search_filter = self.config.get("user_search_filter", "(sAMAccountName={username})")

        if not user_search_base:
            escaped_username = escape_ldap_special_chars(username)
            user_dn_pattern = self.config.get("user_dn_pattern", "cn={username},dc=example,dc=com")
            logger.debug(f"Using direct DN pattern: {user_dn_pattern}")
            return user_dn_pattern.format(username=escaped_username)

        anonymous_search = self.config.get("anonymous_search", False)
        server = self._build_server(get_info=not anonymous_search)
        bind_dn = self.config.get("bind_dn")
        bind_password = self.config.get("bind_password")
        logger.debug(f"Searching user DN with anonymous_search={anonymous_search}, bind_dn: {bind_dn}, search_filter: {user_search_filter}")

        if anonymous_search:
            if bind_dn and bind_password:
                logger.info("Using configured bind DN for user search")
                conn = Connection(
                    server,
                    user=bind_dn,
                    password=bind_password,
                    auto_bind=True,
                    raise_exceptions=True,
                )
            else:
                logger.info("Using anonymous bind for user search as configured")
                conn = Connection(
                    server,
                    user=None,
                    password=None,
                    auto_bind=True,
                    raise_exceptions=True,
                    authentication=ldap3.ANONYMOUS,
                )
        else:
            if bind_dn and not bind_password:
                logger.error("bind_dn is configured but bind_password is missing")
                raise ValueError("LDAP configuration error: bind_dn is set but bind_password is missing")

            if not bind_dn:
                logger.warning("bind_dn not configured, attempting anonymous bind for user search")
                conn = Connection(
                    server,
                    user=None,
                    password=None,
                    auto_bind=True,
                    raise_exceptions=True,
                    authentication=ldap3.ANONYMOUS,
                )
            else:
                conn = Connection(
                    server,
                    user=bind_dn,
                    password=bind_password,
                    auto_bind=True,
                    raise_exceptions=True,
                )

        try:
            escaped_username = escape_ldap_special_chars(username)
            search_filter = user_search_filter.format(username=escaped_username)
            logger.debug(f"Executing LDAP search: base={user_search_base}, filter={search_filter}")

            conn.search(
                search_base=user_search_base,
                search_filter=search_filter,
                attributes=[],
            )

            if conn.entries:
                user_dn = str(conn.entries[0].entry_dn)
                logger.debug(f"Found user DN: {user_dn}")
                return user_dn

            logger.warning(f"User not found in LDAP: {username}")
            raise ValueError(f"User not found: {username}")
        finally:
            conn.unbind()

    def _get_user_info_from_ldap(self, conn: Connection, user_dn: str) -> dict[str, Any]:
        """Get user information from LDAP"""
        conn.search(
            search_base=user_dn,
            search_filter="(objectClass=*)",
            attributes=ALL_ATTRIBUTES,
        )

        if not conn.entries:
            return {}

        entry = conn.entries[0]
        attributes = entry.entry_attributes_as_dict

        email_attr = self.config.get("email_attribute", "mail")
        username_attr = self.config.get("username_attribute", "sAMAccountName")

        return {
            "username": attributes.get(username_attr, [None])[0] if attributes.get(username_attr) else None,
            "email": attributes.get(email_attr, [None])[0] if attributes.get(email_attr) else None,
            "dn": user_dn,
            "raw": attributes,
        }

    def _is_user_active(self, user_info: dict[str, Any]) -> bool:
        """Check if user account is active (AD-specific)"""
        raw_info = user_info.get("raw", {})
        user_account_control = raw_info.get("userAccountControl", [0])[0]
        return not (isinstance(user_account_control, int) and (user_account_control & 2))

    async def get_user_info(self, user_id: str) -> dict[str, Any]:
        """Get user information from LDAP"""
        try:
            anonymous_search = self.config.get("anonymous_search", False)
            server = self._build_server(get_info=not anonymous_search)
            bind_dn = self.config.get("bind_dn")
            bind_password = self.config.get("bind_password")

            if bind_dn and not bind_password:
                return {"error": "bind_dn is set but bind_password is missing"}

            if not bind_dn:
                conn = Connection(
                    server,
                    user=None,
                    password=None,
                    auto_bind=True,
                    raise_exceptions=True,
                    authentication=ldap3.ANONYMOUS,
                )
            else:
                conn = Connection(
                    server,
                    user=bind_dn,
                    password=bind_password,
                    auto_bind=True,
                    raise_exceptions=True,
                )

            try:
                return self._get_user_info_from_ldap(conn, user_id)
            finally:
                conn.unbind()
        except Exception as e:
            return {"error": str(e)}

    async def test_connection(self) -> dict:
        """Test LDAP connection"""
        try:
            anonymous_search = self.config.get("anonymous_search", False)
            server = self._build_server(get_info=not anonymous_search)
            bind_dn = self.config.get("bind_dn")
            bind_password = self.config.get("bind_password")

            if anonymous_search:
                conn = Connection(
                    server,
                    user=None,
                    password=None,
                    auto_bind=True,
                    raise_exceptions=True,
                    authentication=ldap3.ANONYMOUS,
                )
            else:
                if bind_dn and not bind_password:
                    return {
                        "success": False,
                        "message": "bind_dn is configured but bind_password is missing",
                    }

                if not bind_dn:
                    conn = Connection(
                        server,
                        user=None,
                        password=None,
                        auto_bind=True,
                        raise_exceptions=True,
                        authentication=ldap3.ANONYMOUS,
                    )
                else:
                    conn = Connection(
                    server,
                    user=bind_dn,
                    password=bind_password,
                    auto_bind=True,
                    raise_exceptions=True,
                )

            conn.unbind()

            return {
                "success": True,
                "message": f"Connected to LDAP server: {self.config['server']}",
                "details": {
                    "server": self.config["server"],
                    "port": self.config.get("port", 389),
                    "use_ssl": self.config.get("use_ssl", False),
                },
            }
        except LDAPBindError:
            return {
                "success": False,
                "message": "LDAP bind failed - check bind DN and password",
            }
        except LDAPException as e:
            return {
                "success": False,
                "message": f"LDAP connection failed: {str(e)}",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Connection test failed: {str(e)}",
            }

    def search_users(self, search_base: str = None, search_filter: str = None, 
                     username: str = None, page_size: int = 10, page_number: int = 1) -> dict:
        """Search for users in LDAP directory"""
        try:
            anonymous_search = self.config.get("anonymous_search", False)
            server = self._build_server(get_info=not anonymous_search)
            bind_dn = self.config.get("bind_dn")
            bind_password = self.config.get("bind_password")
            user_search_base = search_base or self.config.get("user_search_base", "")
            user_search_filter = search_filter or self.config.get("user_search_filter", "(sAMAccountName={username})")

            if anonymous_search:
                if bind_dn and bind_password:
                    conn = Connection(
                        server,
                        user=bind_dn,
                        password=bind_password,
                        auto_bind=True,
                        raise_exceptions=True,
                    )
                else:
                    conn = Connection(
                        server,
                        user=None,
                        password=None,
                        auto_bind=True,
                        raise_exceptions=True,
                        authentication=ldap3.ANONYMOUS,
                    )
            else:
                if bind_dn and not bind_password:
                    return {"error": "bind_dn is set but bind_password is missing"}

                if not bind_dn:
                    conn = Connection(
                        server,
                        user=None,
                        password=None,
                        auto_bind=True,
                        raise_exceptions=True,
                        authentication=ldap3.ANONYMOUS,
                    )
                else:
                    conn = Connection(
                        server,
                        user=bind_dn,
                        password=bind_password,
                        auto_bind=True,
                        raise_exceptions=True,
                    )

            try:
                if not user_search_base:
                    return {"users": [], "total": 0}

                base_filter = "(objectClass=user)"
                filters_to_combine = [base_filter]
                
                if username:
                    escaped_username = escape_ldap_special_chars(username)
                    user_filter = user_search_filter.format(username=f"*{escaped_username}*")
                    filters_to_combine.append(user_filter)
                
                if search_filter:
                    filters_to_combine.append(search_filter)
                
                if len(filters_to_combine) > 1:
                    final_filter = f"(&{' '.join(filters_to_combine)})"
                else:
                    final_filter = base_filter

                logger.debug(f"LDAP search: base={user_search_base}, filter={final_filter}")

                conn.search(
                    search_base=user_search_base,
                    search_filter=final_filter,
                    attributes=["cn", "sAMAccountName", "mail", "uid", "givenName", "sn"],
                    size_limit=page_size * page_number,
                )

                users = []
                email_attr = self.config.get("email_attribute", "mail")
                username_attr = self.config.get("username_attribute", "sAMAccountName")

                for entry in conn.entries:
                    attrs = entry.entry_attributes_as_dict
                    user_entry = {
                        "dn": str(entry.entry_dn),
                        "cn": attrs.get("cn", [None])[0] if attrs.get("cn") else None,
                        "username": attrs.get(username_attr, [None])[0] if attrs.get(username_attr) else None,
                        "email": attrs.get(email_attr, [None])[0] if attrs.get(email_attr) else None,
                        "givenName": attrs.get("givenName", [None])[0] if attrs.get("givenName") else None,
                        "sn": attrs.get("sn", [None])[0] if attrs.get("sn") else None,
                    }
                    users.append(user_entry)

                start_idx = (page_number - 1) * page_size
                end_idx = start_idx + page_size

                return {
                    "users": users[start_idx:end_idx],
                    "total": len(users),
                }
            finally:
                conn.unbind()
        except Exception as e:
            logger.error(f"LDAP search failed: {str(e)}")
            return {"error": str(e)}

    def get_user_info_by_dn(self, user_dn: str) -> dict:
        """Get user information by DN"""
        try:
            anonymous_search = self.config.get("anonymous_search", False)
            server = self._build_server(get_info=not anonymous_search)
            bind_dn = self.config.get("bind_dn")
            bind_password = self.config.get("bind_password")

            if bind_dn and not bind_password:
                return {"error": "bind_dn is set but bind_password is missing"}

            if not bind_dn:
                conn = Connection(
                    server,
                    user=None,
                    password=None,
                    auto_bind=True,
                    raise_exceptions=True,
                    authentication=ldap3.ANONYMOUS,
                )
            else:
                conn = Connection(
                    server,
                    user=bind_dn,
                    password=bind_password,
                    auto_bind=True,
                    raise_exceptions=True,
                )

            try:
                return self._get_user_info_from_ldap(conn, user_dn)
            finally:
                conn.unbind()
        except Exception as e:
            logger.error(f"Failed to get user info by DN {user_dn}: {str(e)}")
            return {}

    def get_ous(self) -> list:
        """Get Organizational Units from LDAP"""
        try:
            anonymous_search = self.config.get("anonymous_search", False)
            server = self._build_server(get_info=not anonymous_search)
            bind_dn = self.config.get("bind_dn")
            bind_password = self.config.get("bind_password")
            user_search_base = self.config.get("user_search_base", "")

            if bind_dn and not bind_password:
                return []

            if not bind_dn:
                conn = Connection(
                    server,
                    user=None,
                    password=None,
                    auto_bind=True,
                    raise_exceptions=True,
                    authentication=ldap3.ANONYMOUS,
                )
            else:
                conn = Connection(
                    server,
                    user=bind_dn,
                    password=bind_password,
                    auto_bind=True,
                    raise_exceptions=True,
                )

            try:
                if not user_search_base:
                    return []

                conn.search(
                    search_base=user_search_base,
                    search_filter="(objectClass=organizationalUnit)",
                    attributes=["ou", "description"],
                )

                ous = []
                for entry in conn.entries:
                    attrs = entry.entry_attributes_as_dict
                    ous.append({
                        "dn": str(entry.entry_dn),
                        "name": attrs.get("ou", [None])[0] if attrs.get("ou") else None,
                        "description": attrs.get("description", [None])[0] if attrs.get("description") else None,
                    })

                return ous
            finally:
                conn.unbind()
        except Exception as e:
            logger.error(f"Failed to get OUs: {str(e)}")
            return []