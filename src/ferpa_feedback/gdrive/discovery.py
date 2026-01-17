"""Google Drive folder discovery and mapping for the FERPA feedback pipeline.

This module provides folder structure discovery, document enumeration, and
pattern-based filtering for Google Drive hierarchies.

Example:
    from ferpa_feedback.gdrive.discovery import FolderDiscovery, FolderMap

    discovery = FolderDiscovery(service)
    folder_map = discovery.discover_structure(root_folder_id)

    # Filter to specific folders
    september_folders = folder_map.filter_by_pattern("September*")
"""

import fnmatch
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Iterator, List, Optional

from ferpa_feedback.gdrive.errors import DiscoveryTimeoutError, DriveAccessError


@dataclass
class DriveDocument:
    """Represents a document discovered in Google Drive.

    Attributes:
        id: Google Drive file ID.
        name: Document name (filename).
        mime_type: MIME type of the document.
        parent_folder_id: ID of the parent folder.
        modified_time: ISO 8601 timestamp of last modification.
        size_bytes: File size in bytes (None for Google Docs native format).
    """

    id: str
    name: str
    mime_type: str
    parent_folder_id: str
    modified_time: str
    size_bytes: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "mime_type": self.mime_type,
            "parent_folder_id": self.parent_folder_id,
            "modified_time": self.modified_time,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DriveDocument":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            mime_type=data["mime_type"],
            parent_folder_id=data["parent_folder_id"],
            modified_time=data["modified_time"],
            size_bytes=data.get("size_bytes"),
        )


@dataclass
class FolderNode:
    """Represents a single folder in the Drive hierarchy.

    Attributes:
        id: Google Drive folder ID.
        name: Folder name.
        parent_id: ID of the parent folder (None for root).
        depth: Depth in the hierarchy (0 for root).
        children: List of child FolderNode objects.
        documents: List of documents in this folder.
    """

    id: str
    name: str
    parent_id: Optional[str]
    depth: int
    children: List["FolderNode"] = field(default_factory=list)
    documents: List[DriveDocument] = field(default_factory=list)
    _path_components: List[str] = field(default_factory=list, repr=False)

    @property
    def is_leaf(self) -> bool:
        """True if folder contains documents but no subfolders.

        A leaf folder is a processing target - it has documents to process
        but no further hierarchy to traverse.
        """
        return len(self.children) == 0 and len(self.documents) > 0

    @property
    def path(self) -> str:
        """Full path from root (for display).

        Returns:
            Path string like "House1/TeacherA/September Comments"
        """
        if self._path_components:
            return "/".join(self._path_components)
        return self.name

    def set_path_components(self, components: List[str]) -> None:
        """Set the path components for this folder.

        Args:
            components: List of folder names from root to this folder.
        """
        self._path_components = components.copy()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "path": self.path,
            "is_leaf": self.is_leaf,
            "children": [child.to_dict() for child in self.children],
            "documents": [doc.to_dict() for doc in self.documents],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FolderNode":
        """Create from dictionary."""
        node = cls(
            id=data["id"],
            name=data["name"],
            parent_id=data.get("parent_id"),
            depth=data["depth"],
            children=[cls.from_dict(c) for c in data.get("children", [])],
            documents=[DriveDocument.from_dict(d) for d in data.get("documents", [])],
        )
        # Reconstruct path from the stored path
        if "path" in data:
            node._path_components = data["path"].split("/")
        return node


@dataclass
class FolderMetadata:
    """Metadata extracted from folder path/names.

    This uses position-based extraction:
    - Depth 1: House name
    - Depth 2: Teacher name
    - Depth 3: Period/Sprint name

    Attributes:
        house: House name extracted from depth 1 folder.
        teacher: Teacher name extracted from depth 2 folder.
        period: Period/sprint name extracted from depth 3 folder.
        raw_path: Full path string for reference.
    """

    house: Optional[str] = None
    teacher: Optional[str] = None
    period: Optional[str] = None
    raw_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "house": self.house,
            "teacher": self.teacher,
            "period": self.period,
            "raw_path": self.raw_path,
        }


