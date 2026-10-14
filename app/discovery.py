"""mDNS/Zeroconf service discovery for DropLink."""
from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time
from typing import Optional

from zeroconf import IPVersion, ServiceInfo, Zeroconf

from .config import settings
from .network import get_local_ip

log = logging.getLogger("droplink.discovery")

SERVICE_TYPE = "_droplink._tcp.local."
_POLL_INTERVAL = 5.0


class MDNSAdvertiser:
    """Manages mDNS service registration with IP change detection."""
    
    def __init__(self) -> None:
        self._zeroconf: Optional[Zeroconf] = None
        self._service_info: Optional[ServiceInfo] = None
        self._last_advertised_ip: Optional[str] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def _get_all_ipv4_addresses(self) -> list[str]:
        """Get all non-loopback IPv4 addresses."""
        try:
            hostname = socket.gethostname()
            _, _, addrlist = socket.gethostbyname_ex(hostname)
            return [addr for addr in addrlist if not addr.startswith("127.")]
        except OSError:
            return []
    
    def _create_service_info(self, port: int) -> ServiceInfo:
        """Create the ServiceInfo object for DropLink."""
        addresses = self._get_all_ipv4_addresses()
        if not addresses:
            log.warning("No non-loopback IPv4 addresses found for mDNS")
            addresses = ["127.0.0.1"]
        
        return ServiceInfo(
            SERVICE_TYPE,
            f"{settings.device_name} (DropLink).{SERVICE_TYPE}",
            port=port,
            addresses=addresses,
            properties={
                "id": settings.device_id,
                "name": settings.device_name,
                "v": "2",
                "auth": "1" if settings.require_token else "0",
                "path": "/ping",
            },
        )
    
    def start(self, port: int) -> None:
        """Start mDNS advertising in a background thread."""
        if not settings.mdns_enabled:
            log.info("mDNS advertising disabled via DROPLINK_MDNS=0")
            return
        
        with self._lock:
            if self._running:
                log.warning("mDNS advertiser already running")
                return
            
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, args=(port,), daemon=True)
            self._thread.start()
            log.info("mDNS advertiser started on port %d", port)
    
    def _run_loop(self, port: int) -> None:
        """Main loop: register and watch for IP changes."""
        try:
            self._zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
            self._register_service(port)
            
            while self._running:
                time.sleep(_POLL_INTERVAL)
                
                if not self._running:
                    break
                
                # Check if IP changed
                current_ip = get_local_ip()
                if current_ip != self._last_advertised_ip:
                    log.info("IP changed from %s to %s, re-registering mDNS", self._last_advertised_ip, current_ip)
                    self._unregister_service()
                    self._register_service(port)
        
        except Exception as e:
            log.error("mDNS advertiser error: %s", e)
        finally:
            self._unregister_service()
            if self._zeroconf:
                self._zeroconf.close()
                self._zeroconf = None
            log.info("mDNS advertiser stopped")
    
    def _register_service(self, port: int) -> None:
        """Register the service with zeroconf."""
        if not self._zeroconf:
            return
        
        try:
            self._service_info = self._create_service_info(port)
            self._zeroconf.register_service(self._service_info)
            self._last_advertised_ip = get_local_ip()
            log.info(
                "Registered mDNS service: %s at %s:%d",
                f"{settings.device_name} (DropLink)",
                self._last_advertised_ip,
                port,
            )
        except Exception as e:
            log.warning("Failed to register mDNS service: %s", e)
            self._service_info = None
    
    def _unregister_service(self) -> None:
        """Unregister the service."""
        if self._service_info and self._zeroconf:
            try:
                self._zeroconf.unregister_service(self._service_info)
                log.info("Unregistered mDNS service")
            except Exception as e:
                log.warning("Failed to unregister mDNS service: %s", e)
            finally:
                self._service_info = None
    
    def stop(self) -> None:
        """Stop the advertiser and clean up."""
        with self._lock:
            if not self._running:
                return
            
            self._running = False
        
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None


# Global advertiser instance
_advertiser: Optional[MDNSAdvertiser] = None


def start_advertising(port: int) -> None:
    """Start mDNS advertising for the given port."""
    global _advertiser
    if _advertiser is None:
        _advertiser = MDNSAdvertiser()
    _advertiser.start(port)


def stop_advertising() -> None:
    """Stop mDNS advertising."""
    global _advertiser
    if _advertiser:
        _advertiser.stop()
