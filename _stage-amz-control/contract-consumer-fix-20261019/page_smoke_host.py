from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.product_v2_server import create_product_v2_server
from src.providers.v2_fake_image import FakeImageProvider
from src.providers.v2_fake_review import FakeReviewProvider
from src.providers.v2_fake_semantic import FakeSemanticProvider

server = create_product_v2_server(
    "127.0.0.1", 9161,
    provider_factory=lambda: FakeSemanticProvider("ok"),
    image_provider_factory=lambda: FakeImageProvider("ok", size=1200),
    review_provider_factory=lambda: FakeReviewProvider("ok"),
)
server.start()
print("Isolated fake-only consumer smoke ready: http://127.0.0.1:9161/", flush=True)
try:
    threading.Event().wait()
finally:
    server.stop()
