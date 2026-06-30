from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

GATEWAY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

from gateway.app import PartnerGateway
from gateway.media_routes import _build_minio_presigned_proxy_url
from gateway_tests.helpers import build_wsgi_env


class _FakeUpstreamResponse:
    def __init__(self, body: bytes, *, status: int = 206, headers: dict[str, str] | None = None) -> None:
        self._body = body
        self.status = status
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeUpstreamResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class MediaProxyRouteTests(unittest.TestCase):
    def test_build_minio_presigned_proxy_url_signs_private_bucket_request(self) -> None:
        fake_client = mock.Mock()
        fake_client.get_presigned_url.return_value = (
            "http://minio:9000/her-media/chat/demo.mp3?X-Amz-Signature=test"
        )

        with mock.patch.dict(
            "os.environ",
            {
                "MINIO_ACCESS_KEY": "her_minio_admin",
                "MINIO_SECRET_KEY": "her_minio_password",
            },
            clear=False,
        ):
            with mock.patch("gateway.media_routes.Minio", return_value=fake_client, create=True):
                signed_url = _build_minio_presigned_proxy_url(
                    "http://minio:9000/her-media/chat/demo.mp3",
                    "GET",
                )

        self.assertIn("X-Amz-Signature=test", signed_url)
        fake_client.get_presigned_url.assert_called_once_with(
            "GET",
            "her-media",
            "chat/demo.mp3",
            expires=mock.ANY,
        )

    def test_media_proxy_streams_audio_via_gateway_and_rewrites_local_minio_host(self) -> None:
        gateway = PartnerGateway(
            recommendation_dsn="mysql://noop",
            matchmaking_dsn="mysql://noop",
            chat_dsn="mysql://noop",
            db_pool_max=0,
        )

        environ = build_wsgi_env(
            "GET",
            "/v1/media/proxy",
            query="url=http%3A%2F%2F127.0.0.1%3A9000%2Fher-media%2Fchat%2Fdemo.mp3",
            extra={"HTTP_RANGE": "bytes=0-11"},
        )

        status = ""
        headers: list[tuple[str, str]] = []

        def start_response(current_status: str, current_headers: list[tuple[str, str]]) -> None:
            nonlocal status, headers
            status = current_status
            headers = current_headers

        with mock.patch.dict("os.environ", {"MINIO_ENDPOINT": "minio:9000", "MINIO_SECURE": "false"}, clear=False):
            with mock.patch(
                "gateway.media_routes._build_minio_presigned_proxy_url",
                return_value="http://minio:9000/her-media/chat/demo.mp3",
            ):
                with mock.patch(
                    "gateway.media_routes.urllib_request.urlopen",
                    return_value=_FakeUpstreamResponse(
                        b"partial-audio",
                        headers={
                            "Content-Type": "audio/mpeg",
                            "Content-Length": "13",
                            "Accept-Ranges": "bytes",
                            "Content-Range": "bytes 0-11/42",
                        },
                    ),
                ) as urlopen:
                    body = b"".join(gateway(environ, start_response))

        self.assertEqual(status, "206 Partial Content")
        self.assertEqual(body, b"partial-audio")
        header_map = {key.lower(): value for key, value in headers}
        self.assertEqual(header_map["content-type"], "audio/mpeg")
        self.assertEqual(header_map["content-range"], "bytes 0-11/42")
        self.assertEqual(header_map["accept-ranges"], "bytes")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://minio:9000/her-media/chat/demo.mp3")
        self.assertEqual(request.headers.get("Range"), "bytes=0-11")


if __name__ == "__main__":
    unittest.main()
