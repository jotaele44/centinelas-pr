# Email ingestion adapter v0.1

Status: **design-only, feature-disabled**.

## Boundary

Google Alerts email is a T4 discovery lead. It is not verification of the linked claim.
Raw mailbox records are private, deny federation export, and cannot auto-promote. Only an
operator-accepted `AlertResultRecord` may derive a normal Centinelas `RawItem`; the derived
item remains T4 and carries a separate `RawItemLineage` record.

## Safe defaults

- No production Gmail client.
- No OAuth credentials.
- No polling scheduler.
- No mailbox writes or label mutations.
- No raw RFC822 retention by default.
- Attachment metadata only.
- Remote images, scripts, frames, objects, and embeds are removed offline.
- BCC presence may be recorded, but BCC addresses are never serialized.
- Public/federation export is denied for raw email records.

## Offline dry run

```bash
python scripts/email_ingestion_dry_run.py tests/fixtures/email/google_alert_plain.eml
```

The command reads a local fixture only, prints a redacted diagnostic result, and does not
write to the queue, contact Gmail, or modify a mailbox.

## Review state

`unreviewed -> accepted_as_lead | duplicate | irrelevant | rejected`

Conversion to `RawItem` fails unless the state is `accepted_as_lead`. There is no transition
from email intake directly to a verified signal, developing matter, pending officialization,
or MoneySweep handoff.

## Future live implementation gate

A later PR must separately add a minimum-scope OAuth Gmail client, append-only receipts,
history checkpoint recovery, bounded reconciliation, private storage, operator API routes,
and a diagnostic dashboard. That PR must prove that public federation exports contain no
recipient addresses, raw message bodies, provider message IDs, OAuth material, or attachment
content.
