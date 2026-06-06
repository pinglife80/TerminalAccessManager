import httpx
from typing import List, Dict, Any, Optional
from loguru import logger

from app.core.config import settings


class SangforService:
    """Service for interacting with Sangfor AF API"""

    def __init__(self):
        self.base_url = settings.SANGFOR_BASE_URL.rstrip('/') if settings.SANGFOR_BASE_URL else ""
        self.username = settings.SANGFOR_USERNAME
        self.password = settings.SANGFOR_PASSWORD
        self.token = None
        self.session = None

    def _get_verify_setting(self) -> bool | str:
        """Get SSL verification setting.
        Returns True for default, or path to CA bundle if configured."""
        if settings.SANGFOR_CA_BUNDLE:
            return settings.SANGFOR_CA_BUNDLE
        return True

    async def _get_session(self) -> httpx.AsyncClient:
        """Get or create HTTP session with authentication"""
        if not self.session:
            self.session = httpx.AsyncClient(
                verify=self._get_verify_setting(),
                timeout=10.0,
                headers={'Content-Type': 'application/json'}
            )

        if not self.token:
            await self._authenticate()

        return self.session

    async def _authenticate(self):
        """Authenticate with Sangfor API and get token"""
        try:
            async with httpx.AsyncClient(
                verify=self._get_verify_setting(),
                timeout=10.0
            ) as client:
                response = await client.post(
                    f"{self.base_url}/v1/namespaces/public/login",
                    json={"name": self.username, "password": self.password}
                )
                response.raise_for_status()

                data = response.json()
                self.token = data['data']['loginResult']['token']

                # Set token in session cookies
                if self.session:
                    self.session.cookies.set('token', self.token)

                logger.info("Successfully authenticated with Sangfor API")

        except Exception as e:
            logger.error(f"Failed to authenticate with Sangfor API: {str(e)}")
            raise

    async def block_ip(self, ip_list: List[str], block_time: str = "15d") -> Dict[str, Any]:
        """Block IP addresses via Sangfor API"""
        try:
            session = await self._get_session()

            data = {
                "ipType": "SRC",
                "srcIP": ip_list,
                "blockTime": block_time
            }

            response = await session.post(
                f"{self.base_url}/batch/v1/namespaces/public/blockip",
                json=data
            )
            response.raise_for_status()

            result = response.json()
            logger.info(f"Blocked IPs: {ip_list}")

            return result

        except Exception as e:
            logger.error(f"Failed to block IPs {ip_list}: {str(e)}")
            raise

    async def unblock_ip(self, ip_list: List[Dict[str, str]]) -> Dict[str, Any]:
        """Unblock IP addresses via Sangfor API"""
        try:
            session = await self._get_session()

            response = await session.post(
                f"{self.base_url}/batch/v1/namespaces/public/blockip?_method=DELETE",
                json=ip_list
            )
            response.raise_for_status()

            result = response.json()
            logger.info(f"Unblocked IPs: {ip_list}")

            return result

        except Exception as e:
            logger.error(f"Failed to unblock IPs {ip_list}: {str(e)}")
            raise

    async def get_blocked_ips(self) -> Dict[str, Any]:
        """Get list of blocked IPs from Sangfor"""
        try:
            session = await self._get_session()

            response = await session.get(
                f"{self.base_url}/v1/namespaces/public/blockip"
            )
            response.raise_for_status()

            result = response.json()
            return result

        except Exception as e:
            logger.error(f"Failed to get blocked IPs: {str(e)}")
            raise

    async def get_system_stats(self) -> Dict[str, Any]:
        """Get CPU and memory usage from Sangfor"""
        try:
            session = await self._get_session()

            # Get memory usage
            mem_response = await session.get(
                f"{self.base_url}/v1/namespaces/public/memoryusage"
            )
            mem_response.raise_for_status()
            memory_usage = mem_response.json()['data']['memoryUsage']

            # Get CPU usage
            cpu_response = await session.get(
                f"{self.base_url}/v1/namespaces/public/cpuusage"
            )
            cpu_response.raise_for_status()
            cpu_usage = cpu_response.json()['data']['cpuCurrent']

            return {
                'cpu': cpu_usage,
                'memory': memory_usage
            }

        except Exception as e:
            logger.error(f"Failed to get system stats: {str(e)}")
            raise

    async def close(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.aclose()
            self.session = None
            self.token = None