@dataclass
class FolderMap:
    """Complete folder structure discovered from root.

    This is the main data structure returned by FolderDiscovery. It contains
    the entire folder tree and provides methods for filtering and querying.

    Attributes:
        root: Root FolderNode of the discovered hierarchy.
        discovered_at: Timestamp when discovery was performed.
        total_folders: Total number of folders discovered.
        total_documents: Total number of documents discovered.
        leaf_folders: Pre-computed list of leaf folders.
    """

    root: FolderNode
    discovered_at: datetime
    total_folders: int
    total_documents: int
    leaf_folders: List[FolderNode] = field(default_factory=list)

    def get_leaf_folders(self) -> List[FolderNode]:
        """Return all leaf folders (processing targets).

        Leaf folders are folders that contain documents but no subfolders.
        These are the folders that contain documents to be processed.

        Returns:
            List of FolderNode objects that are leaf folders.
        """
        if self.leaf_folders:
            return self.leaf_folders

        # Compute leaf folders by traversing the tree
        leaves: List[FolderNode] = []
        self._collect_leaves(self.root, leaves)
        self.leaf_folders = leaves
        return leaves

    def _collect_leaves(self, node: FolderNode, leaves: List[FolderNode]) -> None:
        """Recursively collect leaf folders."""
        if node.is_leaf:
            leaves.append(node)
        for child in node.children:
            self._collect_leaves(child, leaves)

    def filter_by_pattern(self, pattern: str) -> List[FolderNode]:
        """Filter leaf folders by name pattern.

        Supports glob patterns: "September*", "*Interim*", etc.
        Matches against the full path, not just folder name.
        Case-insensitive matching.

        Args:
            pattern: Glob pattern to match against folder paths.

        Returns:
            List of matching leaf folders.
        """
        leaves = self.get_leaf_folders()
        return [
            folder for folder in leaves
            if match_folder_pattern(folder.path, pattern)
        ]

    def filter_by_patterns(self, patterns: List[str]) -> List[FolderNode]:
        """Filter by multiple patterns (OR logic).

        A folder is included if it matches ANY of the provided patterns.

        Args:
            patterns: List of glob patterns to match.

        Returns:
            List of matching leaf folders (deduplicated).
        """
        if not patterns:
            return self.get_leaf_folders()

        matched: Dict[str, FolderNode] = {}
        for pattern in patterns:
            for folder in self.filter_by_pattern(pattern):
                matched[folder.id] = folder

        return list(matched.values())

    def to_json(self, indent: int = 2) -> str:
        """Export map as JSON for debugging/auditing.

        Args:
            indent: JSON indentation level.

        Returns:
            JSON string representation of the folder map.
        """
        data = {
            "root": self.root.to_dict(),
            "discovered_at": self.discovered_at.isoformat(),
            "total_folders": self.total_folders,
            "total_documents": self.total_documents,
            "leaf_folder_count": len(self.get_leaf_folders()),
        }
        return json.dumps(data, indent=indent)

    def print_tree(self, console: Optional[Any] = None) -> None:
        """Print folder tree using rich console.

        Args:
            console: Rich Console instance. If None, prints to stdout.
        """
        if console is None:
            # Fall back to simple print
            self._print_tree_simple(self.root, 0)
        else:
            # Use rich Tree
            from rich.tree import Tree
            tree = Tree(f"[bold]{self.root.name}[/bold] ({self.root.id})")
            self._build_rich_tree(self.root, tree)
            console.print(tree)

    def _print_tree_simple(self, node: FolderNode, indent: int) -> None:
        """Print tree using simple text output."""
        prefix = "  " * indent
        leaf_marker = " [LEAF]" if node.is_leaf else ""
        doc_count = f" ({len(node.documents)} docs)" if node.documents else ""
        print(f"{prefix}{node.name}{leaf_marker}{doc_count}")

        for child in sorted(node.children, key=lambda x: x.name):
            self._print_tree_simple(child, indent + 1)

    def _build_rich_tree(self, node: FolderNode, tree: Any) -> None:
        """Build rich Tree recursively."""
        for child in sorted(node.children, key=lambda x: x.name):
            leaf_marker = " [green][LEAF][/green]" if child.is_leaf else ""
            doc_count = f" [dim]({len(child.documents)} docs)[/dim]" if child.documents else ""
            branch = tree.add(f"{child.name}{leaf_marker}{doc_count}")
            self._build_rich_tree(child, branch)


