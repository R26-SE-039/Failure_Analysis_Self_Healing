import unittest
from pathlib import Path

from workspace_manager import WorkspaceError, WorkspaceManager


class WorkspaceManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = WorkspaceManager(
            Path(__file__).parents[1] / "workspaces"
        )

    def test_workspace_path_is_derived_from_repository(self):
        path = self.manager.workspace_path_for("example/project")

        self.assertEqual(path.name, "example__project")
        self.assertEqual(path.parent, self.manager.workspace_root)

    def test_rejects_repository_path_traversal(self):
        with self.assertRaises(WorkspaceError):
            self.manager.workspace_path_for("../outside")

    def test_rejects_clone_url_for_different_repository(self):
        with self.assertRaisesRegex(
            WorkspaceError,
            "unexpected clone URL",
        ):
            self.manager.prepare(
                {
                    "repository_full_name": "example/project",
                    "repository_clone_url": (
                        "https://github.com/attacker/project.git"
                    ),
                    "head_sha": "a" * 40,
                    "head_branch": "main",
                },
                index_with_serena=False,
            )


if __name__ == "__main__":
    unittest.main()
