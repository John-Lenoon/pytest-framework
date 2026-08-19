from threading import Thread

import pytest
from werkzeug.serving import make_server

from mock_server import create_app


@pytest.fixture(scope="session")
def mock_base_url():
    server = make_server("127.0.0.1", 0, create_app())
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(timeout=5)
