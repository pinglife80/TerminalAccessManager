"""
LDAP Authentication Provider for TerminalAccessManager.

Supports Active Directory and OpenLDAP authentication.
"""

import re
import ssl
from typing import Any

import ldap3
from ldap3 import ALL_ATTRIBUTES, Connection, Server, Tls
from ldap3.core.exceptions import LDAPBindError, LDAPException

from app.services.auth_providers.base import AuthCredentials, AuthProviderBase, AuthProviderType, AuthResult


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

    async def authenticate(self, credentials: AuthCredentials) -> AuthResult:
        """Authenticate user against LDAP server"""
        username = credentials.username
        password = credentials.password

        if not username or not password:
            return self.build_auth_result(
                success=False,
                error_message="Username and password are required",
            )

        try:
            # Build LDAP connection
            server = self._build_server()

            # Build user DN
            user_dn = self._build_user_dn(username)

            # Connect and bind with user credentials
            conn = Connection(
                server,
                user=user_dn,
                password=password,
                auto_bind=True,
                raise_exceptions=True,
            )

            # Get user attributes if successful
            user_info = await self._get_user_info_from_ldap(conn, user_dn)

            # Check if user is active (optional)
            if not self._is_user_active(user_info):
                return self.build_auth_result(
                    success=False,
                    error_message="User account is disabled",
                )

            return self.build_auth_result(
                success=True,
                username=username,
                email=user_info.get("email"),
                provider_user_id=user_dn,
            )

        except LDAPBindError:
            return self.build_auth_result(
                success=False,
                error_message="Invalid credentials",
            )
        except LDAPException as e:
            return self.build_auth_result(
                success=False,
                error_message=f"LDAP error: {str(e)}",
            )
        except Exception as e:
            return self.build_auth_result(
                success=False,
                error_message=f"Authentication failed: {str(e)}",
            )

    def _build_server(self) -> Server:
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

        server = Server(
            server_host,
            port=server_port,
            use_ssl=use_ssl,
            tls=tls_config,
            get_info=ldap3.ALL,
        )

        return server

    def _build_user_dn(self, username: str) -> str:
        """Build user DN from username"""
        if not validate_username(username):
            raise ValueError("Invalid username format")

        user_search_base = self.config.get("user_search_base", "")

        # If user_search_base is provided, search for the user
        if user_search_base:
            return self._search_user_dn(username)

        # Otherwise, use direct DN construction
        escaped_username = escape_ldap_special_chars(username)
        user_dn_pattern = self.config.get("user_dn_pattern", "cn={username},dc=example,dc=com")
        return user_dn_pattern.format(username=escaped_username)

    def _search_user_dn(self, username: str) -> str:
        """Search for user DN in LDAP directory"""
        if not validate_username(username):
            raise ValueError("Invalid username format")

        server = self._build_server()
        user_search_base = self.config["user_search_base"]
        user_search_filter = self.config.get("user_search_filter", "(sAMAccountName={username})")

        # Use service account for search if configured
        bind_dn = self.config.get("bind_dn")
        bind_password = self.config.get("bind_password")

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
            conn.search(
                search_base=user_search_base,
                search_filter=search_filter,
                attributes=[],
            )

            if conn.entries:
                return str(conn.entries[0].entry_dn)

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

        # Map LDAP attributes to common field names
        email_attr = self.config.get("email_attribute", "mail")
        username_attr = self.config.get("username_attribute", "sAMAccountName")

        return {
            "username": attributes.get(username_attr, [None])[0],
            "email": attributes.get(email_attr, [None])[0],
            "dn": user_dn,
            "raw": attributes,
        }

    def _is_user_active(self, user_info: dict[str, Any]) -> bool:
        """Check if user account is active (AD-specific)"""
        # In Active Directory, account status is in userAccountControl
        # bit 2 is ACCOUNTDISABLE
        raw_info = user_info.get("raw", {})
        user_account_control = raw_info.get("userAccountControl", [0])[0]

        return not (isinstance(user_account_control, int) and (user_account_control & 2))

    async def get_user_info(self, user_id: str) -> dict[str, Any]:
        """Get user information from LDAP"""
        try:
            server = self._build_server()
            bind_dn = self.config.get("bind_dn")
            bind_password = self.config.get("bind_password")

            conn = Connection(
                server,
                user=bind_dn,
                password=bind_password,
                auto_bind=True,
                raise_exceptions=True,
            )

            return self._get_user_info_from_ldap(conn, user_id)
        except Exception as e:
            return {"error": str(e)}

    async def test_connection(self) -> dict:
        """Test LDAP connection"""
        try:
            server = self._build_server()
            bind_dn = self.config.get("bind_dn")
            bind_password = self.config.get("bind_password")

            Connection(
                server,
                user=bind_dn,
                password=bind_password,
                auto_bind=True,
                raise_exceptions=True,
            )

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
