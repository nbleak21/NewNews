# Changelog

All notable changes to NewNews are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-11-22

Initial release.

### Added
- Pipeline that reads a list of public news-podcast RSS feeds and writes one
  combined `feed.xml`: `fetch` (conditional GET), `parse`, `select` (newest
  unplayed episodes fitting ~25 minutes with a mix of outlets), `feedwriter`,
  and SQLite `state` for cross-run dedup and retention.
- `commute-news` CLI with a `build` command (plus `--dry-run`).
- YAML configuration with a default for every key; secrets (feed token, ntfy
  topic) kept in `.env`, never committed.
- Optional [ntfy.sh](https://ntfy.sh) failure alerts.
- launchd install script for hourly scheduled runs, and serving docs covering
  Tailscale Funnel and Cloudflare Tunnel / R2 + Pages.
- Agent build-loop scripts (OpenCode, Aider, Qwen) used to construct the project.
- Offline test suite (157 tests) with a global network guard so tests never hit
  the network.

[Unreleased]: https://github.com/nbleak21/NewNews/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nbleak21/NewNews/releases/tag/v0.1.0
