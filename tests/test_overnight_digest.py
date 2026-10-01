from logistics_digest.overnight_digest import (
    OvernightDigestRequest,
    attention_reason,
    batch_requests,
    deliver_digest,
)


def test_delivered_shipment_without_received_proof_enters_batch() -> None:
    request = OvernightDigestRequest.model_validate(
        {
            "report_date": "2026-09-15",
            "shipments": [
                {
                    "shipment_id": "SHIP-104",
                    "state": "delivered",
                    "latest_event": "Delivered at depot",
                    "proof_of_delivery": {"document_name": "receipt.pdf", "received": False},
                },
                {
                    "shipment_id": "SHIP-105",
                    "state": "in_transit",
                    "latest_event": "Departed hub",
                },
            ],
        }
    )

    assert attention_reason(request.shipments[0]) == "delivery has no received proof"
    assert [item["custom_id"] for item in batch_requests(request.shipments)] == ["SHIP-104"]


def test_digest_uses_batch_response_shape_and_unique_run_keys() -> None:
    request = OvernightDigestRequest.model_validate(
        {
            "report_date": "2026-09-15",
            "shipments": [
                {"shipment_id": "SHIP-104", "state": "delayed", "latest_event": "Held at depot"}
            ],
        }
    )

    class StubClient:
        def __init__(self) -> None:
            self.calls = []

        def request(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs["path"] == "/ai/batch/submit":
                return {"batch_id": f"batch-{len(self.calls)}"}
            if kwargs["path"].startswith("/ai/batch/results/"):
                return {"items": [{"request_index": 0, "result": {"content": "Delayed at depot."}}]}
            return {"id": "pdf-1"}

    client = StubClient()
    deliver_digest(request, client)
    deliver_digest(request, client)
    assert client.calls[0]["request_key"] != client.calls[3]["request_key"]
    assert client.calls[1]["path"] == "/ai/batch/results/batch-1"
    assert "Delayed at depot." in client.calls[2]["body"]["markdown"]
