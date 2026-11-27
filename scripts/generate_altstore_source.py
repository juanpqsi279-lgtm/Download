"""Generate and update altstore-source.json for AltStore / SideStore automatic updates."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_REPO = "juanpqsi279-lgtm/Download"
BUNDLE_ID = "com.juancorporation.exclaimdownload"
APP_NAME = "!Download"
DEVELOPER_NAME = "Juan Corporation"
TINT_COLOR = "#0A84FF"
MIN_IOS_VERSION = "15.0"


def _parse_semver(ver: str) -> tuple[int, ...]:
    cleaned = ver.strip().lstrip("vV")
    parts: list[int] = []
    for token in cleaned.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def build_altstore_source(
    version: str,
    ipa_size: int = 0,
    release_notes: str = "",
    existing_data: dict[str, Any] | None = None,
    repo: str = DEFAULT_REPO,
    release_date: str | None = None,
) -> dict[str, Any]:
    """Build or update an AltStore/SideStore source manifest preserving previous versions."""
    clean_ver = version.strip().lstrip("vV")
    tag = f"v{clean_ver}"
    iso_date = release_date or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    notes_text = (release_notes or "").strip() or (
        f"!Download {tag}: descarga de video/audio, playlists, reproductor nativo con "
        "ecualizador de 10 bandas, editor de metadatos y listas personalizadas."
    )

    existing_versions: list[dict[str, Any]] = []
    if isinstance(existing_data, dict):
        apps = existing_data.get("apps")
        if isinstance(apps, list) and apps and isinstance(apps[0], dict):
            prev_vers = apps[0].get("versions")
            if isinstance(prev_vers, list):
                existing_versions = [v for v in prev_vers if isinstance(v, dict) and v.get("version")]

    versions_by_ver: dict[str, dict[str, Any]] = {}
    for entry in existing_versions:
        ver_key = str(entry["version"]).strip().lstrip("vV")
        if ver_key:
            versions_by_ver[ver_key] = dict(entry, version=ver_key)

    versions_by_ver[clean_ver] = {
        "version": clean_ver,
        "date": iso_date,
        "localizedDescription": notes_text,
        "downloadURL": f"https://github.com/{repo}/releases/download/{tag}/Download-{tag}-ios.ipa",
        "size": max(0, int(ipa_size)),
        "minOSVersion": MIN_IOS_VERSION,
    }

    sorted_versions = sorted(
        versions_by_ver.values(),
        key=lambda item: _parse_semver(str(item.get("version", "0"))),
        reverse=True,
    )

    icon_url = f"https://raw.githubusercontent.com/{repo}/main/static/icon.png"
    website_url = f"https://github.com/{repo}"

    return {
        "name": f"{APP_NAME} · {DEVELOPER_NAME}",
        "subtitle": "Descargador multimedia y reproductor Liquid Glass",
        "description": (
            "Fuente oficial de !Download para SideStore y AltStore. "
            "Descarga videos hasta 8K, música en alta calidad, playlists completas y "
            "reproduce tus archivos con ecualizador de 10 bandas y editor de metadatos."
        ),
        "iconURL": icon_url,
        "website": website_url,
        "tintColor": TINT_COLOR,
        "featuredApps": [BUNDLE_ID],
        "apps": [
            {
                "name": APP_NAME,
                "bundleIdentifier": BUNDLE_ID,
                "developerName": DEVELOPER_NAME,
                "subtitle": "Video, audio, playlists y reproductor con EQ",
                "localizedDescription": (
                    "Descarga video hasta 8K o extrae audio en M4A/MP3 desde más de 1,000 sitios "
                    "con estética Apple Liquid Glass. Incluye gestor de playlists, reproductor "
                    "nativo de audio y video con ecualizador de 10 bandas, guía de ecualización "
                    "y editor manual o automático de metadatos y carátulas."
                ),
                "iconURL": icon_url,
                "tintColor": TINT_COLOR,
                "category": "utilities",
                "versions": sorted_versions,
                "appPermissions": {
                    "entitlements": [],
                    "privacy": {
                        "NSPhotoLibraryAddUsageDescription": (
                            "!Download puede guardar tus videos o audios descargados "
                            "en tu fototeca o Archivos cuando los compartes."
                        )
                    },
                },
            }
        ],
        "news": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate AltStore/SideStore source JSON.")
    parser.add_argument("--tag", required=True, help="Release tag or version (e.g. v1.6.0)")
    parser.add_argument("--ipa", help="Path to the packaged .ipa file to measure exact byte size")
    parser.add_argument("--size", type=int, default=0, help="Fallback .ipa size in bytes")
    parser.add_argument("--notes", default="", help="Release notes text")
    parser.add_argument("--existing", help="Existing altstore-source.json to preserve previous versions")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub owner/repo")
    args = parser.parse_args()

    ipa_size = args.size
    if args.ipa:
        ipa_path = Path(args.ipa)
        if ipa_path.is_file():
            ipa_size = ipa_path.stat().st_size

    existing_data: dict[str, Any] | None = None
    if args.existing:
        existing_path = Path(args.existing)
        if existing_path.is_file():
            try:
                existing_data = json.loads(existing_path.read_text(encoding="utf-8"))
            except Exception:
                existing_data = None

    manifest = build_altstore_source(
        version=args.tag,
        ipa_size=ipa_size,
        release_notes=args.notes,
        existing_data=existing_data,
        repo=args.repo,
    )
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Generated {out_path} (version={manifest['apps'][0]['versions'][0]['version']}, size={ipa_size})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
