"""Folders API endpoints for organizing applications hierarchically."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from flowlens.api.dependencies import DbSession, ViewerUser, AnalystUser
from flowlens.models.asset import Application
from flowlens.models.folder import Folder
from flowlens.schemas.folder import (
    ApplicationInFolder,
    FolderCreate,
    FolderList,
    FolderPath,
    FolderResponse,
    FolderSummary,
    FolderTree,
    FolderTreeNode,
    FolderUpdate,
    MoveFolderRequest,
)

router = APIRouter(prefix="/folders", tags=["folders"])


def build_folder_tree_node(folder: Folder) -> FolderTreeNode:
    """Recursively build a folder tree node from a Folder model."""
    return FolderTreeNode(
        id=folder.id,
        name=folder.name,
        display_name=folder.display_name,
        color=folder.color,
        icon=folder.icon,
        order=folder.order,
        parent_id=folder.parent_id,
        children=[build_folder_tree_node(child) for child in folder.children],
        applications=[
            ApplicationInFolder.model_validate(app) for app in folder.applications
        ],
    )


@router.get("", response_model=FolderList)
async def list_folders(
    db: DbSession,
    user: ViewerUser,
    parent_id: UUID | None = None,
) -> FolderList:
    """List folders.

    Args:
        parent_id: Filter by parent folder. None = root folders.
    """
    query = select(Folder).where(Folder.parent_id == parent_id)
    query = query.order_by(Folder.order, Folder.name)

    result = await db.execute(query)
    folders = result.scalars().all()

    return FolderList(
        items=[FolderSummary.model_validate(f) for f in folders],
        total=len(folders),
    )


@router.get("/tree", response_model=FolderTree)
async def get_folder_tree(
    db: DbSession,
    user: ViewerUser,
) -> FolderTree:
    """Get complete folder hierarchy as a tree structure."""
    # Get all root folders with their children and applications eagerly loaded
    query = (
        select(Folder)
        .where(Folder.parent_id == None)  # noqa: E711
        .options(
            selectinload(Folder.children).selectinload(Folder.children),
            selectinload(Folder.children).selectinload(Folder.applications),
            selectinload(Folder.applications),
        )
        .order_by(Folder.order, Folder.name)
    )

    result = await db.execute(query)
    root_folders = result.scalars().all()

    # Count totals
    folder_count_result = await db.execute(select(func.count(Folder.id)))
    total_folders = folder_count_result.scalar() or 0

    app_count_result = await db.execute(select(func.count(Application.id)))
    total_applications = app_count_result.scalar() or 0

    return FolderTree(
        roots=[build_folder_tree_node(f) for f in root_folders],
        total_folders=total_folders,
        total_applications=total_applications,
    )


@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    folder_data: FolderCreate,
    db: DbSession,
    user: AnalystUser,
) -> FolderResponse:
    """Create a new folder."""
    # Verify parent exists if specified
    if folder_data.parent_id:
        parent_result = await db.execute(
            select(Folder).where(Folder.id == folder_data.parent_id)
        )
        parent = parent_result.scalar_one_or_none()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Parent folder {folder_data.parent_id} not found",
            )

    # Check for duplicate name within parent
    existing_result = await db.execute(
        select(Folder)
        .where(Folder.parent_id == folder_data.parent_id)
        .where(Folder.name == folder_data.name)
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Folder with name '{folder_data.name}' already exists in this location",
        )

    # Create folder
    folder = Folder(
        name=folder_data.name,
        display_name=folder_data.display_name,
        description=folder_data.description,
        parent_id=folder_data.parent_id,
        color=folder_data.color,
        icon=folder_data.icon,
        order=folder_data.order,
        owner=folder_data.owner,
        team=folder_data.team,
        tags=folder_data.tags,
        extra_data=folder_data.metadata,
    )

    db.add(folder)
    await db.commit()
    await db.refresh(folder)

    return FolderResponse.model_validate(folder)


@router.get("/{folder_id}", response_model=FolderResponse)
async def get_folder(
    folder_id: UUID,
    db: DbSession,
    user: ViewerUser,
) -> FolderResponse:
    """Get a folder by ID."""
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    folder = result.scalar_one_or_none()

    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder {folder_id} not found",
        )

    return FolderResponse.model_validate(folder)


@router.patch("/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: UUID,
    folder_data: FolderUpdate,
    db: DbSession,
    user: AnalystUser,
) -> FolderResponse:
    """Update a folder."""
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    folder = result.scalar_one_or_none()

    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder {folder_id} not found",
        )

    # Check for name conflict if name is being changed
    update_data = folder_data.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != folder.name:
        existing_result = await db.execute(
            select(Folder)
            .where(Folder.parent_id == folder.parent_id)
            .where(Folder.name == update_data["name"])
            .where(Folder.id != folder_id)
        )
        if existing_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Folder with name '{update_data['name']}' already exists in this location",
            )

    # Handle metadata field name mapping
    if "metadata" in update_data:
        update_data["extra_data"] = update_data.pop("metadata")

    # Update fields
    for field, value in update_data.items():
        setattr(folder, field, value)

    await db.commit()
    await db.refresh(folder)

    return FolderResponse.model_validate(folder)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: UUID,
    db: DbSession,
    user: AnalystUser,
) -> None:
    """Delete a folder.

    Applications in the folder will have their folder_id set to NULL.
    Child folders will have their parent_id set to NULL (moved to root).
    """
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    folder = result.scalar_one_or_none()

    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder {folder_id} not found",
        )

    await db.delete(folder)
    await db.commit()


@router.post("/{folder_id}/move", response_model=FolderResponse)
async def move_folder(
    folder_id: UUID,
    move_request: MoveFolderRequest,
    db: DbSession,
    user: AnalystUser,
) -> FolderResponse:
    """Move a folder to a new parent."""
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    folder = result.scalar_one_or_none()

    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder {folder_id} not found",
        )

    # Verify new parent exists if specified
    if move_request.new_parent_id:
        parent_result = await db.execute(
            select(Folder).where(Folder.id == move_request.new_parent_id)
        )
        new_parent = parent_result.scalar_one_or_none()
        if not new_parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target parent folder {move_request.new_parent_id} not found",
            )

        # Prevent moving folder to itself or its descendant
        if move_request.new_parent_id == folder_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot move folder to itself",
            )

        # Check if new parent is a descendant of this folder (would create cycle)
        # Walk up from new_parent to check if we reach this folder
        current = new_parent
        while current.parent_id is not None:
            if current.parent_id == folder_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot move folder to its own descendant",
                )
            parent_result = await db.execute(
                select(Folder).where(Folder.id == current.parent_id)
            )
            current = parent_result.scalar_one_or_none()
            if not current:
                break

    # Check for name conflict in new parent
    existing_result = await db.execute(
        select(Folder)
        .where(Folder.parent_id == move_request.new_parent_id)
        .where(Folder.name == folder.name)
        .where(Folder.id != folder_id)
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Folder with name '{folder.name}' already exists in target location",
        )

    folder.parent_id = move_request.new_parent_id
    await db.commit()
    await db.refresh(folder)

    return FolderResponse.model_validate(folder)


@router.get("/{folder_id}/path", response_model=FolderPath)
async def get_folder_path(
    folder_id: UUID,
    db: DbSession,
    user: ViewerUser,
) -> FolderPath:
    """Get the path from root to a folder."""
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    folder = result.scalar_one_or_none()

    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder {folder_id} not found",
        )

    # Build path by walking up the tree
    path = [FolderSummary.model_validate(folder)]
    current = folder

    while current.parent_id is not None:
        parent_result = await db.execute(
            select(Folder).where(Folder.id == current.parent_id)
        )
        current = parent_result.scalar_one_or_none()
        if current:
            path.insert(0, FolderSummary.model_validate(current))
        else:
            break

    return FolderPath(path=path)


@router.get("/{folder_id}/contents", response_model=FolderTreeNode)
async def get_folder_contents(
    folder_id: UUID,
    db: DbSession,
    user: ViewerUser,
) -> FolderTreeNode:
    """Get a folder with its children and applications."""
    result = await db.execute(
        select(Folder)
        .where(Folder.id == folder_id)
        .options(
            selectinload(Folder.children),
            selectinload(Folder.applications),
        )
    )
    folder = result.scalar_one_or_none()

    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder {folder_id} not found",
        )

    return build_folder_tree_node(folder)
