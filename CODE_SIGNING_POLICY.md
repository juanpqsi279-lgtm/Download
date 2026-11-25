# Code Signing Policy

Free code signing provided by [SignPath.io](https://signpath.io), certificate by [SignPath Foundation](https://signpath.org).

This policy describes how official Windows release binaries for **!Download** (developed by **Juan Corporation**) are built, verified, signed, and distributed to guarantee integrity and authenticity.

---

## Covered Artifacts

* **Signed Artifacts:** Only official Windows binaries produced directly by our automated release workflow (`.github/workflows/release.yml`) from tagged commits in this repository are signed:
  * `!Download.exe` (main Windows application executable, also packaged inside the portable archive)
  * `!Download-Setup-<version>.exe` (Windows installer built with Inno Setup)
* **Exclusions:** Binaries compiled on developer workstations, unverified forks, pre-release local test builds, and third-party upstream tools bundled for runtime compatibility (`ffmpeg.exe`, `ffprobe.exe`, `deno.exe`) are not signed by this certificate.

---

## Build and Signing Pipeline

1. **Source Repository:** Releases are built exclusively from the public repository at https://github.com/juanpqsi279-lgtm/Download.
2. **Build Environment:** All Windows release builds run on GitHub-hosted runners (`windows-latest`) via GitHub Actions defined in [`.github/workflows/release.yml`](.github/workflows/release.yml).
3. **Verification & Signing:** Unsigned artifacts are uploaded through `actions/upload-artifact` and submitted to SignPath.io via `signpath/github-action-submit-signing-request`, where SignPath independently verifies build provenance and repository policies before signing inside the SignPath Foundation Hardware Security Module (HSM).

---

## Team Roles & Responsibilities

Multi-factor authentication (MFA) is enforced on all GitHub and SignPath accounts with repository, build, or signing privileges:

* **Maintainer / Committer / Reviewer:** `@juanpqsi279-lgtm` (Juan Corporation)
  * Responsible for maintaining the public codebase, verifying dependencies, and ensuring no unauthorized or proprietary code is included.
* **Approver:** `@juanpqsi279-lgtm` (Juan Corporation)
  * Responsible for reviewing and authorizing release signing requests before signed Windows artifacts are published to GitHub Releases.

---

## Privacy & Network Behavior

* `!Download` runs locally on the user's device and contains no telemetry, analytics, or tracking.
* Network connections are initiated exclusively by explicit user actions (inspecting or downloading user-provided media URLs, checking for `!Download` updates via the GitHub Releases API, or updating `yt-dlp`).
* During automated CI releases, build metadata and release artifacts are processed by GitHub Actions and SignPath.io to verify provenance and apply signatures.

---

## Reporting a Problem

If you suspect a signed release binary has been tampered with, does not match the public source code, or exhibits unexpected behavior, please report it immediately:

* **Issue Tracker:** https://github.com/juanpqsi279-lgtm/Download/issues
* **Repository:** https://github.com/juanpqsi279-lgtm/Download
