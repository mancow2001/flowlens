"""SAML provider management API endpoints.

Admin-only endpoints for configuring SAML identity providers.
"""

import math
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select, update

from flowlens.api.dependencies import AdminUser, DbSession, Pagination
from flowlens.models.auth import SAMLProvider
from flowlens.schemas.auth import (
    SAMLProviderCreate,
    SAMLProviderList,
    SAMLProviderResponse,
    SAMLProviderUpdate,
)

router = APIRouter(prefix="/saml-providers", tags=["SAML Configuration"])


@router.get("", response_model=SAMLProviderList)
async def list_saml_providers(
    _user: AdminUser,
    db: DbSession,
    pagination: Pagination,
) -> SAMLProviderList:
    """List all SAML providers.

    Admin only.
    """
    query = select(SAMLProvider)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply pagination and ordering
    query = (
        query.order_by(SAMLProvider.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )

    result = await db.execute(query)
    providers = list(result.scalars().all())

    return SAMLProviderList(
        items=[SAMLProviderResponse.model_validate(p) for p in providers],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=math.ceil(total / pagination.page_size) if total > 0 else 0,
    )


@router.post("", response_model=SAMLProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_saml_provider(
    body: SAMLProviderCreate,
    _admin: AdminUser,
    db: DbSession,
) -> SAMLProviderResponse:
    """Create a new SAML provider.

    Admin only.
    """
    # Check if entity_id already exists
    existing = await db.execute(
        select(SAMLProvider).where(SAMLProvider.entity_id == body.entity_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A provider with this entity ID already exists",
        )

    # Create provider
    provider = SAMLProvider(
        name=body.name,
        provider_type=body.provider_type.value,
        entity_id=body.entity_id,
        sso_url=body.sso_url,
        slo_url=body.slo_url,
        certificate=body.certificate,
        sp_entity_id=body.sp_entity_id,
        role_attribute=body.role_attribute,
        role_mapping=body.role_mapping,
        default_role=body.default_role,
        auto_provision_users=body.auto_provision_users,
        is_active=False,  # Newly created providers are inactive
    )

    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    return SAMLProviderResponse.model_validate(provider)


@router.get("/{provider_id}", response_model=SAMLProviderResponse)
async def get_saml_provider(
    provider_id: uuid.UUID,
    _admin: AdminUser,
    db: DbSession,
) -> SAMLProviderResponse:
    """Get a SAML provider by ID.

    Admin only.
    """
    result = await db.execute(
        select(SAMLProvider).where(SAMLProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SAML provider not found",
        )

    return SAMLProviderResponse.model_validate(provider)


@router.patch("/{provider_id}", response_model=SAMLProviderResponse)
async def update_saml_provider(
    provider_id: uuid.UUID,
    body: SAMLProviderUpdate,
    _admin: AdminUser,
    db: DbSession,
) -> SAMLProviderResponse:
    """Update a SAML provider.

    Admin only.
    """
    result = await db.execute(
        select(SAMLProvider).where(SAMLProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SAML provider not found",
        )

    # Update fields if provided
    if body.name is not None:
        provider.name = body.name

    if body.provider_type is not None:
        provider.provider_type = body.provider_type.value

    if body.entity_id is not None:
        # Check if new entity_id is already in use by another provider
        if body.entity_id != provider.entity_id:
            existing = await db.execute(
                select(SAMLProvider).where(
                    SAMLProvider.entity_id == body.entity_id,
                    SAMLProvider.id != provider_id,
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A provider with this entity ID already exists",
                )
        provider.entity_id = body.entity_id

    if body.sso_url is not None:
        provider.sso_url = body.sso_url

    if body.slo_url is not None:
        provider.slo_url = body.slo_url if body.slo_url else None

    if body.certificate is not None:
        provider.certificate = body.certificate

    if body.sp_entity_id is not None:
        provider.sp_entity_id = body.sp_entity_id

    if body.role_attribute is not None:
        provider.role_attribute = body.role_attribute if body.role_attribute else None

    if body.role_mapping is not None:
        provider.role_mapping = body.role_mapping

    if body.default_role is not None:
        provider.default_role = body.default_role

    if body.auto_provision_users is not None:
        provider.auto_provision_users = body.auto_provision_users

    await db.commit()
    await db.refresh(provider)

    return SAMLProviderResponse.model_validate(provider)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saml_provider(
    provider_id: uuid.UUID,
    _admin: AdminUser,
    db: DbSession,
) -> None:
    """Delete a SAML provider.

    Admin only.
    """
    result = await db.execute(
        select(SAMLProvider).where(SAMLProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SAML provider not found",
        )

    await db.delete(provider)
    await db.commit()


@router.post("/{provider_id}/activate", response_model=SAMLProviderResponse)
async def activate_saml_provider(
    provider_id: uuid.UUID,
    _admin: AdminUser,
    db: DbSession,
) -> SAMLProviderResponse:
    """Activate a SAML provider.

    Admin only. This deactivates all other providers.
    """
    result = await db.execute(
        select(SAMLProvider).where(SAMLProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SAML provider not found",
        )

    # Deactivate all other providers
    await db.execute(
        update(SAMLProvider)
        .where(SAMLProvider.id != provider_id)
        .values(is_active=False)
    )

    # Activate this provider
    provider.is_active = True

    await db.commit()
    await db.refresh(provider)

    return SAMLProviderResponse.model_validate(provider)


@router.post("/{provider_id}/deactivate", response_model=SAMLProviderResponse)
async def deactivate_saml_provider(
    provider_id: uuid.UUID,
    _admin: AdminUser,
    db: DbSession,
) -> SAMLProviderResponse:
    """Deactivate a SAML provider.

    Admin only.
    """
    result = await db.execute(
        select(SAMLProvider).where(SAMLProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SAML provider not found",
        )

    provider.is_active = False

    await db.commit()
    await db.refresh(provider)

    return SAMLProviderResponse.model_validate(provider)
