---
name: human-trader-signal-pipeline
description: "Add a human-trader role to an otherwise automated trading signal pipeline. A hired trader signs into the community, gets badged, mirrors to a channel, and lands in a public signal log."
version: 1.0.0
license: MIT
author: "the maintainers"
---
# Human-authored event pipeline

## Purpose

Accept authorized human-authored trading events, validate them and deliver them reliably. This skill describes transport and access control only. Trading decisions, strategy logic, sizing rules and execution thresholds are supplied privately by the operator.

## Implementation

1. Choose a structured form or an authorized messaging channel as the input. Prefer structured input when validation matters.
2. Authenticate the author. Check permission on the server for every write; client-side role badges are display only.
3. Validate an explicit schema: instrument, direction, author, timestamp and optional operator-provided price fields. Reject unknown fields and malformed numbers. Do not infer a trade from untrusted prose.
4. Generate an immutable event ID. Store the event and an outbox entry in one database transaction.
5. Deliver outbox entries to configured destinations using bounded retries and idempotency keys. Keep provider credentials in server-side secret storage.
6. Track delivery separately from the event itself. A messaging-provider success does not prove a database write, browser notification or order execution.
7. Record corrections as new versioned events. Preserve author attribution and an audit trail while limiting access to personal data.
8. Define retention and deletion rules for messages and author metadata.

## Example schema

```json
{"event_id":"example-event-001","author_id":"example-author","instrument":"EXAMPLE","direction":"buy","created_at":"2030-01-01T00:00:00Z"}
```

All example values are synthetic. Configure actual instruments, permissions and destinations in the consuming application.

## Verification

- Unauthorized authors cannot create or edit events.
- Duplicate webhook delivery produces one stored event and one delivery per destination.
- Invalid or out-of-order events are handled explicitly.
- Provider downtime leaves retryable outbox entries rather than losing events.
- Logs redact credentials, full webhook payloads and personal data.
- Test fixtures contain no real trading strategies or account information.
