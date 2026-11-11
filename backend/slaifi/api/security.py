"""Request guards for state-changing SLAIFI routes.

Browsers will not attach a custom header to a cross-site *simple* request, and the CORS policy
only allows the configured origins to send it. Requiring ``X-SLAIFI-Client`` on every mutating
route therefore blocks drive-by cross-site POSTs against a locally running API without
introducing accounts. Real-money trading is not reachable through any route.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from slaifi.core.config import Settings
from slaifi.core.utils.errors import SlaifiError

CLIENT_HEADER = "X-SLAIFI-Client"


class ClientHeaderRequired(SlaifiError):
    """Raised when a mutating request lacks the client marker header."""


def require_client_header(
    request: Request,
    x_slaifi_client: Annotated[str | None, Header(alias=CLIENT_HEADER)] = None,
) -> None:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, Settings) and not settings.api_require_client_header:
        return
    if not x_slaifi_client or not x_slaifi_client.strip():
        raise ClientHeaderRequired(
            f"{CLIENT_HEADER} header is required for requests that change state"
        )


MutationGuard = Depends(require_client_header)
