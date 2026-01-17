"""Unit tests for Google Drive discovery module.

Tests folder discovery, pattern matching, metadata extraction, and JSON serialization.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from ferpa_feedback.gdrive.discovery import (
    DriveDocument,
    FolderDiscovery,
    FolderMap,
    FolderMetadata,
    FolderNode,
    match_folder_pattern,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def simple_folder_tree() -> FolderNode:
    """Create a simple 3-level folder tree for testing.

    Structure:
    Root/
    ├── House1/
    │   ├── TeacherA/
    │   │   └── September Comments/ (1 doc) [leaf]
    │   └── TeacherB/
    │       └── Interim 1 Comments/ (1 doc) [leaf]
    └── House2/
        └── TeacherC/
            └── September Comments/ (1 doc) [leaf]
    """
    # Create documents
    doc1 = DriveDocument(
        id="doc1",
        name="Comments.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        parent_folder_id="folder_sept1",
        modified_time="2026-01-15T10:00:00Z",
    )
    doc2 = DriveDocument(
        id="doc2",
        name="Comments.docx",
        mime_type="application/vnd.google-apps.document",
        parent_folder_id="folder_interim1",
        modified_time="2026-01-15T11:00:00Z",
    )
    doc3 = DriveDocument(
        id="doc3",
        name="Comments.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        parent_folder_id="folder_sept2",
        modified_time="2026-01-15T12:00:00Z",
    )

    # Create leaf folders (depth 3)
    folder_sept1 = FolderNode(
        id="folder_sept1",
        name="September Comments",
        parent_id="folder_teacher_a",
        depth=3,
        documents=[doc1],
    )
    folder_sept1.set_path_components(["Root", "House1", "TeacherA", "September Comments"])

    folder_interim1 = FolderNode(
        id="folder_interim1",
        name="Interim 1 Comments",
        parent_id="folder_teacher_b",
        depth=3,
        documents=[doc2],
    )
    folder_interim1.set_path_components(["Root", "House1", "TeacherB", "Interim 1 Comments"])

    folder_sept2 = FolderNode(
        id="folder_sept2",
        name="September Comments",
        parent_id="folder_teacher_c",
        depth=3,
        documents=[doc3],
    )
    folder_sept2.set_path_components(["Root", "House2", "TeacherC", "September Comments"])

    # Create teacher folders (depth 2)
    folder_teacher_a = FolderNode(
        id="folder_teacher_a",
        name="TeacherA",
        parent_id="folder_house1",
        depth=2,
        children=[folder_sept1],
    )
    folder_teacher_a.set_path_components(["Root", "House1", "TeacherA"])

    folder_teacher_b = FolderNode(
        id="folder_teacher_b",
        name="TeacherB",
        parent_id="folder_house1",
        depth=2,
        children=[folder_interim1],
    )
    folder_teacher_b.set_path_components(["Root", "House1", "TeacherB"])

    folder_teacher_c = FolderNode(
        id="folder_teacher_c",
        name="TeacherC",
        parent_id="folder_house2",
        depth=2,
        children=[folder_sept2],
    )
    folder_teacher_c.set_path_components(["Root", "House2", "TeacherC"])

    # Create house folders (depth 1)
    folder_house1 = FolderNode(
        id="folder_house1",
        name="House1",
        parent_id="root",
        depth=1,
        children=[folder_teacher_a, folder_teacher_b],
    )
    folder_house1.set_path_components(["Root", "House1"])

    folder_house2 = FolderNode(
        id="folder_house2",
        name="House2",
        parent_id="root",
        depth=1,
        children=[folder_teacher_c],
    )
    folder_house2.set_path_components(["Root", "House2"])

    # Create root (depth 0)
    root = FolderNode(
        id="root",
        name="Root",
        parent_id=None,
        depth=0,
        children=[folder_house1, folder_house2],
    )
    root.set_path_components(["Root"])

    return root


@pytest.fixture
def folder_map(simple_folder_tree: FolderNode) -> FolderMap:
    """Create a FolderMap from the simple tree."""
    return FolderMap(
        root=simple_folder_tree,
        discovered_at=datetime(2026, 1, 17, 10, 0, 0),
        total_folders=7,
        total_documents=3,
    )


# -----------------------------------------------------------------------------
# Test FolderNode
# -----------------------------------------------------------------------------


class TestFolderNode:
    """Tests for FolderNode dataclass."""

    def test_is_leaf_true_when_has_docs_no_children(self, simple_folder_tree: FolderNode) -> None:
        """Leaf folder has documents but no subfolders."""
        # Get a leaf folder (September Comments under TeacherA)
        leaf = simple_folder_tree.children[0].children[0].children[0]

        assert leaf.name == "September Comments"
        assert leaf.is_leaf is True
        assert len(leaf.documents) == 1
        assert len(leaf.children) == 0

    def test_is_leaf_false_when_has_children(self, simple_folder_tree: FolderNode) -> None:
        """Non-leaf folder has children."""
        # Root has children
        assert simple_folder_tree.is_leaf is False

        # House1 has children
        house1 = simple_folder_tree.children[0]
        assert house1.is_leaf is False

    def test_is_leaf_false_when_empty(self) -> None:
        """Empty folder (no docs, no children) is not a leaf."""
        empty_folder = FolderNode(
            id="empty",
            name="Empty",
            parent_id="root",
            depth=1,
        )
        assert empty_folder.is_leaf is False

    def test_path_property(self, simple_folder_tree: FolderNode) -> None:
        """Path returns full path from root."""
        leaf = simple_folder_tree.children[0].children[0].children[0]
        assert leaf.path == "Root/House1/TeacherA/September Comments"

    def test_to_dict_serialization(self, simple_folder_tree: FolderNode) -> None:
        """Test serialization to dictionary."""
        leaf = simple_folder_tree.children[0].children[0].children[0]
        data = leaf.to_dict()

        assert data["id"] == "folder_sept1"
        assert data["name"] == "September Comments"
        assert data["depth"] == 3
        assert data["is_leaf"] is True
        assert len(data["documents"]) == 1

    def test_from_dict_deserialization(self) -> None:
        """Test deserialization from dictionary."""
        data = {
            "id": "test_folder",
            "name": "Test Folder",
            "parent_id": "parent",
            "depth": 2,
            "path": "Root/Parent/Test Folder",
            "is_leaf": True,
            "children": [],
            "documents": [
                {
                    "id": "doc1",
                    "name": "Test.docx",
                    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "parent_folder_id": "test_folder",
                    "modified_time": "2026-01-15T10:00:00Z",
                    "size_bytes": 1024,
                }
            ],
        }

        node = FolderNode.from_dict(data)

        assert node.id == "test_folder"
        assert node.name == "Test Folder"
        assert node.depth == 2
        assert len(node.documents) == 1
        assert node.documents[0].name == "Test.docx"


# -----------------------------------------------------------------------------
# Test FolderMap
# -----------------------------------------------------------------------------


class TestFolderMap:
    """Tests for FolderMap dataclass."""

    def test_get_leaf_folders_returns_correct_count(self, folder_map: FolderMap) -> None:
        """get_leaf_folders returns all leaf folders."""
        leaves = folder_map.get_leaf_folders()

        assert len(leaves) == 3
        leaf_names = {leaf.name for leaf in leaves}
        assert "September Comments" in leaf_names
        assert "Interim 1 Comments" in leaf_names

    def test_get_leaf_folders_identifies_correct_folders(self, folder_map: FolderMap) -> None:
        """Leaf folders have documents but no children."""
        leaves = folder_map.get_leaf_folders()

        for leaf in leaves:
            assert leaf.is_leaf is True
            assert len(leaf.documents) > 0
            assert len(leaf.children) == 0

    def test_filter_by_pattern_glob_matches_september(self, folder_map: FolderMap) -> None:
        """Pattern 'September*' matches September folders."""
        matches = folder_map.filter_by_pattern("September*")

        assert len(matches) == 2
        for match in matches:
            assert "September" in match.name

    def test_filter_by_pattern_glob_matches_interim(self, folder_map: FolderMap) -> None:
        """Pattern 'Interim*' matches Interim folders."""
        matches = folder_map.filter_by_pattern("Interim*")

        assert len(matches) == 1
        assert matches[0].name == "Interim 1 Comments"

    def test_filter_by_pattern_case_insensitive(self, folder_map: FolderMap) -> None:
        """Pattern matching is case-insensitive."""
        matches_lower = folder_map.filter_by_pattern("september*")
        matches_upper = folder_map.filter_by_pattern("SEPTEMBER*")

        assert len(matches_lower) == 2
        assert len(matches_upper) == 2

    def test_filter_by_pattern_no_matches(self, folder_map: FolderMap) -> None:
        """Pattern with no matches returns empty list."""
        matches = folder_map.filter_by_pattern("NonExistent*")

        assert len(matches) == 0

    def test_filter_by_patterns_multiple_or_logic(self, folder_map: FolderMap) -> None:
        """Multiple patterns use OR logic."""
        matches = folder_map.filter_by_patterns(["September*", "Interim*"])

        # Should get September (2) + Interim (1) = 3 unique
        assert len(matches) == 3

    def test_filter_by_patterns_empty_returns_all(self, folder_map: FolderMap) -> None:
        """Empty patterns list returns all leaf folders."""
        matches = folder_map.filter_by_patterns([])

        assert len(matches) == 3

    def test_filter_by_patterns_deduplicates(self, folder_map: FolderMap) -> None:
        """Overlapping patterns don't duplicate results."""
        matches = folder_map.filter_by_patterns(["September*", "*Comments"])

        # All 3 folders match "*Comments", but should be deduplicated
        folder_ids = [f.id for f in matches]
        assert len(folder_ids) == len(set(folder_ids))

    def test_to_json_serialization(self, folder_map: FolderMap) -> None:
        """to_json produces valid JSON."""
        json_str = folder_map.to_json()

        # Should be valid JSON
        data = json.loads(json_str)

        assert "root" in data
        assert "discovered_at" in data
        assert data["total_folders"] == 7
        assert data["total_documents"] == 3
        assert data["leaf_folder_count"] == 3

    def test_to_json_roundtrip(self, folder_map: FolderMap) -> None:
        """JSON serialization can be deserialized."""
        json_str = folder_map.to_json()
        data = json.loads(json_str)

        # Reconstruct root from data
        root = FolderNode.from_dict(data["root"])

        assert root.name == "Root"
        assert len(root.children) == 2