class FolderDiscovery:
    """Discovers and maps Google Drive folder structure.

    This class crawls a Google Drive folder hierarchy starting from a root
    folder ID and builds a FolderMap data structure containing all folders
    and documents.

    Example:
        discovery = FolderDiscovery(service)
        folder_map = discovery.discover_structure("1abc123xyz")

        # Get all leaf folders
        leaves = folder_map.get_leaf_folders()

        # Filter by pattern
        september = folder_map.filter_by_pattern("September*")
    """

    # MIME type for folders
    FOLDER_MIME = "application/vnd.google-apps.folder"

    # Document MIME types we're interested in
    DOCUMENT_MIMES = [
        "application/vnd.google-apps.document",  # Google Docs
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    ]

    def __init__(
        self,
        service: Any,
        rate_limiter: Optional[Any] = None,
    ) -> None:
        """Initialize folder discovery.

        Args:
            service: Authenticated Drive API service.
            rate_limiter: Optional rate limiter for API calls.
        """
        self._service = service
        self._rate_limiter = rate_limiter

    def discover_structure(
        self,
        root_folder_id: str,
        max_depth: int = 10,
        timeout_seconds: float = 120.0,
    ) -> FolderMap:
        """Discover complete folder structure from root.

        IMPORTANT: This runs fresh at every invocation.
        No caching between runs - structure may have changed.

        Args:
            root_folder_id: Google Drive folder ID to start from.
            max_depth: Maximum folder depth to traverse (safety limit).
            timeout_seconds: Maximum time for discovery operation.

        Returns:
            FolderMap containing complete structure.

        Raises:
            DriveAccessError: If root folder is not accessible.
            DiscoveryTimeoutError: If discovery exceeds timeout.
        """
        import time

        start_time = time.time()
        discovered_at = datetime.now()

        # Get root folder metadata
        root_metadata = self._get_folder_metadata(root_folder_id)
        if root_metadata is None:
            raise DriveAccessError(
                f"Cannot access folder with ID: {root_folder_id}. "
                "Ensure the folder is shared with your account.",
                resource_id=root_folder_id,
            )

        # Create root node
        root = FolderNode(
            id=root_folder_id,
            name=root_metadata.get("name", "Root"),
            parent_id=None,
            depth=0,
        )
        root.set_path_components([root.name])

        # Track totals
        total_folders = 1
        total_documents = 0
        leaf_folders: List[FolderNode] = []

        # BFS traversal to discover all folders and documents
        queue: List[FolderNode] = [root]

        while queue:
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                raise DiscoveryTimeoutError(
                    f"Discovery timed out after {elapsed:.1f} seconds. "
                    f"Discovered {total_folders} folders and {total_documents} documents.",
                    timeout_seconds=elapsed,
                )

            current = queue.pop(0)

            # Skip if we've hit max depth
            if current.depth >= max_depth:
                continue

            # Apply rate limiting if configured
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()

            # List contents of current folder
            children, documents = self._list_folder_contents(current.id)

            # Process child folders
            for child_data in children:
                child_node = FolderNode(
                    id=child_data["id"],
                    name=child_data["name"],
                    parent_id=current.id,
                    depth=current.depth + 1,
                )
                # Build path components
                child_node.set_path_components(current._path_components + [child_node.name])
                current.children.append(child_node)
                queue.append(child_node)
                total_folders += 1

            # Process documents
            for doc_data in documents:
                doc = DriveDocument(
                    id=doc_data["id"],
                    name=doc_data["name"],
                    mime_type=doc_data["mimeType"],
                    parent_folder_id=current.id,
                    modified_time=doc_data.get("modifiedTime", ""),
                    size_bytes=int(doc_data["size"]) if doc_data.get("size") else None,
                )
                current.documents.append(doc)
                total_documents += 1

            # Check if this is a leaf folder after processing
            if current.is_leaf:
                leaf_folders.append(current)

        return FolderMap(
            root=root,
            discovered_at=discovered_at,
            total_folders=total_folders,
            total_documents=total_documents,
            leaf_folders=leaf_folders,
        )

    def _get_folder_metadata(self, folder_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a folder.

        Args:
            folder_id: Google Drive folder ID.

        Returns:
            Folder metadata dict or None if not accessible.
        """
        try:
            result = (
                self._service.files()
                .get(fileId=folder_id, fields="id,name,mimeType")
                .execute()
            )
            return result
        except Exception:
            return None

    def _list_folder_contents(
        self, folder_id: str
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """List all folders and documents in a folder.

        Args:
            folder_id: Google Drive folder ID.

        Returns:
            Tuple of (child_folders, documents).
        """
        folders: List[Dict[str, Any]] = []
        documents: List[Dict[str, Any]] = []

        # Build query for files in this folder
        query = f"'{folder_id}' in parents and trashed = false"

        page_token: Optional[str] = None
        while True:
            # Apply rate limiting if configured
            if self._rate_limiter is not None and page_token is not None:
                self._rate_limiter.acquire()

            response = (
                self._service.files()
                .list(
                    q=query,
                    fields="nextPageToken,files(id,name,mimeType,modifiedTime,size)",
                    pageSize=100,
                    pageToken=page_token,
                )
                .execute()
            )

            for item in response.get("files", []):
                mime_type = item.get("mimeType", "")

                if mime_type == self.FOLDER_MIME:
                    folders.append(item)
                elif mime_type in self.DOCUMENT_MIMES:
                    documents.append(item)
                # Ignore other file types

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return folders, documents

    def extract_metadata(
        self,
        folder: FolderNode,
        folder_map: Optional[FolderMap] = None,
    ) -> FolderMetadata:
        """Extract house/teacher/period from folder path.

        Uses position in hierarchy:
        - Depth 1: House name
        - Depth 2: Teacher name
        - Depth 3: Period/Sprint name

        Args:
            folder: Target folder node.
            folder_map: Complete folder map for path traversal (optional).

        Returns:
            Extracted metadata.
        """
        path_components = folder._path_components or folder.path.split("/")

        metadata = FolderMetadata(raw_path=folder.path)

        # Position-based extraction (skip root at index 0)
        # Depth 1 (index 1) = House
        if len(path_components) > 1:
            metadata.house = path_components[1]

        # Depth 2 (index 2) = Teacher
        if len(path_components) > 2:
            metadata.teacher = path_components[2]

        # Depth 3 (index 3) = Period
        if len(path_components) > 3:
            metadata.period = path_components[3]

        return metadata


def match_folder_pattern(folder_path: str, pattern: str) -> bool:
    """Check if folder path matches pattern.

    Supports:
    - Glob patterns: "September*", "*Interim*"
    - Exact match: "Interim 1 Comments"
    - Case-insensitive matching

    The pattern is matched against each component of the path,
    so "September*" will match "Root/House1/Teacher/September Comments".

    Args:
        folder_path: Full path like "House1/TeacherA/September Comments"
        pattern: Pattern to match.

    Returns:
        True if pattern matches any component of path.
    """
    # Normalize for case-insensitive matching
    pattern_lower = pattern.lower()
    path_lower = folder_path.lower()

    # Check full path match first
    if fnmatch.fnmatch(path_lower, f"*{pattern_lower}*"):
        return True

    # Check each path component
    for component in folder_path.split("/"):
        if fnmatch.fnmatch(component.lower(), pattern_lower):
            return True

    return False
