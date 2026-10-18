# Migration 20261007

Back up the database and document storage before rollout. Stop old API processes,
deploy the new backend, then start it normally. `init_auth_store()` runs the
additive migration before requests or the durable document worker are started.
SQLite remains supported for local development; PostgreSQL uses a transaction
advisory lock during this migration. Run one SQLite process during migration.

The migration preserves existing users, documents and chats. It adds document
versions, failure details, ingestion attempts, content hashes and request keys;
chat sequence numbers and structured response payloads; and revocable sessions.
Existing `stored` documents become queued. Review legacy pending uploads before
starting the worker because recovery can invoke the configured memory provider.

Existing bearer tokens require a fresh login. New sessions expire after 12 hours
and logout removes the hashed token from the session table. Old messages with
equal timestamps receive stable ID ordering; their original order cannot be
reconstructed. Old citations without document IDs remain historical text.

Successful deletion removes original/extracted local files and database content,
after provider deletion succeeds. A small tombstone retains the document ID,
dataset identity and request key for idempotency. Prior chat text is retained;
source access is disabled. Provider backups and historical chat retention are
separate from document deletion.

Rollback requires restoring the backup and previous application together.
PostgreSQL compatibility is implemented but requires a staging integration run
before production rollout; local automated verification uses isolated SQLite.