# -----------------------------------------------------------------------------
# Test match_folder_pattern
# -----------------------------------------------------------------------------


class TestMatchFolderPattern:
    """Tests for match_folder_pattern function."""

    def test_exact_match(self) -> None:
        """Exact name match works."""
        assert match_folder_pattern("Root/House1/September Comments", "September Comments") is True

    def test_glob_asterisk_suffix(self) -> None:
        """Glob pattern with asterisk suffix."""
        assert match_folder_pattern("Root/House1/September Comments", "September*") is True
        assert match_folder_pattern("Root/House1/Interim 1", "September*") is False

    def test_glob_asterisk_prefix(self) -> None:
        """Glob pattern with asterisk prefix."""
        assert match_folder_pattern("Root/House1/September Comments", "*Comments") is True
        assert match_folder_pattern("Root/House1/September Notes", "*Comments") is False

    def test_glob_asterisk_both(self) -> None:
        """Glob pattern with asterisks on both sides."""
        assert match_folder_pattern("Root/House1/September Comments", "*ember*") is True
        assert match_folder_pattern("Root/House1/Interim", "*ember*") is False

    def test_case_insensitive(self) -> None:
        """Matching is case-insensitive."""
        assert match_folder_pattern("Root/House1/September Comments", "september*") is True
        assert match_folder_pattern("Root/House1/September Comments", "SEPTEMBER*") is True
        assert match_folder_pattern("Root/House1/september comments", "September*") is True

    def test_matches_any_path_component(self) -> None:
        """Pattern can match any component in path."""
        path = "Root/House1/TeacherA/September Comments"

        assert match_folder_pattern(path, "Root") is True
        assert match_folder_pattern(path, "House1") is True
        assert match_folder_pattern(path, "TeacherA") is True
        assert match_folder_pattern(path, "September*") is True

    def test_no_match(self) -> None:
        """Non-matching pattern returns False."""
        assert match_folder_pattern("Root/House1/September", "October*") is False


