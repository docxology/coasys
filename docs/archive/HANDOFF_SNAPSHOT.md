# Recorded fleet handoff

The existing release smoke test checks the local inventory against a
previously recorded fleet handoff. The documented inventory had 99
repositories, all cloned, with zero dirty or behind checkouts. It also
recorded 12 configured repositories, 84 detected-only repositories,
three unconfigured repositories, 95 passing validations, and four
warnings.

The inventory is stored locally under `workspace/`. Use the
[operations runbook](../OPERATIONS.md) to refresh it and the
[release checklist](../RELEASE_CHECKLIST.md) to distinguish a populated
handoff workspace from a clean source checkout.
