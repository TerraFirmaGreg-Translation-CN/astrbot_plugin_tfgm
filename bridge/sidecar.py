"""Sidecar 0.13.15.2 HTTP contract; never follow credential-bearing redirects."""

import json

import aiohttp


class SidecarError(Exception):
    def __init__(self, code, retry=False, ambiguous=False):
        super().__init__(code)
        self.code, self.retry, self.ambiguous = code, retry, ambiguous


class Sidecar:
    def __init__(self, session, config, timeout):
        self.session, self.config, self.timeout = session, config, timeout

    async def request(self, path, body=None):
        token = self.config["message_token" if body is not None else "read_token"]
        try:
            async with self.session.request(
                "POST" if body is not None else "GET",
                self.config["url"] + "/api/v1/" + path,
                headers={"Authorization": "Bearer " + token} if token else {},
                json=body,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                allow_redirects=False,
            ) as response:
                raw = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    raw.extend(chunk)
                    if len(raw) > 2 * 1024 * 1024:
                        raise SidecarError("response_too_large", ambiguous=body is not None)
                if response.status not in (200, 202):
                    # 500 may mean partially delivered; retry only the identical request.
                    raise SidecarError(
                        f"http_{response.status}",
                        retry=response.status in (429, 500, 502, 503, 504),
                        ambiguous=body is not None and response.status >= 500,
                    )
                try:
                    data = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    raise SidecarError("invalid_json", ambiguous=body is not None) from None
                if not isinstance(data, dict):
                    raise SidecarError("invalid_response", ambiguous=body is not None)
                return response.status, data
        except (aiohttp.ClientError, TimeoutError):
            raise SidecarError("network_error", retry=True, ambiguous=body is not None) from None

    async def health(self):
        _, data = await self.request("health")
        if data.get("api_version") != "1" and data.get("api_version") != 1:
            raise SidecarError("unsupported_api_version")
        if not isinstance(data.get("instance_id"), str) or not data["instance_id"]:
            raise SidecarError("missing_instance_id")
        version = str(data.get("mod_version", ""))
        try:
            compatible = tuple(map(int, version.split("."))) >= (0, 13, 15, 2)
        except ValueError:
            compatible = False
        if not compatible:
            raise SidecarError("requires_sidecar_0.13.15.2")
        return data

    async def events(self, since, limit):
        _, data = await self.request(f"events?since_seq={since}&limit={limit}")
        if not isinstance(data.get("events"), list) or not isinstance(data.get("instance_id"), str):
            raise SidecarError("invalid_events")
        return data

    async def send(self, body):
        status, data = await self.request("messages", body)
        if data.get("request_id") != body["request_id"] or not isinstance(
            data.get("instance_id"), str
        ):
            raise SidecarError("invalid_delivery_response", ambiguous=True)
        if status == 202 and data.get("status") == "processing":
            return data
        if (
            status != 200
            or data.get("status") != "completed"
            or type(data.get("delivered_count")) is not int
        ):
            raise SidecarError("invalid_delivery_response", ambiguous=True)
        return data
