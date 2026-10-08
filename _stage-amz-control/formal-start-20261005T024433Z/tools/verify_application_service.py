#!/usr/bin/env python
"""Offline contract checks for the Product V1 Application Service."""
from __future__ import annotations

import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from src.application_service import ApplicationService, ImageUpload  # noqa: E402
from src.workspace_store import WorkspaceStore  # noqa: E402


def png_bytes(color: tuple[int, int, int] = (40, 90, 140)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (12, 8), color).save(output, format="PNG")
    return output.getvalue()


class ApplicationServiceChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="amz-application-service-")
        self.parent = Path(self.temp.name)
        self.root = self.parent / "workspace"
        self.service = ApplicationService()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_create_returns_an_empty_intake_projection(self) -> None:
        response = self.service.create_workspace(self.root)

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.ok)
        self.assertIsNone(response.body["error"])
        data = response.body["data"]
        self.assertEqual(data["workspace"]["status"], "NEW")
        self.assertEqual(data["intake"]["product_name"], "")
        self.assertEqual(data["intake"]["reference_images"], [])
        self.assertEqual(data["readiness"]["state"], "EMPTY")
        self.assertEqual(data["readiness"]["missing_required"], ["product_name", "reference_images"])
        self.assertFalse(data["readiness"]["can_save_intake"])
        self.assertIsNone(data["product_brief"])
        self.assertIsNone(data["plan"])
        self.assertFalse(data["readiness"]["can_generate_product_brief"])
        self.assertFalse(data["readiness"]["can_generate_plan"])
        self.assertFalse(data["readiness"]["can_generate_prompts"])
        self.assertNotIn("generation", data)
        self.assertNotIn("candidates", data)
        self.assertTrue((self.root / "workspace.json").is_file())

    def test_missing_material_is_actionable_and_writes_nothing(self) -> None:
        created = self.service.create_workspace(self.root)
        original_index = (self.root / "workspace.json").read_bytes()
        etag = created.body["data"]["workspace"]["revision"]

        both_missing = self.service.save_intake(
            self.root, expected_etag=etag, product_name="", reference_images=None
        )
        self.assertEqual(both_missing.status_code, 422)
        self.assertEqual(both_missing.body["error"]["code"], "INTAKE_REQUIRED")
        self.assertEqual(both_missing.body["error"]["field"], "product_name")
        self.assertEqual(
            both_missing.body["error"]["details"]["missing_fields"],
            ["product_name", "reference_images"],
        )
        self.assertEqual(both_missing.body["error"]["next_action"], "add_missing_material")

        reference_missing = self.service.save_intake(
            self.root, expected_etag=etag, product_name="Lantern", reference_images=None
        )
        self.assertEqual(set(reference_missing.body), {"ok", "data", "error"})
        self.assertEqual(
            set(reference_missing.body["error"]),
            {"code", "message", "field", "recoverable", "next_action", "details"},
        )
        self.assertEqual(reference_missing.body["error"]["field"], "reference_images")
        self.assertEqual((self.root / "workspace.json").read_bytes(), original_index)
        self.assertEqual(WorkspaceStore.open(self.root).list_records("product_input"), [])
        self.assertFalse((self.root / "inputs").exists())

    def test_bad_directory_returns_stable_error_without_touching_file(self) -> None:
        path_is_file = self.parent / "not-a-folder.txt"
        path_is_file.write_text("keep", encoding="utf-8")

        file_result = self.service.create_workspace(path_is_file)
        self.assertEqual(file_result.status_code, 422)
        self.assertEqual(file_result.body["error"]["code"], "DIRECTORY_NOT_FOLDER")
        self.assertEqual(file_result.body["error"]["field"], "directory")
        self.assertEqual(path_is_file.read_text(encoding="utf-8"), "keep")

        missing_parent = self.parent / "missing" / "workspace"
        parent_result = self.service.create_workspace(missing_parent)
        self.assertEqual(parent_result.status_code, 422)
        self.assertEqual(parent_result.body["error"]["code"], "WORKSPACE_PATH_UNAVAILABLE")
        self.assertFalse(missing_parent.parent.exists())

    def test_invalid_image_is_rejected_before_any_intake_file_is_written(self) -> None:
        created = self.service.create_workspace(self.root)
        original_index = (self.root / "workspace.json").read_bytes()
        response = self.service.save_intake(
            self.root,
            expected_etag=created.body["data"]["workspace"]["revision"],
            product_name="Lantern",
            reference_images=[ImageUpload("broken.png", b"not an image", "primary")],
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.body["error"]["code"], "REFERENCE_IMAGE_INVALID")
        self.assertEqual(response.body["error"]["field"], "reference_images[0]")
        self.assertEqual((self.root / "workspace.json").read_bytes(), original_index)
        self.assertEqual(WorkspaceStore.open(self.root).list_records("product_input"), [])
        self.assertFalse((self.root / "inputs").exists())

    def test_saved_intake_is_versioned_and_recovers_after_reopen(self) -> None:
        created = self.service.create_workspace(self.root)
        image = png_bytes()
        first = self.service.save_intake(
            self.root,
            expected_etag=created.body["data"]["workspace"]["revision"],
            product_name="Foldable travel lantern",
            description="Compact rechargeable light for camping.",
            selling_points=["Rechargeable battery", "Folds flat"],
            user_intent="Show portability and warm light outdoors.",
            reference_images=[
                ImageUpload(r"C:\fakepath\listing\lantern-front.png", image, "primary")
            ],
        )

        self.assertTrue(first.ok, first.body["error"])
        first_data = first.body["data"]
        self.assertEqual(first_data["workspace"]["status"], "INTAKE_READY")
        self.assertTrue(first_data["readiness"]["can_save_intake"])
        self.assertEqual(first_data["intake"]["selling_points"][0]["source"], "user")
        self.assertEqual(first_data["intake"]["reference_images"][0]["name"], "lantern-front.png")
        first_digest = hashlib.sha256(image).hexdigest()
        self.assertEqual(first_data["intake"]["reference_images"][0]["sha256"], first_digest)

        repeated = self.service.save_intake(
            self.root,
            expected_etag=first_data["workspace"]["revision"],
            product_name="Foldable travel lantern",
            description="Compact rechargeable light for camping.",
            selling_points=["Rechargeable battery", "Folds flat"],
            user_intent="Show portability and warm light outdoors.",
            reference_images=None,
        )
        self.assertTrue(repeated.ok, repeated.body["error"])
        self.assertEqual(repeated.body["data"]["workspace"]["revision"], first_data["workspace"]["revision"])
        self.assertEqual(len(WorkspaceStore.open(self.root).list_records("product_input")), 1)

        workspace_store = WorkspaceStore.open(self.root)
        first_input = workspace_store.list_records("product_input")[0]
        first_input_path = self.root / "inputs" / "product-input-v001.json"
        original_record_bytes = first_input_path.read_bytes()
        relative_asset = workspace_store.load_workspace().workspace["assets"][0]["relative_path"]
        asset_path = self.root / Path(relative_asset)
        self.assertEqual(asset_path.read_bytes(), image)

        second = self.service.save_intake(
            self.root,
            expected_etag=first_data["workspace"]["revision"],
            product_name="Foldable travel lantern — revised",
            description="Same source photo; revised product description.",
            selling_points=["Rechargeable battery", "Folds flat"],
            user_intent="Emphasize packability.",
            reference_images=None,
        )
        self.assertTrue(second.ok, second.body["error"])
        self.assertEqual([item["version"] for item in WorkspaceStore.open(self.root).list_records("product_input")], [1, 2])
        self.assertEqual(first_input_path.read_bytes(), original_record_bytes)
        self.assertEqual(WorkspaceStore.open(self.root).list_records("product_input")[0], first_input)

        reopened = self.service.open_workspace(self.root)
        self.assertTrue(reopened.ok, reopened.body["error"])
        reopened_data = reopened.body["data"]
        self.assertEqual(reopened_data["intake"]["product_name"], "Foldable travel lantern — revised")
        self.assertEqual(reopened_data["intake"]["reference_images"][0]["sha256"], first_digest)
        self.assertEqual(reopened_data["intake"]["selling_points"][1]["text"], "Folds flat")
        self.assertEqual(reopened_data["workspace"]["status"], "INTAKE_READY")

    def test_stale_revision_does_not_create_an_orphan_asset_or_record(self) -> None:
        created = self.service.create_workspace(self.root)
        initial_etag = created.body["data"]["workspace"]["revision"]
        first_image = png_bytes((10, 20, 30))
        saved = self.service.save_intake(
            self.root,
            expected_etag=initial_etag,
            product_name="Sample product",
            reference_images=[ImageUpload("first.png", first_image, "primary")],
        )
        second_image = png_bytes((200, 180, 160))

        stale = self.service.save_intake(
            self.root,
            expected_etag=initial_etag,
            product_name="Stale overwrite",
            reference_images=[ImageUpload("second.png", second_image, "detail")],
        )

        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.body["error"]["code"], "REVISION_CONFLICT")
        store = WorkspaceStore.open(self.root)
        self.assertEqual(len(store.list_records("product_input")), 1)
        self.assertEqual(len(store.load_workspace().workspace["assets"]), 1)
        self.assertEqual(
            store.load_workspace().workspace["current"]["product_input"]["version"], 1
        )
        self.assertFalse((self.root / "inputs" / "originals" / f"{hashlib.sha256(second_image).hexdigest()}.png").exists())
        self.assertTrue(saved.ok)

    def test_ordered_references_support_reorder_insert_and_rejection(self) -> None:
        created = self.service.create_workspace(self.root)
        first_image = png_bytes((10, 20, 30))
        second_image = png_bytes((200, 180, 160))
        third_image = png_bytes((60, 160, 90))
        sha_first = hashlib.sha256(first_image).hexdigest()
        sha_second = hashlib.sha256(second_image).hexdigest()
        sha_third = hashlib.sha256(third_image).hexdigest()

        saved = self.service.save_intake(
            self.root,
            expected_etag=created.body["data"]["workspace"]["revision"],
            product_name="Ordered lantern",
            reference_images=[
                ImageUpload("front.png", first_image, "primary"),
                ImageUpload("back.png", second_image, "detail"),
            ],
            reference_order=["upload:1", "upload:0"],
        )
        self.assertTrue(saved.ok, saved.body["error"])
        first_data = saved.body["data"]
        self.assertEqual(
            [item["sha256"] for item in first_data["intake"]["reference_images"]],
            [sha_second, sha_first],
        )

        reordered = self.service.save_intake(
            self.root,
            expected_etag=first_data["workspace"]["revision"],
            product_name="Ordered lantern",
            reference_images=None,
            reference_order=["sha256:" + sha_first, "sha256:" + sha_second],
        )
        self.assertTrue(reordered.ok, reordered.body["error"])
        second_data = reordered.body["data"]
        self.assertEqual(
            [item["sha256"] for item in second_data["intake"]["reference_images"]],
            [sha_first, sha_second],
        )

        inserted = self.service.save_intake(
            self.root,
            expected_etag=second_data["workspace"]["revision"],
            product_name="Ordered lantern",
            reference_images=[ImageUpload("side.png", third_image, "detail")],
            reference_order=["sha256:" + sha_second, "upload:0", "sha256:" + sha_first],
        )
        self.assertTrue(inserted.ok, inserted.body["error"])
        third_data = inserted.body["data"]
        self.assertEqual(
            [item["sha256"] for item in third_data["intake"]["reference_images"]],
            [sha_second, sha_third, sha_first],
        )

        for order, code, field in (
            (["sha256:" + "0" * 64], "REFERENCE_ORDER_INVALID", "reference_order"),
            ([], "REFERENCE_IMAGE_COUNT", "reference_images"),
        ):
            rejected = self.service.save_intake(
                self.root,
                expected_etag=third_data["workspace"]["revision"],
                product_name="Ordered lantern",
                reference_images=None,
                reference_order=order,
            )
            self.assertEqual(rejected.status_code, 422, rejected.body)
            self.assertEqual(rejected.body["error"]["code"], code)
            self.assertEqual(rejected.body["error"]["field"], field)
            after = self.service.open_workspace(self.root).body["data"]
            self.assertEqual(
                [item["sha256"] for item in after["intake"]["reference_images"]],
                [sha_second, sha_third, sha_first],
            )

    def test_missing_revision_is_a_contract_error(self) -> None:
        self.service.create_workspace(self.root)
        response = self.service.save_intake(
            self.root, expected_etag=None, product_name="Sample", reference_images=None
        )

        self.assertEqual(response.status_code, 428)
        self.assertEqual(response.body["error"]["code"], "REVISION_REQUIRED")
        self.assertEqual(response.body["error"]["field"], "revision")


if __name__ == "__main__":
    unittest.main(verbosity=2)
