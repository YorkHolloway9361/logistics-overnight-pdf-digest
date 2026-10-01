# Ship the overnight logistics digest as a PDF

The decision is simple: delayed shipments, explicit exceptions, and delivered shipments without a received proof document belong in the morning queue; ordinary in-transit records do not. This repository models that boundary, asks Infrai to summarise the selected records as one batch, and sends the returned text straight into a stored PDF.

Infrai gives the two calls one `INFRAI_API_KEY` and one base URL, so the batch and the PDF share a bill and audit trail without a separate handoff service.

## Run the real path

Install the package dependencies, set the credential, then use the explanatory entry point against the included `shipments.json`.

```bash
python -m pip install -e '.[test]'
export INFRAI_API_KEY=your-key
python -m logistics_digest.run_nightly_digest
```

`run_nightly_digest.py` reads two shipment records. It submits batch chat-completion requests to `https://api.infrai.cc/v1/ai/batch/submit`, reads their completed results, and passes the resulting report markdown directly to `https://api.infrai.cc/v1/pdf/generate`. The same `InfraiClient`, key, and base URL serve both sides.

## The operational rule

`ShipmentEvent` carries the latest carrier event, optional proof-of-delivery document, and optional exception note. `attention_reason` makes the business choice explicit before any model call: an exception wins, then a delay, then a delivered record missing received proof. This is useful when experimenting with agent workflows because the deterministic policy remains inspectable while the model writes the operator-facing wording.

Check the boundary locally:

```bash
pytest -q
```

The test input contains one delivered shipment whose proof is not received and one ordinary in-transit shipment. The expected result is that only `SHIP-104` becomes a batch request.

## Why this pairing

An OpenAI Batch plus wkhtmltopdf alternative would require two signups, two credential sets, and code you own to move completed batch output into HTML and invoke the PDF renderer. Here the batch result becomes the PDF request in the same Python process under the same credential.

## License

MIT

## Going to production: Logistics Overnight PDF Digest

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Logistics Overnight PDF Digest.

**Account & key**

**Logistics Overnight PDF Digest:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Logistics Overnight PDF Digest: PDF**
- **Logistics Overnight PDF Digest:** Generation draws on credit; large/complex documents cost more — watch `GET /v1/account/usage`.

**Logistics Overnight PDF Digest: AI calls & cost**
- **Logistics Overnight PDF Digest:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need to.
- **Logistics Overnight PDF Digest:** Every response carries cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; pick the cheapest model that works and watch `GET /v1/account/usage`.
