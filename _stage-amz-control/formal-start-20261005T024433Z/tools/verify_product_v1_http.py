#!/usr/bin/env python
"""Standard-library HTTP integration checks for the Product V1 local server."""
from __future__ import annotations

import hashlib
import http.client
import json
import sys
import tempfile
import threading
import unittest
import uuid
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from struct import pack
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.product_v1_server import ProductApplication, create_product_server  # noqa: E402


def png_bytes(rgb: tuple[int, int, int] = (72, 118, 164)) -> bytes:
    """Build a tiny valid RGBA PNG using only the Python standard library."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return pack(">I", len(data)) + kind + data + pack(">I", crc)

    ihdr = pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0)
    scanline = b"\x00" + bytes((*rgb, 255)) * 2
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(scanline * 2)) + chunk(b"IEND", b""))


def multipart_body(fields: dict[str, str], files: list[tuple[str, str, str, bytes]]):
    boundary = "----amz-listing-kit-" + uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("ascii"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"))
        body.extend(value.encode("utf-8") + b"\r\n")
    for name, filename, media_type, content in files:
        body.extend(f"--{boundary}\r\n".encode("ascii"))
        body.extend(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("ascii"))
        body.extend(f"Content-Type: {media_type}\r\n\r\n".encode("ascii"))
        body.extend(content + b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("ascii"))
    return bytes(body), f"multipart/form-data; boundary={boundary}"


class ProductV1HTTPChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory(prefix="amz-product-v1-http-")
        cls.root = Path(cls._temporary.name)
        application = ProductApplication(
            recent_index_path=cls.root / "recent-workspaces.json",
            folder_picker=lambda _purpose: None,
        )
        cls.server = create_product_server(port=0, application=application)
        cls.port = cls.server.server_address[1]
        cls.origin = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls._temporary.cleanup()

    def request(self, method: str, path: str, *, body: bytes | None = None,
                content_type: str | None = None):
        headers = {"Origin": self.origin}
        if content_type:
            headers["Content-Type"] = content_type
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            return response.status, {key.lower(): value for key, value in response.getheaders()}, payload
        finally:
            connection.close()

    def json_request(self, method: str, path: str, value: dict[str, object]):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        return self.request(method, path, body=body, content_type="application/json")

    @staticmethod
    def json_payload(payload: bytes) -> dict[str, object]:
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict):
            raise AssertionError("HTTP JSON body must be an object")
        return value

    def create_workspace(self, name: str):
        directory = self.root / name
        status, _, payload = self.json_request(
            "POST", "/api/workspaces", {"directory": str(directory)}
        )
        envelope = self.json_payload(payload)
        self.assertEqual(status, 201, envelope)
        self.assertTrue(envelope["ok"], envelope)
        self.assertIsNone(envelope["error"], envelope)
        return directory, envelope["data"]

    def intake_request(self, directory: Path, revision: str, *,
                       product_name: str = "Adjustable Reading Lamp",
                       description: str = "A compact desk lamp for focused reading.",
                       selling_points: str = "Adjustable lamp head\nStable weighted base",
                       user_intent: str = "Show the product clearly for Amazon US.",
                       image: bytes | None = None, filename: str = "reference.png",
                       images: list[tuple[str, bytes]] | None = None,
                       reference_order: list[str] | None = None):
        if images is None:
            content = png_bytes() if image is None else image
            images = [(filename, content)]
        fields = {
            "directory": str(directory), "expected_etag": revision,
            "product_name": product_name, "description": description,
            "selling_points": selling_points, "user_intent": user_intent,
        }
        if reference_order is not None:
            fields["reference_order"] = json.dumps(reference_order)
        return multipart_body(
            fields,
            [("reference_images", name, "image/png", content) for name, content in images],
        )

    def save_intake(self, directory: Path, revision: str, **kwargs):
        body, content_type = self.intake_request(directory, revision, **kwargs)
        return self.request("PUT", "/api/intake", body=body, content_type=content_type)

    def workspace_projection(self, directory: Path):
        path = "/api/workspace?directory=" + quote(str(directory), safe="")
        status, _, payload = self.request("GET", path)
        envelope = self.json_payload(payload)
        self.assertEqual(status, 200, envelope)
        self.assertTrue(envelope["ok"], envelope)
        return envelope["data"]

    def test_create_empty_workspace_and_list_recent(self) -> None:
        directory, data = self.create_workspace("empty-workspace")
        self.assertEqual(data["workspace"]["status"], "NEW")
        self.assertEqual(data["intake"]["product_name"], "")
        self.assertEqual(data["intake"]["reference_images"], [])
        self.assertEqual(data["readiness"]["state"], "EMPTY")
        self.assertFalse(data["readiness"]["can_save_intake"])

        status, _, payload = self.request("GET", "/api/workspaces/recent")
        envelope = self.json_payload(payload)
        self.assertEqual(status, 200, envelope)
        self.assertTrue(envelope["ok"], envelope)
        items = envelope["data"]["workspaces"]
        self.assertTrue(any(item["workspace_id"] == data["workspace"]["id"] for item in items))
        self.assertTrue(any(Path(item["directory"]) == directory for item in items))

    def test_multipart_save_reopen_and_reference_preview(self) -> None:
        directory, created = self.create_workspace("save-and-reopen")
        content = png_bytes()
        status, _, payload = self.save_intake(
            directory, created["workspace"]["revision"], image=content
        )
        saved_envelope = self.json_payload(payload)
        self.assertEqual(status, 200, saved_envelope)
        self.assertTrue(saved_envelope["ok"], saved_envelope)
        saved = saved_envelope["data"]
        self.assertEqual(saved["intake"]["product_name"], "Adjustable Reading Lamp")
        self.assertEqual(saved["intake"]["description"], "A compact desk lamp for focused reading.")
        self.assertEqual(
            [item["text"] for item in saved["intake"]["selling_points"]],
            ["Adjustable lamp head", "Stable weighted base"],
        )
        self.assertEqual(saved["intake"]["user_intent"], "Show the product clearly for Amazon US.")
        self.assertEqual(len(saved["intake"]["reference_images"]), 1)
        reference = saved["intake"]["reference_images"][0]
        digest = hashlib.sha256(content).hexdigest()
        self.assertEqual(reference["sha256"], digest)
        self.assertEqual(reference["media_type"], "image/png")

        status, _, payload = self.json_request(
            "POST", "/api/workspaces/open", {"directory": str(directory)}
        )
        reopened_envelope = self.json_payload(payload)
        self.assertEqual(status, 200, reopened_envelope)
        self.assertTrue(reopened_envelope["ok"], reopened_envelope)
        reopened = self.workspace_projection(directory)
        self.assertEqual(reopened["workspace"]["id"], created["workspace"]["id"])
        self.assertEqual(reopened["intake"], saved["intake"])
        self.assertEqual(reopened["workspace"]["revision"], saved["workspace"]["revision"])

        preview_path = (
            "/api/workspace/references/" + digest
            + "?directory=" + quote(str(directory), safe="")
        )
        status, headers, preview = self.request("GET", preview_path)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("content-type"), "image/png")
        self.assertEqual(preview, content)

    def test_bad_image_is_rejected_without_workspace_mutation(self) -> None:
        directory, created = self.create_workspace("bad-image")
        revision = created["workspace"]["revision"]
        status, _, payload = self.save_intake(
            directory, revision, image=b"this is not an image", filename="broken.png"
        )
        envelope = self.json_payload(payload)
        self.assertEqual(status, 422, envelope)
        self.assertFalse(envelope["ok"], envelope)
        self.assertEqual(envelope["error"]["code"], "REFERENCE_IMAGE_INVALID")
        self.assertEqual(set(envelope), {"ok", "data", "error"})

        after = self.workspace_projection(directory)
        self.assertEqual(after["workspace"]["revision"], revision)
        self.assertEqual(after["workspace"]["status"], "NEW")
        self.assertEqual(after["intake"]["product_name"], "")
        self.assertEqual(after["intake"]["reference_images"], [])

    def test_competing_saves_reject_the_stale_revision(self) -> None:
        directory, created = self.create_workspace("concurrent-saves")
        revision = created["workspace"]["revision"]
        attempts = [("Concurrent Lamp A", "User intent A"),
                    ("Concurrent Lamp B", "User intent B")]
        requests = [
            self.intake_request(directory, revision, product_name=name, user_intent=intent)
            for name, intent in attempts
        ]
        barrier = threading.Barrier(3)

        def send(request):
            body, content_type = request
            barrier.wait(timeout=5)
            return self.request("PUT", "/api/intake", body=body, content_type=content_type)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(send, request) for request in requests]
            barrier.wait(timeout=5)
            results = [future.result(timeout=15) for future in futures]

        parsed = [(status, self.json_payload(payload)) for status, _, payload in results]
        winners = [(status, body) for status, body in parsed if status == 200 and body.get("ok")]
        losers = [(status, body) for status, body in parsed if status == 409 and not body.get("ok")]
        self.assertEqual(len(winners), 1, parsed)
        self.assertEqual(len(losers), 1, parsed)
        loser_code = losers[0][1]["error"]["code"]
        self.assertIn(loser_code, {"REVISION_CONFLICT", "WORKSPACE_BUSY"}, parsed)

        if loser_code == "WORKSPACE_BUSY":
            stale_body, stale_type = requests[1]
            status, _, payload = self.request(
                "PUT", "/api/intake", body=stale_body, content_type=stale_type
            )
            stale = self.json_payload(payload)
            self.assertEqual(status, 409, stale)
            self.assertEqual(stale["error"]["code"], "REVISION_CONFLICT", stale)

        after = self.workspace_projection(directory)
        winner_name = winners[0][1]["data"]["intake"]["product_name"]
        self.assertEqual(after["intake"]["product_name"], winner_name)
        self.assertIn(winner_name, {name for name, _ in attempts})

    def test_ordered_reference_set_supports_reorder_insert_and_remove(self) -> None:
        directory, created = self.create_workspace("ordered-references")
        image_a = png_bytes((72, 118, 164))
        image_b = png_bytes((196, 88, 64))
        image_c = png_bytes((46, 150, 92))
        sha_a = hashlib.sha256(image_a).hexdigest()
        sha_b = hashlib.sha256(image_b).hexdigest()
        sha_c = hashlib.sha256(image_c).hexdigest()

        # A first upload set can already be ordered differently from the
        # selection order; the first entry becomes the primary reference.
        status, _, payload = self.save_intake(
            directory, created["workspace"]["revision"],
            images=[("a.png", image_a), ("b.png", image_b)],
            reference_order=["upload:1", "upload:0"],
        )
        first = self.json_payload(payload)
        self.assertEqual(status, 200, first)
        self.assertTrue(first["ok"], first)
        first_data = first["data"]
        self.assertEqual(
            [(item["name"], item["sha256"]) for item in first_data["intake"]["reference_images"]],
            [("b.png", sha_b), ("a.png", sha_a)],
        )

        # Reordering without uploading keeps the same bytes in place.
        status, _, payload = self.save_intake(
            directory, first_data["workspace"]["revision"], images=[],
            reference_order=["sha256:" + sha_a, "sha256:" + sha_b],
        )
        reordered = self.json_payload(payload)
        self.assertEqual(status, 200, reordered)
        second_data = reordered["data"]
        self.assertEqual(
            [item["sha256"] for item in second_data["intake"]["reference_images"]],
            [sha_a, sha_b],
        )

        # A new upload can be inserted between two existing references.
        status, _, payload = self.save_intake(
            directory, second_data["workspace"]["revision"],
            images=[("c.png", image_c)],
            reference_order=["sha256:" + sha_b, "upload:0", "sha256:" + sha_a],
        )
        inserted = self.json_payload(payload)
        self.assertEqual(status, 200, inserted)
        third_data = inserted["data"]
        self.assertEqual(
            [item["sha256"] for item in third_data["intake"]["reference_images"]],
            [sha_b, sha_c, sha_a],
        )

        # Leaving an image out of the order removes it from the set.
        status, _, payload = self.save_intake(
            directory, third_data["workspace"]["revision"], images=[],
            reference_order=["sha256:" + sha_c],
        )
        removed = self.json_payload(payload)
        self.assertEqual(status, 200, removed)
        fourth_data = removed["data"]
        self.assertEqual(
            [item["sha256"] for item in fourth_data["intake"]["reference_images"]],
            [sha_c],
        )

        # Unknown digests, an empty order and duplicated upload tokens are
        # rejected without moving the workspace revision.
        rejected_cases = [
            (["sha256:" + "0" * 64], [], "REFERENCE_ORDER_INVALID"),
            ([], [], "REFERENCE_IMAGE_COUNT"),
            (["upload:0", "upload:0"], [("d.png", image_a)], "REFERENCE_ORDER_INVALID"),
        ]
        for order, images, code in rejected_cases:
            status, _, payload = self.save_intake(
                directory, fourth_data["workspace"]["revision"], images=images,
                reference_order=order,
            )
            rejected = self.json_payload(payload)
            self.assertEqual(status, 422, rejected)
            self.assertEqual(rejected["error"]["code"], code, rejected)
            after = self.workspace_projection(directory)
            self.assertEqual(
                after["workspace"]["revision"], fourth_data["workspace"]["revision"]
            )
            self.assertEqual(
                [item["sha256"] for item in after["intake"]["reference_images"]],
                [sha_c],
            )

        # Assets are append-only: every uploaded original is still on disk
        # with unchanged bytes after reorder, insert, remove and rejections.
        document = json.loads((directory / "workspace.json").read_text(encoding="utf-8"))
        assets = {asset["sha256"]: asset for asset in document["assets"]}
        self.assertEqual(set(assets), {sha_a, sha_b, sha_c})
        for digest in (sha_a, sha_b, sha_c):
            stored = directory / assets[digest]["relative_path"]
            self.assertTrue(stored.exists(), stored)
            self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), digest)

    def test_file_path_is_rejected_as_workspace_directory(self) -> None:
        not_a_directory = self.root / "not-a-folder.txt"
        not_a_directory.write_text("keep this file", encoding="utf-8")
        status, _, payload = self.json_request(
            "POST", "/api/workspaces", {"directory": str(not_a_directory)}
        )
        envelope = self.json_payload(payload)
        self.assertEqual(status, 422, envelope)
        self.assertFalse(envelope["ok"], envelope)
        self.assertEqual(envelope["error"]["code"], "DIRECTORY_NOT_FOLDER")
        self.assertEqual(not_a_directory.read_text(encoding="utf-8"), "keep this file")


if __name__ == "__main__":
    unittest.main(verbosity=2)
