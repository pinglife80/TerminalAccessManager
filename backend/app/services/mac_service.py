import re
import ipaddress
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, or_
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from loguru import logger

from app.models.mac_address import MacAddress
from app.models.whitelist import Whitelist
from app.models.blacklist import Blacklist
from app.models.log import AuditLog
from app.schemas.mac_address import MacAddressQuery
from app.services.sangfor_service import SangforService


class IPAddressParser:
    """Utility class to parse and expand IP addresses, CIDR subnets, and IP ranges"""
    
    @staticmethod
    def parse_ip_input(ip_input: str) -> List[str]:
        """Parse IP input and return list of IP addresses"""
        ip_input = ip_input.strip()
        
        if '/' in ip_input:
            if '-' in ip_input:
                return IPAddressParser._parse_ip_range_with_subnet(ip_input)
            else:
                return IPAddressParser._parse_cidr(ip_input)
        elif '-' in ip_input:
            return IPAddressParser._parse_ip_range(ip_input)
        else:
            return [ip_input]
    
    @staticmethod
    def _parse_cidr(cidr: str) -> List[str]:
        """Parse CIDR notation and return list of IP addresses"""
        try:
            network = ipaddress.IPv4Network(cidr, strict=False)
            return [str(ip) for ip in network.hosts()]
        except ValueError:
            raise ValueError(f"Invalid CIDR notation: {cidr}")
    
    @staticmethod
    def _parse_ip_range(ip_range: str) -> List[str]:
        """Parse IP range like 192.168.1.1-100"""
        match = re.match(r'^(\d+\.\d+\.\d+)\.(\d+)-(\d+)$', ip_range)
        if not match:
            raise ValueError(f"Invalid IP range format: {ip_range}. Expected: 192.168.1.1-100")
        
        prefix = match.group(1)
        start = int(match.group(2))
        end = int(match.group(3))
        
        if start > end:
            raise ValueError(f"Invalid IP range: start ({start}) > end ({end})")
        if end > 255:
            raise ValueError(f"IP range end ({end}) exceeds 255")
        
        return [f"{prefix}.{i}" for i in range(start, end + 1)]
    
    @staticmethod
    def _parse_ip_range_with_subnet(ip_range: str) -> List[str]:
        """Parse IP range with subnet like 192.168.1.1-100/24"""
        subnet_match = re.match(r'^(.+)/(\d+)$', ip_range)
        if not subnet_match:
            raise ValueError(f"Invalid IP range with subnet: {ip_range}")
        
        range_part = subnet_match.group(1)
        subnet_bits = int(subnet_match.group(2))
        
        match = re.match(r'^(\d+\.\d+\.\d+)\.(\d+)-(\d+)$', range_part)
        if not match:
            raise ValueError(f"Invalid IP range format: {range_part}")
        
        prefix = match.group(1)
        start = int(match.group(2))
        end = int(match.group(3))
        
        if start > end:
            raise ValueError(f"Invalid IP range: start ({start}) > end ({end})")
        if end > 255:
            raise ValueError(f"IP range end ({end}) exceeds 255")
        
        ip_addresses = [f"{prefix}.{i}" for i in range(start, end + 1)]
        
        try:
            network = ipaddress.IPv4Network(f"{prefix}.0/{subnet_bits}", strict=False)
            return [ip for ip in ip_addresses if ipaddress.IPv4Address(ip) in network]
        except ValueError:
            raise ValueError(f"Invalid subnet: /{subnet_bits}")
    
    @staticmethod
    def validate_ip(ip: str) -> bool:
        """Validate a single IP address"""
        try:
            ipaddress.IPv4Address(ip)
            return True
        except ValueError:
            return False


