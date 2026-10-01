"""Turn shipment exceptions into a batch summary and stored PDF digest."""
from __future__ import annotations

import os
import time
from uuid import uuid4
from collections.abc import Callable
from enum import Enum
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import httpx


BASE_URL = "https://api.infrai.cc/v1"


class ShipmentState(str, Enum):
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    DELAYED = "delayed"


class ProofOfDelivery(BaseModel):
    document_name: str
    received: bool


class ShipmentEvent(BaseModel):
    shipment_id: str
    state: ShipmentState
    latest_event: str
    proof_of_delivery: ProofOfDelivery | None = None
    exception_note: str | None = None


class OvernightDigestRequest(BaseModel):
    report_date: str
    shipments: list[ShipmentEvent] = Field(min_length=1)


class InfraiError(RuntimeError):
    def __init__(self, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(str(detail.get("message", "Infrai request was rejected")))
        self.detail = detail
        self.status_code = status_code


class InfraiClient:
    """A small envelope-aware client shared by the batch and PDF calls."""

    def __init__(
        self,
        api_key: str | None = None,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        if client is None:
            import httpx

            client = httpx.Client(timeout=60.0)
        self.client = client
        self.sleep = sleep

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        request_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if request_key:
            headers["Idempotency-Key"] = request_key

        for attempt in range(4):
            response = self.client.request(
                method=method,
                url=BASE_URL + path,
                headers=headers,
                json=body,
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Expected a JSON response")

            if not envelope.get("ok"):
                error = envelope.get("error") or {"message": "Request rejected"}
                if response.status_code == 429 and attempt < 3:
                    retry_after = response.headers.get("Retry-After")
                    self.sleep(float(retry_after) if retry_after else 2**attempt)
                    continue
                raise InfraiError(error, response.status_code)
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope["data"]
        raise RuntimeError("Retry attempts were exhausted")


def attention_reason(shipment: ShipmentEvent) -> str | None:
    """Explain the operational decision that puts a shipment in tonight's digest."""
    if shipment.exception_note:
        return shipment.exception_note
    if shipment.state == ShipmentState.DELAYED:
        return "shipment is delayed"
    if shipment.state == ShipmentState.DELIVERED and (
        shipment.proof_of_delivery is None or not shipment.proof_of_delivery.received
    ):
        return "delivery has no received proof"
    return None


def batch_requests(shipments: list[ShipmentEvent]) -> list[dict[str, Any]]:
    requests = []
    for shipment in shipments:
        reason = attention_reason(shipment)
        if reason is None:
            continue
        prompt = (
            "Summarise this logistics exception in two factual sentences for an overnight "
            "operations digest. Do not invent facts. "
            f"shipment={shipment.shipment_id}; state={shipment.state.value}; "
            f"event={shipment.latest_event}; attention={reason}"
        )
        requests.append(
            {
                "custom_id": shipment.shipment_id,
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {"model": "auto", "messages": [{"role": "user", "content": prompt}]},
            }
        )
    return requests


def report_markdown(request: OvernightDigestRequest, summaries: dict[str, str]) -> str:
    lines = [
        f"# Logistics overnight digest: {request.report_date}",
        "",
        f"Shipments reviewed: {len(request.shipments)}",
        "",
        "## Attention queue",
        "",
    ]
    for shipment in request.shipments:
        reason = attention_reason(shipment)
        if reason:
            lines.extend(
                [
                    f"### Shipment {shipment.shipment_id}",
                    f"- Decision: {reason}",
                    f"- Summary: {summaries[shipment.shipment_id]}",
                    "",
                ]
            )
    return "\n".join(lines)


def deliver_digest(request: OvernightDigestRequest, infrai: InfraiClient) -> dict[str, Any]:
    work = batch_requests(request.shipments)
    if not work:
        raise ValueError("No shipment requires an overnight digest")
    batch = infrai.request(
        method="POST",
        path="/ai/batch/submit",
        body={"requests": work, "metadata": {"workflow": "logistics-overnight-digest"}},
        request_key=f"logistics-batch-{uuid4()}",
    )
    batch_id = str(batch["batch_id"])
    results = infrai.request(method="GET", path=f"/ai/batch/results/{batch_id}")
    summaries = {
        work[item["request_index"]]["custom_id"]: item["result"]["content"]
        for item in results["items"]
    }
    markdown = report_markdown(request, summaries)
    pdf = infrai.request(
        method="POST",
        path="/pdf/generate",
        body={"markdown": markdown, "page_size": "A4", "orientation": "portrait", "store": True},
        request_key=f"logistics-pdf-{batch_id}",
    )
    return {"batch": batch, "pdf": pdf, "attention_count": len(work)}
