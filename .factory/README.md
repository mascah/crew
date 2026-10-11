# Factory setup

This project owns its Factory profile, setup script and worker Dockerfile.
The runtime and operating commands live in [mascah/factory](https://github.com/mascah/factory).

Build `factory-base` from the Factory checkout, then build `crew-worker`
with `docker build -t crew-worker -f .factory/Dockerfile .`.
Keep toolchain pins here aligned with this project's dependency metadata.

The host maps `crew` to a trusted checkout and its full base-branch ref.
Factory reads these committed files from that ref, ignoring uncommitted
changes and candidate checkout policy. Serving is enabled separately by
listing `crew` in the host's `projects` array.