# -----------------------------------------------------------------------------
# Test FolderMetadata extraction
# -----------------------------------------------------------------------------


class TestExtractMetadata:
    """Tests for FolderDiscovery.extract_metadata method."""

    def test_extract_metadata_full_path(self) -> None:
        """Extract metadata from full 4-level path."""
        # Create a mock service
        mock_service = MagicMock()
        discovery = FolderDiscovery(mock_service)

        # Create folder with path
        folder = FolderNode(
            id="test",
            name="September Comments",
            parent_id="teacher",
            depth=3,
        )
        folder.set_path_components(["Root", "House1", "TeacherA", "September Comments"])

        metadata = discovery.extract_metadata(folder)

        assert metadata.house == "House1"
        assert metadata.teacher == "TeacherA"
        assert metadata.period == "September Comments"
        assert metadata.raw_path == "Root/House1/TeacherA/September Comments"

    def test_extract_metadata_partial_path(self) -> None:
        """Extract metadata from partial path (depth 2)."""
        mock_service = MagicMock()
        discovery = FolderDiscovery(mock_service)

        folder = FolderNode(
            id="test",
            name="TeacherA",
            parent_id="house",
            depth=2,
        )
        folder.set_path_components(["Root", "House1", "TeacherA"])

        metadata = discovery.extract_metadata(folder)

        assert metadata.house == "House1"
        assert metadata.teacher == "TeacherA"
        assert metadata.period is None

    def test_extract_metadata_shallow_path(self) -> None:
        """Extract metadata from shallow path (depth 1)."""
        mock_service = MagicMock()
        discovery = FolderDiscovery(mock_service)

        folder = FolderNode(
            id="test",
            name="House1",
            parent_id="root",
            depth=1,
        )
        folder.set_path_components(["Root", "House1"])

        metadata = discovery.extract_metadata(folder)

        assert metadata.house == "House1"
        assert metadata.teacher is None
        assert metadata.period is None


