"""Lazily built googleapiclient services, shared by every client."""

from typing import Any

from googleapiclient.discovery import build

from gsuite_core.api_utils import authorized_http


class GoogleService:
    """Descriptor for a discovery-based API service, built on first access.

    The owner needs an ``auth`` attribute (a ``GoogleAuth``). The service is
    built with :func:`authorized_http`, so requests time out, and cached on
    the instance. Assigning replaces it, which is how tests or callers inject
    a fake or a preconfigured service::

        class Drive:
            service = GoogleService("drive", "v3")

        drive = Drive(auth)
        drive.service = fake_service

    Args:
        api: Discovery API name, e.g. ``"gmail"``.
        version: API version, e.g. ``"v1"``.
        attr: Instance attribute that caches the service; defaults to the
            descriptor's name with a leading underscore (``service`` ->
            ``_service``).
    """

    def __init__(self, api: str, version: str, *, attr: str | None = None) -> None:
        self.api = api
        self.version = version
        self.attr = attr

    def __set_name__(self, owner: type, name: str) -> None:
        if self.attr is None:
            self.attr = f"_{name}"

    def __get__(self, obj: object, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        service = getattr(obj, self._attr, None)
        if service is None:
            auth = obj.auth  # type: ignore[attr-defined]
            service = build(
                self.api,
                self.version,
                http=authorized_http(auth.credentials),
                cache_discovery=False,
            )
            setattr(obj, self._attr, service)
        return service

    def __set__(self, obj: object, value: Any) -> None:
        setattr(obj, self._attr, value)

    @property
    def _attr(self) -> str:
        if self.attr is None:
            raise TypeError("GoogleService must be assigned in a class body")
        return self.attr
