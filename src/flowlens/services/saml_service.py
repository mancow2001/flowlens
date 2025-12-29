"""SAML authentication service.

Handles SAML SSO authentication using python3-saml.
"""

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.config import get_settings
from flowlens.common.exceptions import AuthenticationError, NotFoundError
from flowlens.common.logging import get_logger
from flowlens.models.auth import (
    AuthAuditLog,
    AuthEventType,
    SAMLProvider,
    User,
    UserRole,
)
from flowlens.services.auth_service import AuthService, TokenPair

logger = get_logger(__name__)


class SAMLService:
    """Service for SAML authentication operations."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize SAML service.

        Args:
            db: Database session.
        """
        self.db = db
        self.settings = get_settings()

    async def get_active_provider(self) -> SAMLProvider | None:
        """Get the active SAML provider.

        Returns:
            Active SAML provider or None if no provider is active.
        """
        result = await self.db.execute(
            select(SAMLProvider).where(SAMLProvider.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()

    def _prepare_request(
        self,
        request_url: str,
        request_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Prepare request data for python3-saml.

        Args:
            request_url: Full request URL.
            request_data: Request data (form data for POST, query params for GET).

        Returns:
            Request dict for python3-saml.
        """
        parsed = urlparse(request_url)
        return {
            "https": "on" if parsed.scheme == "https" else "off",
            "http_host": parsed.netloc,
            "script_name": parsed.path,
            "get_data": request_data if not request_data.get("SAMLResponse") else {},
            "post_data": request_data if request_data.get("SAMLResponse") else {},
        }

    def _get_saml_settings(self, provider: SAMLProvider) -> dict[str, Any]:
        """Build SAML settings dict for python3-saml.

        Args:
            provider: SAML provider configuration.

        Returns:
            Settings dict for OneLogin_Saml2_Auth.
        """
        # Build ACS URL from settings
        base_url = self.settings.saml.sp_base_url.rstrip("/")
        acs_url = f"{base_url}/api/v1/auth/saml/acs"
        slo_url = f"{base_url}/api/v1/auth/saml/slo"
        metadata_url = f"{base_url}/api/v1/auth/saml/metadata"

        return {
            "strict": True,
            "debug": not self.settings.is_production,
            "sp": {
                "entityId": provider.sp_entity_id,
                "assertionConsumerService": {
                    "url": acs_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
                },
                "singleLogoutService": {
                    "url": slo_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
            },
            "idp": {
                "entityId": provider.entity_id,
                "singleSignOnService": {
                    "url": provider.sso_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "singleLogoutService": {
                    "url": provider.slo_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                } if provider.slo_url else None,
                "x509cert": provider.certificate,
            },
            "security": {
                "nameIdEncrypted": False,
                "authnRequestsSigned": False,
                "logoutRequestSigned": False,
                "logoutResponseSigned": False,
                "signMetadata": False,
                "wantMessagesSigned": True,
                "wantAssertionsSigned": True,
                "wantNameId": True,
                "wantNameIdEncrypted": False,
                "wantAssertionsEncrypted": False,
                "allowSingleLabelDomains": False,
                "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
                "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256",
            },
        }

    async def initiate_login(
        self,
        request_url: str,
        relay_state: str | None = None,
    ) -> str:
        """Initiate SAML login flow.

        Args:
            request_url: Current request URL.
            relay_state: Optional relay state (return URL after auth).

        Returns:
            Redirect URL to IdP.

        Raises:
            NotFoundError: If no active SAML provider.
        """
        provider = await self.get_active_provider()
        if not provider:
            raise NotFoundError("No active SAML provider configured")

        settings = self._get_saml_settings(provider)
        req = self._prepare_request(request_url, {})

        auth = OneLogin_Saml2_Auth(req, settings)
        return auth.login(return_to=relay_state)

    async def process_acs(
        self,
        request_url: str,
        request_data: dict[str, Any],
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[User, TokenPair]:
        """Process SAML Assertion Consumer Service callback.

        Args:
            request_url: Current request URL.
            request_data: POST data from IdP.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Returns:
            Tuple of (user, token_pair).

        Raises:
            AuthenticationError: If SAML response is invalid.
            NotFoundError: If no active SAML provider.
        """
        provider = await self.get_active_provider()
        if not provider:
            raise NotFoundError("No active SAML provider configured")

        settings = self._get_saml_settings(provider)
        req = self._prepare_request(request_url, request_data)

        auth = OneLogin_Saml2_Auth(req, settings)
        auth.process_response()

        errors = auth.get_errors()
        if errors:
            error_reason = auth.get_last_error_reason()
            logger.warning(
                "SAML authentication failed",
                errors=errors,
                reason=error_reason,
            )

            # Log failed attempt
            audit_log = AuthAuditLog.create_event(
                event_type=AuthEventType.SAML_LOGIN_FAILED,
                email=None,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                event_details={
                    "provider_id": str(provider.id),
                    "errors": errors,
                    "reason": error_reason,
                },
            )
            self.db.add(audit_log)
            await self.db.commit()

            raise AuthenticationError(f"SAML authentication failed: {error_reason}")

        if not auth.is_authenticated():
            raise AuthenticationError("SAML authentication failed: not authenticated")

        # Extract user attributes
        attributes = auth.get_attributes()
        name_id = auth.get_nameid()

        logger.info(
            "SAML authentication successful",
            name_id=name_id,
            attributes=attributes,
        )

        # Get or create user
        user = await self._get_or_create_saml_user(
            provider=provider,
            name_id=name_id,
            attributes=attributes,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Generate tokens
        auth_service = AuthService(self.db)
        token_pair = await auth_service.create_session(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Log successful login
        audit_log = AuthAuditLog.create_event(
            event_type=AuthEventType.SAML_LOGIN,
            user_id=user.id,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True,
            event_details={
                "provider_id": str(provider.id),
                "name_id": name_id,
            },
        )
        self.db.add(audit_log)

        # Update last login
        user.last_login_at = datetime.now(timezone.utc)
        await self.db.commit()

        return user, token_pair

    async def _get_or_create_saml_user(
        self,
        provider: SAMLProvider,
        name_id: str,
        attributes: dict[str, list[str]],
        ip_address: str | None,
        user_agent: str | None,
    ) -> User:
        """Get existing user or create new one from SAML response.

        Args:
            provider: SAML provider.
            name_id: SAML NameID (usually email).
            attributes: SAML attributes from IdP.
            ip_address: Client IP address.
            user_agent: Client user agent.

        Returns:
            User object.

        Raises:
            AuthenticationError: If user cannot be created/found.
        """
        # Try to find user by SAML subject ID first
        result = await self.db.execute(
            select(User).where(User.saml_subject_id == name_id)
        )
        user = result.scalar_one_or_none()

        if user:
            # Update role if role mapping changed
            new_role = self._determine_role(provider, attributes)
            if new_role != user.role:
                user.role = new_role
            return user

        # Try to find by email (for linking existing accounts)
        email = name_id.lower()  # NameID is typically email
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()

        if user:
            # Link existing user to SAML
            user.saml_subject_id = name_id
            user.is_local = False
            # Update role based on SAML attributes
            user.role = self._determine_role(provider, attributes)
            return user

        # Create new user if auto-provisioning is enabled
        if not provider.auto_provision_users:
            raise AuthenticationError(
                "User not found and auto-provisioning is disabled"
            )

        # Extract name from attributes
        name = self._extract_name(attributes) or email.split("@")[0]
        role = self._determine_role(provider, attributes)

        user = User(
            email=email,
            name=name,
            role=role,
            is_active=True,
            is_local=False,
            saml_subject_id=name_id,
            hashed_password=None,
        )
        self.db.add(user)

        # Log user creation
        audit_log = AuthAuditLog.create_event(
            event_type=AuthEventType.USER_CREATED,
            user_id=user.id,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True,
            event_details={
                "action": "saml_auto_provision",
                "provider_id": str(provider.id),
                "role": role,
            },
        )
        self.db.add(audit_log)

        return user

    def _extract_name(self, attributes: dict[str, list[str]]) -> str | None:
        """Extract display name from SAML attributes.

        Args:
            attributes: SAML attributes.

        Returns:
            Display name or None.
        """
        # Common attribute names for display name
        name_attrs = [
            "displayName",
            "http://schemas.microsoft.com/identity/claims/displayname",
            "name",
            "cn",
            "givenName",
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
        ]

        for attr in name_attrs:
            if attr in attributes and attributes[attr]:
                return attributes[attr][0]

        # Try to construct from first/last name
        first_name = None
        last_name = None

        first_name_attrs = [
            "givenName",
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
            "firstName",
        ]
        last_name_attrs = [
            "sn",
            "surname",
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
            "lastName",
        ]

        for attr in first_name_attrs:
            if attr in attributes and attributes[attr]:
                first_name = attributes[attr][0]
                break

        for attr in last_name_attrs:
            if attr in attributes and attributes[attr]:
                last_name = attributes[attr][0]
                break

        if first_name and last_name:
            return f"{first_name} {last_name}"
        elif first_name:
            return first_name

        return None

    def _determine_role(
        self,
        provider: SAMLProvider,
        attributes: dict[str, list[str]],
    ) -> str:
        """Determine user role from SAML attributes.

        Args:
            provider: SAML provider with role mapping config.
            attributes: SAML attributes from IdP.

        Returns:
            Role string (admin, analyst, or viewer).
        """
        if not provider.role_attribute or not provider.role_mapping:
            return provider.default_role

        # Get role values from attributes
        role_values = attributes.get(provider.role_attribute, [])

        # Check each role value against mapping
        for role_value in role_values:
            if role_value in provider.role_mapping:
                mapped_role = provider.role_mapping[role_value]
                # Validate role
                if mapped_role in [r.value for r in UserRole]:
                    return mapped_role

        return provider.default_role

    def generate_metadata(self, provider: SAMLProvider) -> str:
        """Generate SP metadata XML.

        Args:
            provider: SAML provider configuration.

        Returns:
            SP metadata XML string.
        """
        settings = self._get_saml_settings(provider)

        # Create a dummy request for metadata generation
        base_url = self.settings.saml.sp_base_url.rstrip("/")
        parsed = urlparse(base_url)
        req = {
            "https": "on" if parsed.scheme == "https" else "off",
            "http_host": parsed.netloc,
            "script_name": "/api/v1/auth/saml/metadata",
            "get_data": {},
            "post_data": {},
        }

        auth = OneLogin_Saml2_Auth(req, settings)
        metadata = auth.get_settings().get_sp_metadata()

        return metadata

    def validate_metadata(self, metadata: str) -> dict[str, Any] | None:
        """Validate and parse IdP metadata XML.

        Args:
            metadata: IdP metadata XML string.

        Returns:
            Parsed metadata dict or None if invalid.
        """
        try:
            return OneLogin_Saml2_IdPMetadataParser.parse(metadata)
        except Exception as e:
            logger.warning("Failed to parse IdP metadata", error=str(e))
            return None