# -----------------------------------------------------------------------------
# Test DriveDocument
# -----------------------------------------------------------------------------


class TestDriveDocument:
    """Tests for DriveDocument dataclass."""

    def test_to_dict(self) -> None:
        """Test document serialization."""
        doc = DriveDocument(
            id="doc123",
            name="Test.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            parent_folder_id="folder123",
            modified_time="2026-01-15T10:00:00Z",
            size_bytes=1024,
        )

        data = doc.to_dict()

        assert data["id"] == "doc123"
        assert data["name"] == "Test.docx"
        assert data["size_bytes"] == 1024

    def test_from_dict(self) -> None:
        """Test document deserialization."""
        data = {
            "id": "doc456",
            "name": "Another.docx",
            "mime_type": "application/vnd.google-apps.document",
            "parent_folder_id": "folder456",
            "modified_time": "2026-01-16T12:00:00Z",
            "size_bytes": None,
        }

        doc = DriveDocument.from_dict(data)

        assert doc.id == "doc456"
        assert doc.name == "Another.docx"
        assert doc.size_bytes is None


# -----------------------------------------------------------------------------
# Test FolderDiscovery with mocked API
# -----------------------------------------------------------------------------


class TestFolderDiscoveryWithMockedAPI:
    """Tests for FolderDiscovery with mocked Google API."""

    def test_discover_structure_simple_hierarchy(self) -> None:
        """Test discovering a simple folder hierarchy."""
        # Create mock service
        mock_service = MagicMock()

        # Mock the files().get() call for root folder
        mock_service.files().get().execute.return_value = {
            "id": "root123",
            "name": "Root Folder",
            "mimeType": "application/vnd.google-apps.folder",
        }

        # Mock the files().list() call for children
        # First call: root's children (one house folder)
        # Second call: house's children (one teacher folder)
        # Third call: teacher's children (one period folder with docs)
        # Fourth call: period folder has no subfolders
        mock_service.files().list().execute.side_effect = [
            # Root children (1 house)
            {
                "files": [
                    {
                        "id": "house1",
                        "name": "House1",
                        "mimeType": "application/vnd.google-apps.folder",
                    }
                ],
                "nextPageToken": None,
            },
            # House children (1 teacher)
            {
                "files": [
                    {
                        "id": "teacher1",
                        "name": "TeacherA",
                        "mimeType": "application/vnd.google-apps.folder",
                    }
                ],
                "nextPageToken": None,
            },
            # Teacher children (1 period folder + 1 doc)
            {
                "files": [
                    {
                        "id": "period1",
                        "name": "September Comments",
                        "mimeType": "application/vnd.google-apps.folder",
                    },
                    {
                        "id": "doc1",
                        "name": "Comments.docx",
                        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "modifiedTime": "2026-01-15T10:00:00Z",
                    },
                ],
                "nextPageToken": None,
            },
            # Period folder children (just docs)
            {
                "files": [
                    {
                        "id": "doc2",
                        "name": "Comments.docx",
                        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "modifiedTime": "2026-01-15T10:00:00Z",
                    },
                ],
                "nextPageToken": None,
            },
        ]

        discovery = FolderDiscovery(mock_service)
        folder_map = discovery.discover_structure("root123")

        assert folder_map.root.name == "Root Folder"
        assert folder_map.total_folders >= 1
        assert folder_map.total_documents >= 1
