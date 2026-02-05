"""
Certificate Verification Middleware for Severus AI
Handles mTLS client certificate verification for incoming requests
"""

import os
import ssl
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CertificateVerifier:
    """Handles client certificate verification for mTLS"""
    
    def __init__(
        self,
        ca_bundle_path: str = "/etc/certs/ca.crt",
        enforce_mode: str = "permissive"
    ):
        """
        Initialize certificate verifier
        
        Args:
            ca_bundle_path: Path to CA bundle for verifying client certificates
            enforce_mode: "strict" (reject without cert) or "permissive" (allow without cert)
        """
        self.ca_bundle_path = ca_bundle_path
        self.enforce_mode = enforce_mode
        self.enabled = os.path.exists(ca_bundle_path)
        
        if self.enabled:
            logger.info(f"Certificate verification enabled (mode: {enforce_mode})")
            logger.info(f"CA bundle: {ca_bundle_path}")
        else:
            logger.warning(f"Certificate verification disabled - CA bundle not found at {ca_bundle_path}")
    
    def verify_client_certificate(
        self,
        cert_pem: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Verify client certificate
        
        Args:
            cert_pem: PEM-encoded client certificate
        
        Returns:
            Tuple of (is_valid, error_message, cert_info)
        """
        # If verification is disabled, allow all requests
        if not self.enabled:
            return True, None, {"mode": "disabled"}
        
        # If no certificate provided
        if not cert_pem:
            if self.enforce_mode == "strict":
                logger.warning("Request rejected: No client certificate provided")
                return False, "Client certificate required", None
            else:
                logger.info("Request allowed without certificate (permissive mode)")
                return True, None, {"mode": "permissive", "authenticated": False}
        
        try:
            # Parse certificate
            cert_info = self._parse_certificate(cert_pem)
            
            # Verify certificate against CA bundle
            is_valid = self._verify_against_ca(cert_pem)
            
            if is_valid:
                logger.info(f"✅ Valid certificate from: {cert_info.get('common_name', 'unknown')}")
                return True, None, cert_info
            else:
                logger.warning(f"❌ Invalid certificate signature")
                return False, "Certificate signature verification failed", None
                
        except Exception as e:
            logger.error(f"Certificate verification error: {e}")
            return False, f"Certificate verification error: {str(e)}", None
    
    def _parse_certificate(self, cert_pem: str) -> dict:
        """
        Parse certificate and extract information
        
        Args:
            cert_pem: PEM-encoded certificate
        
        Returns:
            Dictionary with certificate information
        """
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            
            # Load certificate
            cert = x509.load_pem_x509_certificate(
                cert_pem.encode() if isinstance(cert_pem, str) else cert_pem,
                default_backend()
            )
            
            # Extract information
            subject = cert.subject
            issuer = cert.issuer
            
            # Get common name
            cn_attr = subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
            common_name = cn_attr[0].value if cn_attr else "unknown"
            
            # Get organization
            org_attr = subject.get_attributes_for_oid(x509.oid.NameOID.ORGANIZATION_NAME)
            organization = org_attr[0].value if org_attr else "unknown"
            
            return {
                "common_name": common_name,
                "organization": organization,
                "not_before": cert.not_valid_before_utc.isoformat(),
                "not_after": cert.not_valid_after_utc.isoformat(),
                "serial_number": cert.serial_number,
                "authenticated": True
            }
            
        except Exception as e:
            logger.error(f"Error parsing certificate: {e}")
            raise
    
    def _verify_against_ca(self, cert_pem: str) -> bool:
        """
        Verify certificate signature against CA bundle
        
        Args:
            cert_pem: PEM-encoded certificate
        
        Returns:
            True if certificate is valid, False otherwise
        """
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import hashes
            from cryptography.exceptions import InvalidSignature
            
            # Load client certificate
            cert = x509.load_pem_x509_certificate(
                cert_pem.encode() if isinstance(cert_pem, str) else cert_pem,
                default_backend()
            )
            
            # Load CA bundle
            with open(self.ca_bundle_path, 'rb') as f:
                ca_cert = x509.load_pem_x509_certificate(f.read(), default_backend())
            
            # Verify signature
            try:
                ca_public_key = ca_cert.public_key()
                ca_public_key.verify(
                    cert.signature,
                    cert.tbs_certificate_bytes,
                    # Use the signature algorithm from the certificate
                    cert.signature_algorithm_parameters
                )
                return True
            except InvalidSignature:
                return False
            except Exception as e:
                logger.error(f"Signature verification error: {e}")
                # For self-signed certs, check if cert == CA cert
                if cert.subject == ca_cert.subject:
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Error verifying certificate: {e}")
            return False


# Global verifier instance
_verifier: Optional[CertificateVerifier] = None


def init_certificate_verifier(
    ca_bundle_path: str = "/etc/certs/ca.crt",
    enforce_mode: str = "permissive"
) -> CertificateVerifier:
    """
    Initialize global certificate verifier
    
    Args:
        ca_bundle_path: Path to CA bundle
        enforce_mode: "strict" or "permissive"
    
    Returns:
        CertificateVerifier instance
    """
    global _verifier
    _verifier = CertificateVerifier(ca_bundle_path, enforce_mode)
    return _verifier


def get_certificate_verifier() -> Optional[CertificateVerifier]:
    """Get global certificate verifier instance"""
    return _verifier


def verify_request_certificate(cert_pem: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[dict]]:
    """
    Verify certificate for incoming request
    
    Args:
        cert_pem: PEM-encoded client certificate
    
    Returns:
        Tuple of (is_valid, error_message, cert_info)
    """
    if _verifier is None:
        # Auto-initialize with defaults
        init_certificate_verifier()
    
    return _verifier.verify_client_certificate(cert_pem)