class MacService:
    """Service for MAC address management operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.sangfor = SangforService()
    
    async def get_invalid_macs(self, skip: int = 0, limit: int = 50) -> List[MacAddress]:
        """Get invalid (unfrozen) MAC addresses with pagination"""
        try:
            stmt = (
                select(MacAddress)
                .where(MacAddress.status == "unfrozen")
                .order_by(desc(MacAddress.timestamp))
                .offset(skip)
                .limit(limit)
            )
            
            result = await self.db.execute(stmt)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Error getting invalid MACs: {str(e)}")
            raise
    
    async def search_macs(self, query: MacAddressQuery) -> List[MacAddress]:
        """Search MAC addresses by various criteria"""
        try:
            conditions = []
            
            if query.ip:
                conditions.append(MacAddress.ip_address == query.ip)
            
            if query.mac:
                # Normalize MAC format
                normalized_mac = self._normalize_mac(query.mac)
                conditions.append(MacAddress.mac_address == normalized_mac)
            
            if query.status:
                conditions.append(MacAddress.status == query.status)
            
            stmt = (
                select(MacAddress)
                .where(and_(*conditions) if conditions else True)
                .order_by(desc(MacAddress.timestamp))
                .offset(query.skip)
                .limit(query.limit)
            )
            
            result = await self.db.execute(stmt)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Error searching MACs: {str(e)}")
            raise
    
    async def block_ip(self, ip_address: str, mac_address: str, username: str) -> dict:
        """Block an IP address via Sangfor API and update database"""
        try:
            # Call Sangfor API to block IP
            response = await self.sangfor.block_ip([ip_address])
            
            if response.get('code') == 0:
                # Update MAC address status in database
                stmt = (
                    select(MacAddress)
                    .where(MacAddress.ip_address == ip_address)
                    .where(MacAddress.mac_address == mac_address)
                )
                result = await self.db.execute(stmt)
                mac_record = result.scalar_one_or_none()
                
                if mac_record:
                    mac_record.status = "frozen"
                
                # Add to blacklist
                blacklist_entry = Blacklist(
                    ip_address=ip_address,
                    mac_address=mac_address,
                    blocked_by=username
                )
                self.db.add(blacklist_entry)
                
                # Log the action
                await self._log_action(username, "block_ip", "mac", ip_address, 
                                     f"Blocked IP {ip_address} (MAC: {mac_address})")
                
                await self.db.commit()
                
                logger.info(f"Successfully blocked IP: {ip_address}")
                return {"success": True, "message": "IP blocked successfully"}
            else:
                error_msg = response.get('message', 'Unknown error')
                logger.error(f"Sangfor API error: {error_msg}")
                return {"success": False, "message": f"Sangfor API error: {error_msg}"}
                
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error blocking IP {ip_address}: {str(e)}")
            raise
        finally:
            await self.sangfor.close()
    
    async def unblock_ip(self, ip_address: str, username: str) -> dict:
        """Unblock an IP address via Sangfor API"""
        try:
            # Call Sangfor API to unblock IP
            response = await self.sangfor.unblock_ip([{"srcIP": ip_address}])
            
            if response.get('code') == 0:
                # Update MAC address status
                stmt = (
                    select(MacAddress)
                    .where(MacAddress.ip_address == ip_address)
                )
                result = await self.db.execute(stmt)
                mac_records = result.scalars().all()
                
                for record in mac_records:
                    record.status = "unfrozen"
                
                # Log the action
                await self._log_action(username, "unblock_ip", "mac", ip_address,
                                     f"Unblocked IP {ip_address}")
                
                await self.db.commit()
                
                logger.info(f"Successfully unblocked IP: {ip_address}")
                return {"success": True, "message": "IP unblocked successfully"}
            else:
                error_msg = response.get('message', 'Unknown error')
                logger.error(f"Sangfor API error: {error_msg}")
                return {"success": False, "message": f"Sangfor API error: {error_msg}"}
                
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error unblocking IP {ip_address}: {str(e)}")
            raise
        finally:
            await self.sangfor.close()
    
    async def add_to_whitelist(self, mac_address: str = None, ip_address: str = None, comments: str = "", username: str = "") -> dict:
        """Add to whitelist by MAC address, IP address, CIDR subnet, or IP range"""
        try:
            normalized_mac = None
            
            if mac_address:
                normalized_mac = self._normalize_mac(mac_address)
            
            ip_addresses = []
            if ip_address:
                ip_addresses = IPAddressParser.parse_ip_input(ip_address)
            
            added_count = 0
            skipped_count = 0
            errors = []
            
            for ip_addr in ip_addresses:
                try:
                    if mac_address and ip_addr:
                        stmt = select(MacAddress).where(MacAddress.ip_address == ip_addr)
                        result = await self.db.execute(stmt)
                        mac_record = result.scalar_one_or_none()
                        
                        if mac_record and mac_record.mac_address != normalized_mac:
                            errors.append(f"IP {ip_addr} is bound to different MAC: {mac_record.mac_address}")
                            skipped_count += 1
                            continue
                    
                    stmt = select(Whitelist).where(Whitelist.ip_address == ip_addr)
                    result = await self.db.execute(stmt)
                    existing = result.scalar_one_or_none()
                    
                    if existing:
                        existing.comments = comments
                        if normalized_mac:
                            existing.mac_address = normalized_mac
                    else:
                        whitelist_entry = Whitelist(
                            mac_address=normalized_mac,
                            ip_address=ip_addr,
                            comments=comments,
                            added_by=username
                        )
                        self.db.add(whitelist_entry)
                    
                    added_count += 1
                except Exception as e:
                    errors.append(f"Error adding IP {ip_addr}: {str(e)}")
                    skipped_count += 1
            
            if mac_address and not ip_address:
                stmt = select(Whitelist).where(Whitelist.mac_address == normalized_mac)
                result = await self.db.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    existing.comments = comments
                else:
                    whitelist_entry = Whitelist(
                        mac_address=normalized_mac,
                        ip_address=None,
                        comments=comments,
                        added_by=username
                    )
                    self.db.add(whitelist_entry)
                added_count += 1
                
                stmt = select(MacAddress).where(MacAddress.mac_address == normalized_mac)
                result = await self.db.execute(stmt)
                mac_record = result.scalar_one_or_none()
                
                if mac_record:
                    await self.db.delete(mac_record)
            
            if normalized_mac:
                stmt = select(MacAddress).where(MacAddress.mac_address == normalized_mac)
                result = await self.db.execute(stmt)
                mac_record = result.scalar_one_or_none()
                
                if mac_record:
                    await self.db.delete(mac_record)
            
            if ip_address and mac_address:
                if len(ip_addresses) == 1:
                    log_details = f"Added MAC {normalized_mac} and IP {ip_addresses[0]} to whitelist"
                else:
                    log_details = f"Added MAC {normalized_mac} and {len(ip_addresses)} IP addresses (starting with {ip_addresses[0]}) to whitelist"
                resource_id = normalized_mac
            elif ip_address:
                if len(ip_addresses) == 1:
                    log_details = f"Added IP {ip_addresses[0]} to whitelist"
                elif len(ip_addresses) <= 3:
                    log_details = f"Added IPs {', '.join(ip_addresses)} to whitelist"
                else:
                    log_details = f"Added IP range/subnet ({len(ip_addresses)} addresses, starting with {ip_addresses[0]}) to whitelist"
                resource_id = ip_address
            elif mac_address:
                log_details = f"Added MAC {normalized_mac} to whitelist"
                resource_id = normalized_mac
            else:
                log_details = "Added entry to whitelist"
                resource_id = None
            await self._log_action(username, "add_whitelist", "whitelist", resource_id, log_details)
            
            await self.db.commit()
            
            return {
                "success": True,
                "added": added_count,
                "skipped": skipped_count,
                "errors": errors,
                "message": f"Successfully added {added_count} terminal(s) to whitelist"
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error adding to whitelist: {str(e)}")
            raise
    
    async def get_whitelist(self, skip: int = 0, limit: int = 50) -> List[Whitelist]:
        """Get whitelist entries"""
        stmt = (
            select(Whitelist)
            .order_by(desc(Whitelist.created_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def delete_from_whitelist(self, identifier: str, username: str) -> bool:
        """Delete from whitelist by MAC address or IP address"""
        try:
            whitelist_entry = None
            
            cleaned_identifier = identifier.replace('-', '').replace(':', '').replace('.', '').upper()
            
            if len(cleaned_identifier) == 12 and cleaned_identifier.isalnum():
                normalized_mac = self._normalize_mac(identifier)
                stmt = select(Whitelist).where(Whitelist.mac_address == normalized_mac)
                result = await self.db.execute(stmt)
                whitelist_entry = result.scalar_one_or_none()
            else:
                stmt = select(Whitelist).where(Whitelist.ip_address == identifier)
                result = await self.db.execute(stmt)
                whitelist_entry = result.scalar_one_or_none()
            
            if whitelist_entry:
                await self.db.delete(whitelist_entry)
                
                log_details_parts = []
                if whitelist_entry.mac_address:
                    log_details_parts.append(f"MAC {whitelist_entry.mac_address}")
                if whitelist_entry.ip_address:
                    log_details_parts.append(f"IP {whitelist_entry.ip_address}")
                log_details = f"Removed {' and '.join(log_details_parts)} from whitelist"
                
                resource_id = whitelist_entry.mac_address if whitelist_entry.mac_address else whitelist_entry.ip_address
                await self._log_action(username, "remove_whitelist", "whitelist", resource_id, log_details)
                
                await self.db.commit()
                return True
            
            return False
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting from whitelist: {str(e)}")
            raise
    
    async def _log_action(self, username: str, action: str, resource_type: str,
                         resource_id: str, details: str):
        """Log an audit action"""
        audit_log = AuditLog(
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details
        )
        self.db.add(audit_log)
    
    async def get_blacklist(self, skip: int = 0, limit: int = 50) -> List[Blacklist]:
        """Get blacklist entries"""
        stmt = (
            select(Blacklist)
            .order_by(desc(Blacklist.blocked_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def add_to_blacklist(self, ip_address: str = "", mac_address: str = None, reason: str = "", username: str = "") -> dict:
        """Add to blacklist by IP address, MAC address, or both"""
        try:
            normalized_mac = None
            if mac_address:
                normalized_mac = self._normalize_mac(mac_address)
            
            future_date = datetime.now(timezone.utc) + timedelta(days=30)
            
            blacklist_entry = Blacklist(
                ip_address=ip_address or None,
                mac_address=normalized_mac,
                reason=reason,
                expires_at=future_date,
                blocked_by=username
            )
            self.db.add(blacklist_entry)
            
            log_details_parts = []
            if normalized_mac:
                log_details_parts.append(f"MAC {normalized_mac}")
            if ip_address:
                log_details_parts.append(f"IP {ip_address}")
            log_details = f"Blocked {' and '.join(log_details_parts)} - {reason}"
            
            resource_id = normalized_mac if normalized_mac else ip_address
            await self._log_action(username, "block", "blacklist", resource_id, log_details)
            
            await self.db.commit()
            
            return {
                "success": True,
                "message": "Successfully blocked terminal"
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error adding to blacklist: {str(e)}")
            raise
    
    async def delete_from_blacklist(self, identifier: str, username: str) -> bool:
        """Delete from blacklist by MAC address or IP address"""
        try:
            blacklist_entry = None
            
            cleaned_identifier = identifier.replace('-', '').replace(':', '').replace('.', '').upper()
            
            if len(cleaned_identifier) == 12 and cleaned_identifier.isalnum():
                normalized_mac = self._normalize_mac(identifier)
                stmt = select(Blacklist).where(Blacklist.mac_address == normalized_mac)
                result = await self.db.execute(stmt)
                blacklist_entry = result.scalar_one_or_none()
            else:
                stmt = select(Blacklist).where(Blacklist.ip_address == identifier)
                result = await self.db.execute(stmt)
                blacklist_entry = result.scalar_one_or_none()
            
            if blacklist_entry:
                log_details_parts = []
                if blacklist_entry.mac_address:
                    log_details_parts.append(f"MAC {blacklist_entry.mac_address}")
                if blacklist_entry.ip_address:
                    log_details_parts.append(f"IP {blacklist_entry.ip_address}")
                log_details = f"Unblocked {' and '.join(log_details_parts)}"
                
                resource_id = blacklist_entry.mac_address if blacklist_entry.mac_address else blacklist_entry.ip_address
                await self._log_action(username, "unblock", "blacklist", resource_id, log_details)
                
                await self.db.delete(blacklist_entry)
                await self.db.commit()
                return True
            
            return False
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting from blacklist: {str(e)}")
            raise

    @staticmethod
    def _normalize_mac(mac: str) -> str:
        """Normalize MAC address format to XX-XX-XX-XX-XX-XX"""
        # Remove separators and convert to uppercase
        mac_clean = mac.replace('-', '').replace(':', '').replace('.', '').upper()
        
        # Add hyphens every 2 characters
        formatted = '-'.join(mac_clean[i:i+2] for i in range(0, len(mac_clean), 2))
        
        return formatted
