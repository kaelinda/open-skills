#!/usr/bin/env python3
"""Render Markdown articles as tabbed MDNice-themed HTML previews."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


API_BASE = "https://api.mdnice.com"
THEMES_ENDPOINT = f"{API_BASE}/themes"
STYLES_ENDPOINT = f"{API_BASE}/articles/styles"
REFERENCES_DIR = Path(__file__).resolve().parents[1] / "references"
DEFAULT_CATALOG = REFERENCES_DIR / "mdnice-themes.json"
# The built-in inline pack; every other "<pack>-themes.json" under references/ is
# an auto-discovered stylesheet theme pack (theme-hub, mweb-theme, ...).
BUILTIN_PACK = "mdnice"
PACK_CATALOG_SUFFIX = "-themes.json"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class MdniceError(RuntimeError):
    """Raised for MDNice API or catalog errors."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def cert_error(exc: BaseException) -> bool:
    reason = getattr(exc, "reason", None)
    return isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(exc)


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    token: str | None = None,
    strict_tls: bool = False,
    timeout: int = 25,
) -> dict[str, Any]:
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method=method)
    req.add_header("Accept", "application/json, text/plain, */*")
    req.add_header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
    req.add_header("Origin", "https://editor.mdnice.com")
    req.add_header("Referer", "https://editor.mdnice.com/")
    req.add_header("User-Agent", USER_AGENT)
    if payload is not None:
        req.add_header("Content-Type", "application/json;charset=UTF-8")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        if strict_tls or not cert_error(exc):
            raise
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            return json.loads(resp.read().decode("utf-8"))


def ensure_success(response: dict[str, Any], context: str) -> dict[str, Any]:
    if response.get("success") is True or response.get("code") == 0:
        data = response.get("data")
        if isinstance(data, dict):
            return data
    message = response.get("message") or response
    raise MdniceError(f"{context} failed: {message}")


def fetch_theme_list(page_size: int, strict_tls: bool) -> list[dict[str, Any]]:
    themes: list[dict[str, Any]] = []
    seen: set[int] = set()
    current_page = 1

    while True:
        query = urllib.parse.urlencode({"pageSize": page_size, "currentPage": current_page})
        data = ensure_success(
            request_json(f"{THEMES_ENDPOINT}?{query}", strict_tls=strict_tls),
            f"fetch themes page {current_page}",
        )
        batch = data.get("themeList") or []
        if not isinstance(batch, list) or not batch:
            break

        for item in batch:
            if not isinstance(item, dict):
                continue
            theme_id = item.get("themeId")
            if isinstance(theme_id, int) and theme_id not in seen:
                seen.add(theme_id)
                themes.append(dict(item))

        total = data.get("pageNum")
        if isinstance(total, int) and len(themes) >= total:
            break
        if len(batch) < page_size:
            break
        current_page += 1

    return themes


def fetch_theme_style(theme_id: int, out_id: str, token: str, strict_tls: bool) -> dict[str, Any]:
    data = ensure_success(
        request_json(
            STYLES_ENDPOINT,
            method="PUT",
            body={"outId": out_id, "themeId": theme_id},
            token=token,
            strict_tls=strict_tls,
        ),
        f"fetch style for theme {theme_id}",
    )
    style = data.get("style")
    if not isinstance(style, str) or not style.strip():
        raise MdniceError(f"theme {theme_id} returned no CSS")
    return {
        "styleCss": style,
        "styleDataVersion": data.get("dataVersion"),
        "styleFetchedAt": utc_now(),
    }


def load_catalog(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise MdniceError(f"theme catalog not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_catalog(path: Path, catalog: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pack_catalog_path(pack: str) -> Path:
    return REFERENCES_DIR / f"{pack}{PACK_CATALOG_SUFFIX}"


def pack_dir(pack: str) -> Path:
    return REFERENCES_DIR / pack


def discover_packs() -> list[str]:
    """Names of every auto-discovered stylesheet theme pack: any
    references/<pack>-themes.json except the built-in inline pack (mdnice).
    Drop a new `<pack>-themes.json` + `<pack>/` folder and it loads with no code
    change — that is how theme-hub, mweb-theme, etc. plug in."""
    names = []
    for catalog in sorted(REFERENCES_DIR.glob(f"*{PACK_CATALOG_SUFFIX}")):
        name = catalog.name[: -len(PACK_CATALOG_SUFFIX)]
        if name and name != BUILTIN_PACK:
            names.append(name)
    return names


def load_pack_themes(packs: list[str] | None = None) -> list[dict[str, Any]]:
    """Stylesheet-engine themes from all (or the given) extension packs. Each entry
    references a CSS file under references/<pack>/, read lazily at render time so
    the catalog JSON stays small and the source files remain license-traceable.
    Each theme is tagged with its `pack` so CSS resolves to the right folder."""
    themes: list[dict[str, Any]] = []
    for name in (packs if packs is not None else discover_packs()):
        catalog = pack_catalog_path(name)
        if not catalog.exists():
            continue
        try:
            data = json.loads(catalog.read_text(encoding="utf-8"))
        except Exception:
            continue
        entries = data.get("themes") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            continue
        for theme in entries:
            if isinstance(theme, dict):
                theme.setdefault("engine", "stylesheet")
                theme["pack"] = name
                themes.append(theme)
    return themes


# Back-compat alias (older callers / docs).
def load_hub_themes() -> list[dict[str, Any]]:
    return load_pack_themes()


def pack_theme_css(theme: dict[str, Any]) -> str:
    rel = str(theme.get("file") or "").strip()
    if not rel:
        raise MdniceError(f"stylesheet theme {theme.get('slug')!r} has no file")
    base = pack_dir(str(theme.get("pack") or "theme-hub"))
    css_path = base / rel
    if not css_path.exists():
        raise MdniceError(f"theme CSS not found: {css_path}")
    return css_path.read_text(encoding="utf-8")


# --- Adding stylesheet theme packs -----------------------------------------
# A theme pack is just `references/<pack>-themes.json` + `references/<pack>/`
# (CSS files). `add-theme` vendors a CSS file/URL into a pack, auto-detects the
# wrapper class and light/dark appearance, picks paired code/mermaid themes, and
# registers the entry — creating the pack on first add. To add a whole group,
# loop it or pass `--manifest`.

def fetch_text(url: str, strict_tls: bool = False, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        if strict_tls or not cert_error(exc):
            raise
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            return resp.read().decode("utf-8", "replace")


def _hex_luma(hex_color: str) -> float | None:
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) < 6:
        return None
    try:
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def detect_appearance(css: str) -> str:
    """Guess light/dark from the root/body background colour."""
    low = css.lower()
    match = re.search(
        r"(?:html|body|\.markdown-body|:root)\s*\{[^}]*?background(?:-color)?\s*:\s*#([0-9a-f]{3,8})",
        low,
        re.S,
    )
    if match:
        luma = _hex_luma(match.group(1))
        if luma is not None and luma < 0.4:
            return "dark"
    return "light"


def detect_wrapper_class(css: str) -> tuple[str, str | None]:
    """Guess the wrapper class a theme expects; returns (class, warning)."""
    if "#write" in css:
        return "", "theme references #write (Typora editor DOM); content may need a #write wrapper to style correctly"
    for cls in ("markdown-body", "heti", "typo"):
        if re.search(r"\." + re.escape(cls) + r"(?![\w-])", css):
            return cls, None
    return "", None


def add_theme_entry(spec: dict[str, Any], strict_tls: bool = False) -> dict[str, Any]:
    """Vendor one stylesheet theme into its pack and return the catalog entry."""
    pack = str(spec.get("pack") or "").strip()
    slug = str(spec.get("slug") or "").strip()
    source = str(spec.get("from") or spec.get("source") or "").strip()
    if not (pack and slug and source):
        raise MdniceError(f"theme spec needs pack, slug, and from/source: {spec}")
    category = str(spec.get("category") or "default").strip()

    css = fetch_text(source, strict_tls) if source.startswith(("http://", "https://")) else Path(source).read_text(encoding="utf-8")
    if not css.strip():
        raise MdniceError(f"empty CSS from {source}")

    rel = f"{category}/{slug}.css"
    dest = pack_dir(pack) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(css, encoding="utf-8")

    appearance = str(spec.get("appearance") or "auto")
    if appearance == "auto":
        appearance = detect_appearance(css)
    raw_wrapper = spec.get("wrapperClass")
    if raw_wrapper is None or raw_wrapper == "auto":
        wrapper, warn = detect_wrapper_class(css)
    else:
        wrapper, warn = ("" if raw_wrapper in ("none", "") else str(raw_wrapper)), None
    code_theme = str(spec.get("codeTheme") or ("atom-one-dark" if appearance == "dark" else "github"))
    mermaid_theme = str(spec.get("mermaidTheme") or ("dark" if appearance == "dark" else DEFAULT_MERMAID_THEME))

    entry = {
        "name": str(spec.get("name") or slug),
        "slug": slug,
        "engine": "stylesheet",
        "category": category,
        "file": rel,
        "wrapperClass": wrapper,
        "appearance": appearance,
        "codeTheme": code_theme,
        "mermaidTheme": mermaid_theme,
        "license": str(spec.get("license") or ""),
        "source": str(spec.get("sourceUrl") or (source if source.startswith("http") else "")),
    }

    catalog_path = pack_catalog_path(pack)
    if catalog_path.exists():
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    else:
        data = {"source": pack, "engine": "stylesheet", "themes": []}
    entries = [t for t in (data.get("themes") or []) if isinstance(t, dict) and t.get("slug") != slug]
    entries.append(entry)
    data["themes"] = entries
    catalog_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    label = wrapper or "(body)"
    print(
        f"added '{slug}' to pack '{pack}' [{category}] wrapper={label} appearance={appearance} "
        f"code={code_theme} mermaid={mermaid_theme} -> {dest}",
        file=sys.stderr,
    )
    if warn:
        print(f"  warning: {warn}", file=sys.stderr)
    return entry


def add_theme(args: argparse.Namespace) -> None:
    if args.manifest:
        specs = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        if not isinstance(specs, list):
            raise MdniceError("--manifest must be a JSON array of theme specs")
        for spec in specs:
            spec.setdefault("pack", args.pack)
            add_theme_entry(spec, args.strict_tls)
        print(f"added {len(specs)} theme(s) via manifest", file=sys.stderr)
        return
    spec = {
        "pack": args.pack,
        "slug": args.slug,
        "name": args.name,
        "from": getattr(args, "from_"),
        "category": args.category,
        "license": args.license,
        "sourceUrl": args.source_url,
        "wrapperClass": args.wrapper_class,
        "appearance": args.appearance,
        "codeTheme": args.code_theme,
        "mermaidTheme": args.mermaid_theme,
    }
    add_theme_entry(spec, args.strict_tls)


def all_themes(mdnice_catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """Combined selectable themes: MDNice inline themes + stylesheet hub themes.

    The MDNice catalog is not mutated on disk; the engine tag is added in-memory."""
    combined: list[dict[str, Any]] = []
    for theme in mdnice_catalog.get("themes") or []:
        if isinstance(theme, dict):
            theme.setdefault("engine", "inline")
            combined.append(theme)
    combined.extend(load_pack_themes())
    return combined


def theme_identity(theme: dict[str, Any]) -> Any:
    """Dedup/identity key: MDNice themes use themeId; pack themes use pack+slug so
    two packs can reuse the same slug without colliding."""
    if isinstance(theme.get("themeId"), int):
        return ("id", theme["themeId"])
    return ("slug", str(theme.get("pack") or ""), str(theme.get("slug") or theme.get("name") or ""))


# --- Per-theme CSS file storage --------------------------------------------
# The MDNice catalog used to inline each theme's ~40KB `styleCss` string, so the
# JSON ballooned to >1MB (98% CSS). The CSS now lives in one file per theme under
# references/mdnice-themes/, and the catalog keeps only metadata + a `cssFile`
# pointer (~450 bytes/theme), so it never balloons. `styleCss` is still honoured
# inline for backward compatibility with older catalogs.
MDNICE_CSS_SUBDIR = "mdnice-themes"


def catalog_dir_for(path: Path) -> Path:
    return Path(path).resolve().parent


def slugify_theme_name(name: Any) -> str:
    s = re.sub(r"\s+", "", str(name or ""))          # drop whitespace incl. newlines
    s = re.sub(r'[/\\:*?"<>|]+', "", s)               # drop filesystem-unsafe chars
    return s[:40] or "theme"


def theme_css_filename(theme: dict[str, Any]) -> str:
    tid = theme.get("themeId")
    slug = slugify_theme_name(theme.get("name"))
    base = f"{tid}-{slug}" if tid is not None else slug
    return f"{MDNICE_CSS_SUBDIR}/{base}.css"


def theme_has_style(theme: dict[str, Any]) -> bool:
    return bool(theme.get("styleCss")) or bool(theme.get("cssFile"))


def read_theme_css(catalog_dir: Path, theme: dict[str, Any]) -> str:
    """Resolve a theme's CSS: inline `styleCss` wins (legacy/in-memory), else read
    the per-theme `cssFile` relative to the catalog directory."""
    inline = theme.get("styleCss")
    if inline:
        return str(inline)
    rel = theme.get("cssFile")
    if not rel:
        return ""
    css_path = catalog_dir / rel
    return css_path.read_text(encoding="utf-8") if css_path.exists() else ""


def hydrate_theme_css(theme: dict[str, Any], catalog_dir: Path) -> dict[str, Any]:
    """Populate in-memory `styleCss` from `cssFile` so downstream rendering code
    can stay unchanged. No-op for themes that already carry inline CSS."""
    if not theme.get("styleCss") and theme.get("cssFile"):
        css = read_theme_css(catalog_dir, theme)
        if css:
            theme["styleCss"] = css
    return theme


def externalize_theme_css(catalog_dir: Path, theme: dict[str, Any]) -> bool:
    """Move an inline `styleCss` string out to a per-theme CSS file and replace it
    with a `cssFile` pointer. Returns True if a write happened."""
    css = theme.get("styleCss")
    if not css:
        return False
    rel = theme_css_filename(theme)
    target = catalog_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(css), encoding="utf-8")
    theme["cssFile"] = rel
    theme.pop("styleCss", None)
    return True


def split_catalog(args: argparse.Namespace) -> None:
    """One-off migration: externalize every inline `styleCss` into a per-theme CSS
    file and slim the catalog to metadata + `cssFile`. Idempotent."""
    catalog = load_catalog(args.catalog)
    catalog_dir = catalog_dir_for(args.catalog)
    themes = catalog.get("themes") or []
    moved = sum(1 for theme in themes if isinstance(theme, dict) and externalize_theme_css(catalog_dir, theme))
    catalog["styleCount"] = sum(1 for theme in themes if isinstance(theme, dict) and theme_has_style(theme))
    write_catalog(args.catalog, catalog)
    print(
        f"split {moved} theme styles into {catalog_dir / MDNICE_CSS_SUBDIR}; "
        f"catalog now {args.catalog}",
        file=sys.stderr,
    )


def build_catalog(args: argparse.Namespace) -> None:
    themes = fetch_theme_list(args.page_size, args.strict_tls)
    existing_by_id: dict[int, dict[str, Any]] = {}
    if args.output.exists():
        try:
            existing = load_catalog(args.output)
            existing_by_id = {
                int(theme["themeId"]): theme
                for theme in existing.get("themes", [])
                if isinstance(theme, dict) and isinstance(theme.get("themeId"), int)
            }
        except Exception:
            existing_by_id = {}

    catalog_dir = catalog_dir_for(args.output)
    for theme in themes:
        previous = existing_by_id.get(theme.get("themeId"))
        if previous:
            # Preserve the per-file pointer (and legacy inline CSS / metadata) from
            # an existing catalog so a no-auth refresh never drops cached styles.
            for key in ("cssFile", "styleCss", "styleDataVersion", "styleFetchedAt", "styleError"):
                if previous.get(key):
                    theme[key] = previous[key]

    token = os.environ.get(args.token_env, "").strip()
    out_id = args.out_id or os.environ.get("MDNICE_OUT_ID", "").strip()

    if args.include_styles:
        if not token:
            raise MdniceError(f"--include-styles requires {args.token_env}")
        if not out_id:
            raise MdniceError("--include-styles requires --out-id or MDNICE_OUT_ID")
        for index, theme in enumerate(themes, 1):
            theme_id = theme["themeId"]
            try:
                theme.update(fetch_theme_style(theme_id, out_id, token, args.strict_tls))
                theme.pop("styleError", None)
                print(f"[{index}/{len(themes)}] fetched CSS for {theme_id} {theme.get('name')}", file=sys.stderr)
            except Exception as exc:  # noqa: BLE001 - preserve per-theme failures in the catalog.
                theme["styleError"] = str(exc)
                print(f"[{index}/{len(themes)}] failed CSS for {theme_id}: {exc}", file=sys.stderr)
            time.sleep(args.delay)

    # Always store CSS as one file per theme; the catalog keeps only a `cssFile`
    # pointer so the JSON never balloons (metadata is ~450 bytes/theme).
    for theme in themes:
        externalize_theme_css(catalog_dir, theme)
    style_count = sum(1 for theme in themes if theme_has_style(theme))

    catalog = {
        "source": "mdnice",
        "fetchedAt": utc_now(),
        "api": {
            "themes": THEMES_ENDPOINT,
            "styles": STYLES_ENDPOINT,
            "styleAuth": "MDNICE_TOKEN",
            "styleOutId": "MDNICE_OUT_ID",
        },
        "themeCount": len(themes),
        "styleCount": style_count,
        "cssDir": MDNICE_CSS_SUBDIR,
        "themes": themes,
    }
    write_catalog(args.output, catalog)
    print(f"wrote {len(themes)} themes, {style_count} with CSS files under {catalog_dir / MDNICE_CSS_SUBDIR}", file=sys.stderr)


def theme_label(theme: dict[str, Any]) -> str:
    name = clean_text(str(theme.get("name") or "Unnamed"))
    if str(theme.get("engine")) == "stylesheet":
        bits = [str(theme.get("slug")), name, f"pack:{theme.get('pack')}"]
        category = theme.get("category")
        if category:
            bits.append(str(category))
        appearance = theme.get("appearance")
        if appearance:
            bits.append(str(appearance))
        return " | ".join(bits)
    bits = [str(theme.get("themeId")), name, "mdnice"]
    author = theme.get("applicantUsername")
    if author:
        bits.append(f"by {author}")
    if theme_has_style(theme):
        bits.append("css")
    elif theme.get("styleError"):
        bits.append("style-error")
    return " | ".join(bits)


def list_themes(args: argparse.Namespace) -> None:
    catalog = load_catalog(args.catalog)
    themes = all_themes(catalog)
    query = (args.query or "").casefold()
    if args.json:
        filtered = [
            theme
            for theme in themes
            if (not query or query in json.dumps(theme, ensure_ascii=False).casefold())
            and (not args.with_style_only or theme_has_style(theme) or str(theme.get("engine")) == "stylesheet")
        ]
        print(json.dumps(filtered, ensure_ascii=False, indent=2))
        return

    for theme in themes:
        if args.with_style_only and not theme_has_style(theme) and str(theme.get("engine")) != "stylesheet":
            continue
        haystack = json.dumps(theme, ensure_ascii=False).casefold()
        if query and query not in haystack:
            continue
        print(theme_label(theme))


def split_theme_refs(raw_values: list[str]) -> list[str]:
    refs: list[str] = []
    for raw in raw_values:
        refs.extend(part.strip() for part in raw.split(",") if part.strip())
    return refs


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def theme_ref_label(theme: dict[str, Any]) -> str:
    if isinstance(theme.get("themeId"), int):
        return f"{theme.get('themeId')}:{theme.get('name')}"
    return f"{theme.get('slug')}:{theme.get('name')}"


def resolve_themes(catalog: dict[str, Any], refs: list[str]) -> list[dict[str, Any]]:
    # Search both engines: MDNice inline themes (themeId) and pack stylesheet
    # themes (slug, optionally pack-qualified as "pack:slug"). A digit ref only
    # matches an MDNice themeId; everything else matches a name (exact, then
    # substring) or a slug.
    themes = all_themes(catalog)
    if not themes:
        raise MdniceError("catalog has no themes list")

    selected: list[dict[str, Any]] = []
    used: set[Any] = set()
    for ref in refs:
        match: dict[str, Any] | None = None
        # "pack:slug" disambiguates a slug shared across packs.
        pack_q = None
        slug_ref = ref
        if ":" in ref and not ref.isdigit():
            maybe_pack, _, maybe_slug = ref.partition(":")
            if maybe_pack and maybe_slug:
                pack_q, slug_ref = maybe_pack.strip().casefold(), maybe_slug.strip()
        if ref.isdigit():
            wanted = int(ref)
            match = next((theme for theme in themes if theme.get("themeId") == wanted), None)
        elif pack_q is not None:
            folded = clean_text(slug_ref).casefold()
            hits = [
                theme for theme in themes
                if str(theme.get("pack") or "").casefold() == pack_q
                and str(theme.get("slug") or "").casefold() == folded
            ]
            match = hits[0] if len(hits) == 1 else None
            if len(hits) > 1:
                raise MdniceError(f"theme selector {ref!r} is ambiguous within pack {pack_q!r}")
        else:
            folded = clean_text(ref).casefold()
            slug_hit = [theme for theme in themes if str(theme.get("slug") or "").casefold() == folded]
            exact = [theme for theme in themes if clean_text(str(theme.get("name") or "")).casefold() == folded]
            partial = [theme for theme in themes if folded in clean_text(str(theme.get("name") or "")).casefold()]
            matches = slug_hit or exact or partial
            if len(matches) == 1:
                match = matches[0]
            elif len(matches) > 1:
                names = ", ".join(theme_ref_label(theme) for theme in matches[:8])
                raise MdniceError(f"theme selector {ref!r} is ambiguous: {names}")
        if not match:
            raise MdniceError(f"theme not found: {ref}")
        identity = theme_identity(match)
        if identity not in used:
            selected.append(match)
            used.add(identity)

    if not 1 <= len(selected) <= 5:
        raise MdniceError(f"select 1-5 unique themes, got {len(selected)}")
    return selected


def strip_frontmatter(markdown_text: str) -> str:
    # Drop a leading YAML frontmatter block (--- ... ---). Without this the opening
    # "---" is treated as <hr> and the metadata lines render as a stray paragraph.
    text = markdown_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return markdown_text
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return "\n".join(lines[i + 1 :]).lstrip("\n")
    return markdown_text


def render_markdown(markdown_text: str, flavor: str = "mdnice") -> str:
    # flavor="mdnice": emit MDNice wrapper nodes (.prefix/.content/.suffix spans,
    # li>section, pre.custom code.hljs) so cached MDNice theme CSS can attach and
    # be inlined. flavor="semantic": emit plain semantic HTML (<h2>, <li>, <pre>
    # <code>) so standalone stylesheet themes (github/sakura/...) style it the way
    # their authors intended.
    return render_markdown_fallback(strip_frontmatter(markdown_text), flavor)


def render_markdown_fallback(markdown_text: str, flavor: str = "mdnice") -> str:
    semantic = flavor == "semantic"
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[str] = []
    paragraph: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            text = "<br>\n".join(inline_markup(line.strip()) for line in paragraph)
            blocks.append(f"<p>{text}</p>")
            paragraph = []

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        fence = re.match(r"^```([A-Za-z0-9_-]+)?\s*$", stripped)
        if fence:
            flush_paragraph()
            language = fence.group(1) or ""
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not re.match(r"^```\s*$", lines[index].strip()):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            # Mermaid fences are diagrams, not code: route them to a mermaid.js
            # container so they render as real flowcharts/sequence diagrams the way
            # MDNice does, instead of dumping raw source as a code block.
            if language.lower() == "mermaid":
                blocks.append(render_mermaid_block(chr(10).join(code_lines)))
                continue
            lang_cls = f" language-{html.escape(language)}" if language else ""
            highlighted = highlight_code(chr(10).join(code_lines), language, semantic=semantic)
            if semantic:
                # Plain <pre><code>: stylesheet themes style real code blocks and
                # the paired code theme colours the .hljs-* token spans; newlines
                # stay literal under white-space:pre.
                blocks.append(f'<pre><code class="hljs{lang_cls}">{highlighted}</code></pre>')
            else:
                # code carries "hljs code__pre" so both bare ".hljs" and compound
                # ".hljs.code__pre" highlightTheme variants match; language-* kept for info.
                blocks.append(f'<pre class="custom"><code class="hljs code__pre{lang_cls}">{highlighted}</code></pre>')
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            blocks.append(render_heading(level, heading.group(2).strip(), semantic=semantic))
            index += 1
            continue

        if re.match(r"^[-*_]\s*([-*_]\s*){2,}$", stripped):
            flush_paragraph()
            blocks.append("<hr>")
            index += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip().lstrip(">").strip())
                index += 1
            blocks.append(f"<blockquote>{render_markdown_fallback(chr(10).join(quote_lines), flavor)}</blockquote>")
            continue

        if is_table_start(lines, index):
            flush_paragraph()
            table_lines: list[str] = [lines[index], lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                table_lines.append(lines[index])
                index += 1
            blocks.append(render_table(table_lines, semantic=semantic))
            continue

        # Semantic flavor uses bare <li>Item</li>; MDNice flavor wraps in <section>
        # so themes targeting "li section" attach.
        item_wrap = (lambda inner: inner) if semantic else (lambda inner: f"<section>{inner}</section>")

        ul_match = re.match(r"^\s*[-*+]\s+(.+)$", line)
        if ul_match:
            flush_paragraph()
            items: list[str] = []
            while index < len(lines):
                item_match = re.match(r"^\s*[-*+]\s+(.+)$", lines[index])
                if not item_match:
                    break
                items.append(f"<li>{item_wrap(inline_markup(item_match.group(1)))}</li>")
                index += 1
            blocks.append(f"<ul>{''.join(items)}</ul>")
            continue

        ol_match = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if ol_match:
            flush_paragraph()
            items = []
            while index < len(lines):
                item_match = re.match(r"^\s*\d+\.\s+(.+)$", lines[index])
                if not item_match:
                    break
                items.append(f"<li>{item_wrap(inline_markup(item_match.group(1)))}</li>")
                index += 1
            blocks.append(f"<ol>{''.join(items)}</ol>")
            continue

        paragraph.append(line)
        index += 1

    flush_paragraph()
    return "\n".join(blocks)


def render_heading(level: int, text: str, semantic: bool = False) -> str:
    content = inline_markup(text)
    if semantic:
        return f"<h{level}>{content}</h{level}>"
    return (
        f"<h{level}>"
        '<span class="prefix"></span>'
        f'<span class="content">{content}</span>'
        '<span class="suffix"></span>'
        f"</h{level}>"
    )


# pygments token type -> highlight.js class. The MDNice code themes
# (highlightTheme) target highlight.js classes (.hljs-keyword, ...), so we map
# pygments tokens onto them by string prefix (most specific first). Two engines
# classify tokens differently, so this is a close semantic approximation.
HLJS_CLASS_RULES = [
    ("Token.Comment.Special", "hljs-doctag"),
    ("Token.Comment.Preproc", "hljs-meta"),
    ("Token.Comment", "hljs-comment"),
    ("Token.Keyword.Constant", "hljs-literal"),
    ("Token.Keyword.Type", "hljs-type"),
    ("Token.Keyword", "hljs-keyword"),
    ("Token.Operator.Word", "hljs-keyword"),
    ("Token.Literal.String.Regex", "hljs-regexp"),
    ("Token.Literal.String.Symbol", "hljs-symbol"),
    ("Token.Literal.String", "hljs-string"),
    ("Token.Literal.Number", "hljs-number"),
    ("Token.Name.Builtin.Pseudo", "hljs-variable"),
    ("Token.Name.Builtin", "hljs-built_in"),
    ("Token.Name.Function", "hljs-title"),
    ("Token.Name.Class", "hljs-title"),
    ("Token.Name.Decorator", "hljs-meta"),
    ("Token.Name.Tag", "hljs-name"),
    ("Token.Name.Attribute", "hljs-attr"),
    ("Token.Name.Variable", "hljs-variable"),
    ("Token.Name.Constant", "hljs-variable"),
    ("Token.Name.Label", "hljs-symbol"),
    ("Token.Generic.Deleted", "hljs-deletion"),
    ("Token.Generic.Inserted", "hljs-addition"),
    ("Token.Generic.Subheading", "hljs-section"),
    ("Token.Generic.Heading", "hljs-section"),
    ("Token.Generic.Strong", "hljs-strong"),
    ("Token.Generic.Emph", "hljs-emphasis"),
]


def hljs_class_for(ttype: Any) -> str | None:
    label = str(ttype)
    for prefix, cls in HLJS_CLASS_RULES:
        if label.startswith(prefix):
            return cls
    return None


def code_escape(text: str, semantic: bool = False) -> str:
    # MDNice mode: newline -> <br>, space -> &nbsp;. MDNice themes set
    # display:-webkit-box on <code>, where a bare "\n" would not wrap, so the
    # markup must carry explicit line breaks (and nbsp to preserve indentation).
    # Semantic mode: keep literal newlines/spaces; stylesheet themes render code
    # under white-space:pre, so real text copies cleanly and selects correctly.
    text = html.escape(text)
    if semantic:
        return text
    text = text.replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
    text = text.replace(" ", "&nbsp;")
    text = text.replace("\n", "<br>")
    return text


def highlight_code(code: str, language: str, semantic: bool = False) -> str:
    code = code.rstrip("\n")
    try:
        from pygments.lexers import TextLexer, get_lexer_by_name  # type: ignore

        try:
            lexer = get_lexer_by_name(language) if language else TextLexer()
        except Exception:
            lexer = TextLexer()
        parts: list[str] = []
        for ttype, value in lexer.get_tokens(code):
            if not value:
                continue
            cls = hljs_class_for(ttype)
            esc = code_escape(value, semantic=semantic)
            parts.append(f'<span class="{cls}">{esc}</span>' if cls else esc)
        result = "".join(parts)
        if semantic:
            if result.endswith("\n"):  # get_tokens appends a trailing newline
                result = result[:-1]
        elif result.endswith("<br>"):
            result = result[:-4]
        return result
    except Exception:
        return code_escape(code, semantic=semantic)


def render_mermaid_block(source: str) -> str:
    # mermaid.js renders the textContent of a `.mermaid` element into SVG on load.
    # HTML-escape the source so mermaid syntax such as A["x<br/>y"] survives as
    # literal text instead of being parsed into real DOM tags. Wrap in a marker
    # <section> so article_document can lift it out before theme inlining (the
    # inliner must not touch diagram source) and restore it afterwards.
    escaped = html.escape(source.strip("\n"))
    return (
        '<section class="mermaid-figure" data-mermaid="1" '
        'style="text-align:center;margin:16px 0;overflow-x:auto;">'
        f'<div class="mermaid">{escaped}</div>'
        "</section>"
    )


# --- Code-syntax themes -----------------------------------------------------
# The cached layout themes style only inline `code`; the code BLOCK (pre.custom)
# carries no background or token colors (highlight.js themes are a separate
# dimension in MDNice). We reproduce a set of standard highlight.js themes and
# pair each layout theme with a fitting one, so different layout themes get
# different — but coherent — code blocks. A theme is expressed as a small role ->
# color map and expanded into #nice-scoped CSS that is appended after the layout
# CSS, so the inliner turns it into inline styles (surviving WeChat/Zhihu paste)
# and its high-specificity rules outrank the layout theme's plain pre/code rules.

# highlight.js token class -> semantic colour role.
HLJS_ROLE_CLASSES: dict[str, list[str]] = {
    "comment": ["hljs-comment", "hljs-quote"],
    "keyword": ["hljs-doctag", "hljs-keyword", "hljs-formula"],
    "name": ["hljs-section", "hljs-name", "hljs-selector-tag", "hljs-deletion", "hljs-subst"],
    "literal": ["hljs-literal"],
    "string": ["hljs-string", "hljs-regexp", "hljs-addition", "hljs-attribute", "hljs-meta"],
    "attr": [
        "hljs-attr", "hljs-variable", "hljs-template-variable", "hljs-type",
        "hljs-selector-class", "hljs-selector-attr", "hljs-selector-pseudo", "hljs-number",
    ],
    "symbol": ["hljs-symbol", "hljs-bullet", "hljs-link", "hljs-selector-id", "hljs-title"],
    "builtin": ["hljs-built_in"],
}

# role colours per code theme (bg = container background, base = default text).
CODE_THEMES: dict[str, dict[str, str]] = {
    "atom-one-dark": {"bg": "#282c34", "base": "#abb2bf", "comment": "#5c6370", "keyword": "#c678dd", "name": "#e06c75", "literal": "#56b6c2", "string": "#98c379", "attr": "#d19a66", "symbol": "#61aeee", "builtin": "#e6c07b"},
    "atom-one-light": {"bg": "#fafafa", "base": "#383a42", "comment": "#a0a1a7", "keyword": "#a626a4", "name": "#e45649", "literal": "#0184bb", "string": "#50a14f", "attr": "#986801", "symbol": "#4078f2", "builtin": "#c18401"},
    "github": {"bg": "#f6f8fa", "base": "#24292e", "comment": "#6a737d", "keyword": "#d73a49", "name": "#22863a", "literal": "#005cc5", "string": "#032f62", "attr": "#005cc5", "symbol": "#6f42c1", "builtin": "#005cc5"},
    "vs2015": {"bg": "#1e1e1e", "base": "#dcdcdc", "comment": "#57a64a", "keyword": "#569cd6", "name": "#569cd6", "literal": "#569cd6", "string": "#d69d85", "attr": "#9cdcfe", "symbol": "#d7ba7d", "builtin": "#4ec9b0"},
    "monokai": {"bg": "#272822", "base": "#f8f8f2", "comment": "#75715e", "keyword": "#f92672", "name": "#f92672", "literal": "#ae81ff", "string": "#e6db74", "attr": "#fd971f", "symbol": "#66d9ef", "builtin": "#a6e22e"},
    "dracula": {"bg": "#282a36", "base": "#f8f8f2", "comment": "#6272a4", "keyword": "#ff79c6", "name": "#ff79c6", "literal": "#bd93f9", "string": "#f1fa8c", "attr": "#bd93f9", "symbol": "#8be9fd", "builtin": "#50fa7b"},
}
DEFAULT_CODE_THEME = "atom-one-dark"
MERMAID_THEMES = ("default", "dark", "forest", "neutral", "base")
DEFAULT_MERMAID_THEME = "default"


def build_code_theme_css(key: str) -> str:
    theme = CODE_THEMES.get(key) or CODE_THEMES[DEFAULT_CODE_THEME]
    lines = [
        f"#nice pre.custom {{ background-color: {theme['bg']}; border-radius: 5px; padding-top: 16px; padding-bottom: 16px; padding-left: 16px; padding-right: 16px; overflow-x: auto; }}",
        f"#nice pre.custom code.hljs {{ background: transparent; color: {theme['base']}; display: block; white-space: pre; padding: 0; font-size: 13px; line-height: 22px; }}",
    ]
    for role, classes in HLJS_ROLE_CLASSES.items():
        color = theme.get(role)
        if not color:
            continue
        selector = ", ".join(f"#nice pre.custom code.hljs .{cls}" for cls in classes)
        extra = " font-style: italic;" if role == "comment" else ""
        lines.append(f"{selector} {{ color: {color};{extra} }}")
    lines.append("#nice pre.custom code.hljs .hljs-class .hljs-title { color: " + theme["builtin"] + "; }")
    lines.append("#nice pre.custom code.hljs .hljs-emphasis { font-style: italic; }")
    lines.append("#nice pre.custom code.hljs .hljs-strong { font-weight: bold; }")
    return "\n".join(lines)


def build_code_theme_css_semantic(key: str, prefix: str) -> str:
    """Code-block CSS for stylesheet (standalone) themes, scoped under `prefix`
    (the theme's wrapper class selector, or `body` for classless themes).

    Stylesheet themes either don't colour syntax tokens at all (classless) or use
    a non-hljs class set (GitHub `.pl-*`), so the paired code theme owns the block:
    background + base text + `.hljs-*` token colours. It is appended after the
    layout CSS at equal-or-higher specificity, so it wins the cascade and gives
    every theme a coherent, readable, highlighted code block."""
    theme = CODE_THEMES.get(key) or CODE_THEMES[DEFAULT_CODE_THEME]
    p = prefix
    lines = [
        f"{p} pre {{ background-color: {theme['bg']}; border-radius: 6px; padding: 14px 16px; overflow-x: auto; }}",
        f"{p} pre code.hljs {{ display: block; background: transparent; color: {theme['base']}; "
        "white-space: pre; padding: 0; border: 0; font-size: 13px; line-height: 1.6; "
        'font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }',
    ]
    for role, classes in HLJS_ROLE_CLASSES.items():
        color = theme.get(role)
        if not color:
            continue
        selector = ", ".join(f"{p} pre code.hljs .{cls}" for cls in classes)
        extra = " font-style: italic;" if role == "comment" else ""
        lines.append(f"{selector} {{ color: {color};{extra} }}")
    lines.append(f"{p} pre code.hljs .hljs-class .hljs-title {{ color: {theme['builtin']}; }}")
    lines.append(f"{p} pre code.hljs .hljs-emphasis {{ font-style: italic; }}")
    lines.append(f"{p} pre code.hljs .hljs-strong {{ font-weight: bold; }}")
    return "\n".join(lines)


# Each layout theme -> (code theme, mermaid theme), chosen to match the layout's
# accent/mood. Unmapped themes fall back to the default pairing.
THEME_STYLE_MAP: dict[str, tuple[str, str]] = {
    # warm / coral / red accents
    "极客黑": ("atom-one-dark", "default"),
    "橙心": ("github", "default"),
    "红绯": ("monokai", "default"),
    "橙蓝风": ("monokai", "default"),
    "萌粉": ("github", "default"),
    "Pornhub黄": ("monokai", "dark"),
    "WeFormat": ("monokai", "default"),
    "简": ("github", "neutral"),
    "锤子便签主题第2版": ("atom-one-light", "neutral"),
    # blue / tech accents
    "科技蓝": ("vs2015", "dark"),
    "全栈蓝": ("vs2015", "dark"),
    "蓝莹": ("vs2015", "dark"),
    "灵动蓝": ("vs2015", "dark"),
    "前端之巅同款": ("vs2015", "default"),
    "重影": ("atom-one-dark", "default"),
    "雁栖湖": ("atom-one-dark", "default"),
    "柠檬黄": ("atom-one-dark", "default"),
    "极简黑": ("github", "neutral"),
    "奇点": ("atom-one-dark", "default"),
    "山吹": ("atom-one-dark", "default"),
    "WeFormat ": ("monokai", "default"),
    # green accents
    "萌绿": ("atom-one-dark", "forest"),
    "绿意": ("atom-one-dark", "forest"),
    "嫩青": ("atom-one-dark", "forest"),
    "兰青": ("atom-one-dark", "forest"),
    "草原绿": ("atom-one-dark", "forest"),
    # purple accents
    "姹紫": ("dracula", "dark"),
    "蔷薇紫": ("dracula", "dark"),
    "凝夜紫": ("dracula", "dark"),
    "丘比特忙": ("dracula", "default"),
    # dark canvas
    "Obsidian": ("dracula", "dark"),
}


def resolve_theme_styles(
    theme: dict[str, Any],
    code_override: str | None = None,
    mermaid_override: str | None = None,
) -> tuple[str, str]:
    name = clean_text(str(theme.get("name") or "")).strip()
    code_key, mermaid_theme = THEME_STYLE_MAP.get(name, (DEFAULT_CODE_THEME, DEFAULT_MERMAID_THEME))
    if code_override:
        code_key = code_override
    if mermaid_override:
        mermaid_theme = mermaid_override
    if code_key not in CODE_THEMES:
        code_key = DEFAULT_CODE_THEME
    if mermaid_theme not in MERMAID_THEMES:
        mermaid_theme = DEFAULT_MERMAID_THEME
    return code_key, mermaid_theme


def resolve_stylesheet_styles(
    theme: dict[str, Any],
    code_override: str | None = None,
    mermaid_override: str | None = None,
) -> tuple[str, str]:
    """Code/mermaid pairing for stylesheet themes: catalog metadata first, then a
    sensible default keyed by the theme's light/dark appearance."""
    appearance = str(theme.get("appearance") or "light").lower()
    default_code = "atom-one-dark" if appearance == "dark" else "github"
    code_key = code_override or str(theme.get("codeTheme") or default_code)
    mermaid_theme = mermaid_override or str(
        theme.get("mermaidTheme") or ("dark" if appearance == "dark" else DEFAULT_MERMAID_THEME)
    )
    if code_key not in CODE_THEMES:
        code_key = default_code if default_code in CODE_THEMES else DEFAULT_CODE_THEME
    if mermaid_theme not in MERMAID_THEMES:
        mermaid_theme = DEFAULT_MERMAID_THEME
    return code_key, mermaid_theme


def mermaid_runtime(mermaid_theme: str) -> str:
    # Loaded from a CDN only when a document actually contains mermaid diagrams.
    return (
        '<script type="module">\n'
        "import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';\n"
        f"mermaid.initialize({{ startOnLoad: true, securityLevel: 'loose', theme: '{mermaid_theme}' }});\n"
        "</script>"
    )


def extract_mermaid_blocks(body_html: str) -> tuple[str, list[str]]:
    """Replace each mermaid <section> with a plain-text token so the theme inliner
    cannot mutate diagram source. Returns (tokenized_html, ordered_block_list)."""
    blocks: list[str] = []

    def stash(match: re.Match[str]) -> str:
        blocks.append(match.group(0))
        return f"@@MERMAIDBLOCK{len(blocks) - 1}@@"

    pattern = re.compile(
        r'<section class="mermaid-figure" data-mermaid="1".*?</section>', re.S
    )
    return pattern.sub(stash, body_html), blocks


def inline_markup(text: str) -> str:
    code_spans: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        code_spans.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"@@CODE{len(code_spans) - 1}@@"

    text = re.sub(r"`([^`]+)`", stash_code, text)
    text = html.escape(text)
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)",
        lambda m: f'<img src="{m.group(2)}" alt="{m.group(1)}">',
        text,
    )
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)",
        lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>',
        text,
    )
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"<em>\1</em>", text)
    for index, code in enumerate(code_spans):
        text = text.replace(f"@@CODE{index}@@", code)
    return text


def is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return "|" in lines[index] and bool(re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", lines[index + 1]))


def split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def render_table(lines: list[str], semantic: bool = False) -> str:
    headers = split_table_row(lines[0])
    body_rows = [split_table_row(line) for line in lines[2:]]
    head = "".join(f"<th>{inline_markup(cell)}</th>" for cell in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{inline_markup(cell)}</td>" for cell in row) + "</tr>" for row in body_rows
    )
    table = f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    if semantic:
        # Stylesheet themes style <table>/<th>/<td> directly; wrap only in a
        # style-only scroll box (no class) so wide tables don't break layout.
        return f'<div style="overflow-x:auto;">{table}</div>'
    return f'<section class="table-container">{table}</section>'


@dataclass
class HtmlNode:
    tag: str | None = None
    attrs: list[tuple[str, str | None]] = field(default_factory=list)
    children: list["HtmlNode | str"] = field(default_factory=list)
    parent: "HtmlNode | None" = None
    styles: dict[str, str] = field(default_factory=dict)
    style_weights: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class SimpleSelector:
    tag: str | None = None
    node_id: str | None = None
    classes: tuple[str, ...] = ()
    pseudo: tuple[str, str | None] = ()


@dataclass(frozen=True)
class SelectorPart:
    combinator: str
    selector: SimpleSelector


@dataclass
class CssRule:
    selectors: list[str]
    declarations: list[tuple[str, str]]


class FragmentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.root = HtmlNode()
        self.stack: list[HtmlNode] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = HtmlNode(tag=tag.lower(), attrs=list(attrs), parent=self.stack[-1])
        self.stack[-1].children.append(node)
        if node.tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = HtmlNode(tag=tag.lower(), attrs=list(attrs), parent=self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)

    def handle_entityref(self, name: str) -> None:
        self.stack[-1].children.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.stack[-1].children.append(f"&#{name};")


def parse_html_fragment(fragment: str) -> HtmlNode:
    parser = FragmentParser()
    parser.feed(fragment)
    parser.close()
    return parser.root


def serialize_html_fragment(root: HtmlNode) -> str:
    return "".join(serialize_html_node(child) for child in root.children)


def serialize_html_node(node: HtmlNode | str) -> str:
    if isinstance(node, str):
        return node
    if node.tag is None:
        return serialize_html_fragment(node)

    attrs = merged_attrs(node)
    attr_html = "".join(
        f" {html.escape(name, quote=True)}" if value is None else f' {html.escape(name, quote=True)}="{html.escape(value, quote=True)}"'
        for name, value in attrs
    )
    if node.tag in VOID_TAGS:
        return f"<{node.tag}{attr_html}>"
    content = "".join(serialize_html_node(child) for child in node.children)
    return f"<{node.tag}{attr_html}>{content}</{node.tag}>"


def merged_attrs(node: HtmlNode) -> list[tuple[str, str | None]]:
    attrs: list[tuple[str, str | None]] = []
    existing_style = ""
    for name, value in node.attrs:
        if name.lower() == "style":
            existing_style = value or ""
        else:
            attrs.append((name, value))

    style = style_text(parse_declarations(existing_style) + list(node.styles.items()))
    if style:
        attrs.append(("style", style))
    return attrs


def inline_theme_article(body_html: str, css: str) -> str:
    root = parse_html_fragment(f'<article id="nice">{body_html}</article>')
    rules = parse_css_rules(css)
    for order, rule in enumerate(rules):
        for selector in rule.selectors:
            base_selector, pseudo = extract_terminal_pseudo(selector)
            parts = parse_selector(base_selector)
            if parts is None:
                continue
            specificity = selector_specificity(parts, pseudo)
            weight = (*specificity, order)
            for node in iter_elements(root):
                if selector_matches(node, parts):
                    target = pseudo_node(node, pseudo) if pseudo else node
                    declarations = pseudo_declarations(rule.declarations, target) if pseudo else rule.declarations
                    merge_inline_styles(target, declarations, weight)
    return serialize_html_fragment(root)


def parse_css_rules(css: str) -> list[CssRule]:
    clean_css = strip_css_comments(css)
    rules: list[CssRule] = []
    index = 0
    while index < len(clean_css):
        selector_start = index
        brace = clean_css.find("{", index)
        if brace == -1:
            break
        selector_text = clean_css[selector_start:brace].strip()
        end = find_matching_brace(clean_css, brace)
        if end == -1:
            break
        body = clean_css[brace + 1 : end]
        index = end + 1
        if not selector_text or selector_text.startswith("@"):
            continue
        declarations = parse_declarations(body)
        if not declarations:
            continue
        selectors = [selector.strip() for selector in split_selector_list(selector_text) if selector.strip()]
        if selectors:
            rules.append(CssRule(selectors=selectors, declarations=declarations))
    return rules


def strip_css_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def find_matching_brace(css: str, start: int) -> int:
    depth = 0
    quote = ""
    escape = False
    for index in range(start, len(css)):
        char = css[index]
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def split_selector_list(selector_text: str) -> list[str]:
    selectors: list[str] = []
    start = 0
    depth = 0
    quote = ""
    escape = False
    for index, char in enumerate(selector_text):
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            selectors.append(selector_text[start:index])
            start = index + 1
    selectors.append(selector_text[start:])
    return selectors


def parse_declarations(style_text_value: str) -> list[tuple[str, str]]:
    declarations: list[tuple[str, str]] = []
    for item in split_declarations(style_text_value):
        if ":" not in item:
            continue
        name, value = item.split(":", 1)
        name = name.strip().lower()
        value = value.strip()
        if name and value:
            declarations.append((name, value))
    return declarations


def split_declarations(declaration_text: str) -> list[str]:
    declarations: list[str] = []
    start = 0
    depth = 0
    quote = ""
    escape = False
    for index, char in enumerate(declaration_text):
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == ";" and depth == 0:
            declarations.append(declaration_text[start:index])
            start = index + 1
    declarations.append(declaration_text[start:])
    return declarations


def style_text(declarations: list[tuple[str, str]]) -> str:
    merged: dict[str, str] = {}
    for name, value in declarations:
        if name and value:
            merged[name] = value
    return "; ".join(f"{name}: {value}" for name, value in merged.items())


def merge_inline_styles(
    node: HtmlNode,
    declarations: list[tuple[str, str]],
    weight: tuple[int, int, int, int],
) -> None:
    for name, value in declarations:
        current = node.style_weights.get(name)
        if name and value and (current is None or weight >= current):
            node.styles[name] = value
            node.style_weights[name] = weight


def iter_elements(root: HtmlNode) -> list[HtmlNode]:
    nodes: list[HtmlNode] = []

    def visit(node: HtmlNode) -> None:
        if node.tag is not None:
            nodes.append(node)
        for child in node.children:
            if isinstance(child, HtmlNode):
                visit(child)

    visit(root)
    return nodes


def parse_selector(selector: str) -> list[SelectorPart] | None:
    selector = normalize_selector(selector)
    if not selector:
        return None
    tokens = selector_tokens(selector)
    if not tokens:
        return None

    parts: list[SelectorPart] = []
    combinator = " "
    expect_selector = True
    for token in tokens:
        if token in (">", "+"):
            if expect_selector:
                return None
            combinator = token
            expect_selector = True
            continue
        simple = parse_simple_selector(token)
        if simple is None:
            return None
        parts.append(SelectorPart(combinator=combinator, selector=simple))
        combinator = " "
        expect_selector = False
    return parts if parts and not expect_selector else None


def normalize_selector(selector: str) -> str:
    selector = selector.strip()
    selector = re.sub(r"::", ":", selector)
    selector = re.sub(r"\s+", " ", selector)
    return selector


def selector_tokens(selector: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    quote = ""
    escape = False
    pending_space = False

    for char in selector:
        if quote:
            current.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            current.append(char)
            quote = char
        elif char == "(":
            current.append(char)
            depth += 1
        elif char == ")":
            current.append(char)
            if depth:
                depth -= 1
        elif depth == 0 and char in (">", "+"):
            if current:
                tokens.append("".join(current).strip())
                current = []
            tokens.append(char)
            pending_space = False
        elif depth == 0 and char.isspace():
            if current:
                tokens.append("".join(current).strip())
                current = []
                pending_space = True
        else:
            if pending_space and tokens and tokens[-1] not in (">", "+"):
                tokens.append(" ")
            pending_space = False
            current.append(char)

    if current:
        tokens.append("".join(current).strip())
    return [token for token in tokens if token != " "]


def parse_simple_selector(token: str) -> SimpleSelector | None:
    token = token.strip()
    if not token or any(char in token for char in ("[", "~", "*")):
        return None
    if ":" in token:
        allowed = re.compile(r":(nth-of-type\((?:n|2n|2n[+-]1|odd|even|\d+)\)|first-child|last-child)")
        reduced = allowed.sub("", token)
        if ":" in reduced:
            return None

    pseudo: list[tuple[str, str | None]] = []

    def take_pseudo(match: re.Match[str]) -> str:
        name = match.group(1)
        arg = match.group(2) if match.lastindex and match.lastindex >= 2 else None
        pseudo.append((name, arg))
        return ""

    token = re.sub(r":(nth-of-type)\(([^)]*)\)", take_pseudo, token)
    token = re.sub(r":(first-child|last-child)\b", take_pseudo, token)

    tag_match = re.match(r"^[A-Za-z][A-Za-z0-9_-]*", token)
    tag = tag_match.group(0).lower() if tag_match else None
    rest = token[len(tag_match.group(0)) :] if tag_match else token
    node_id: str | None = None
    classes: list[str] = []
    while rest:
        if rest.startswith("#"):
            match = re.match(r"#([A-Za-z0-9_-]+)", rest)
            if not match:
                return None
            node_id = match.group(1)
            rest = rest[len(match.group(0)) :]
        elif rest.startswith("."):
            match = re.match(r"\.([A-Za-z0-9_-]+)", rest)
            if not match:
                return None
            classes.append(match.group(1))
            rest = rest[len(match.group(0)) :]
        else:
            return None
    return SimpleSelector(tag=tag, node_id=node_id, classes=tuple(classes), pseudo=tuple(pseudo))


def extract_terminal_pseudo(selector: str) -> tuple[str, str | None]:
    match = re.search(r":{1,2}(before|after)\s*$", selector, flags=re.I)
    if not match:
        return selector, None
    return selector[: match.start()].strip(), match.group(1).lower()


def selector_specificity(parts: list[SelectorPart], pseudo: str | None = None) -> tuple[int, int, int]:
    ids = 0
    classes = 0
    tags = 1 if pseudo else 0
    for part in parts:
        selector = part.selector
        if selector.node_id:
            ids += 1
        classes += len(selector.classes) + len(selector.pseudo)
        if selector.tag:
            tags += 1
    return ids, classes, tags


def pseudo_node(node: HtmlNode, pseudo: str | None) -> HtmlNode:
    if pseudo not in {"before", "after"}:
        return node
    for child in node.children:
        if isinstance(child, HtmlNode) and attr_value(child, "data-mdnice-pseudo") == pseudo:
            return child

    child = HtmlNode(tag="span", attrs=[("data-mdnice-pseudo", pseudo)], parent=node)
    if pseudo == "before":
        node.children.insert(0, child)
    else:
        node.children.append(child)
    return child


def pseudo_declarations(declarations: list[tuple[str, str]], node: HtmlNode) -> list[tuple[str, str]]:
    styles: list[tuple[str, str]] = []
    for name, value in declarations:
        if name == "content":
            set_pseudo_content(node, value)
        else:
            styles.append((name, value))
    return styles


def set_pseudo_content(node: HtmlNode, value: str) -> None:
    content = css_content_text(value)
    node.children = [] if content is None else [html.escape(content)]


def css_content_text(value: str) -> str | None:
    value = value.strip()
    if value.lower() in {"normal", "none", "unset", "initial"}:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    if value == "":
        return ""
    value = value.replace(r"\"", '"').replace(r"\'", "'").replace(r"\\", "\\")
    value = re.sub(r"\\a\s*", "\n", value, flags=re.I)
    return value


def selector_matches(node: HtmlNode, parts: list[SelectorPart]) -> bool:
    return match_part(node, parts, len(parts) - 1)


def match_part(node: HtmlNode | None, parts: list[SelectorPart], index: int) -> bool:
    if node is None or node.tag is None:
        return False
    part = parts[index]
    if not simple_selector_matches(node, part.selector):
        return False
    if index == 0:
        return True

    combinator = part.combinator
    if combinator == ">":
        return match_part(element_parent(node), parts, index - 1)
    if combinator == "+":
        return match_part(previous_element_sibling(node), parts, index - 1)

    ancestor = element_parent(node)
    while ancestor is not None:
        if match_part(ancestor, parts, index - 1):
            return True
        ancestor = element_parent(ancestor)
    return False


def simple_selector_matches(node: HtmlNode, selector: SimpleSelector) -> bool:
    if selector.tag and node.tag != selector.tag:
        return False
    if selector.node_id and attr_value(node, "id") != selector.node_id:
        return False
    classes = set((attr_value(node, "class") or "").split())
    if any(class_name not in classes for class_name in selector.classes):
        return False
    for name, arg in selector.pseudo:
        if name == "nth-of-type":
            if not nth_of_type_matches(node, arg or ""):
                return False
        elif name == "first-child":
            if previous_element_sibling(node) is not None:
                return False
        elif name == "last-child":
            if next_element_sibling(node) is not None:
                return False
        else:
            return False
    return True


def attr_value(node: HtmlNode, name: str) -> str | None:
    wanted = name.lower()
    for attr_name, value in node.attrs:
        if attr_name.lower() == wanted:
            return value
    return None


def element_parent(node: HtmlNode) -> HtmlNode | None:
    parent = node.parent
    return parent if parent is not None and parent.tag is not None else None


def element_siblings(node: HtmlNode) -> list[HtmlNode]:
    if node.parent is None:
        return []
    return [child for child in node.parent.children if isinstance(child, HtmlNode) and child.tag is not None]


def _index_by_identity(seq: list, node: HtmlNode) -> int:
    # Identity lookup ("is"), never "==". HtmlNodes form parent<->children
    # cycles; using list.index() (which uses ==) risks deep recursion.
    for i, child in enumerate(seq):
        if child is node:
            return i
    return -1


def previous_element_sibling(node: HtmlNode) -> HtmlNode | None:
    siblings = element_siblings(node)
    index = _index_by_identity(siblings, node)
    return siblings[index - 1] if index > 0 else None


def next_element_sibling(node: HtmlNode) -> HtmlNode | None:
    siblings = element_siblings(node)
    index = _index_by_identity(siblings, node)
    return siblings[index + 1] if 0 <= index and index + 1 < len(siblings) else None


def nth_of_type_matches(node: HtmlNode, expression: str) -> bool:
    if node.parent is None:
        return False
    same_type = [
        child
        for child in node.parent.children
        if isinstance(child, HtmlNode) and child.tag == node.tag
    ]
    position = _index_by_identity(same_type, node)
    if position < 0:
        return False
    position += 1

    expression = expression.strip().lower().replace(" ", "")
    if expression in ("n", "1n"):
        return True
    if expression == "odd":
        return position % 2 == 1
    if expression == "even" or expression == "2n":
        return position % 2 == 0
    if expression in ("2n+1", "2n-1"):
        return position % 2 == 1
    if expression.isdigit():
        return position == int(expression)
    return False


# Page-level compatibility CSS for the #nice article DOM (reset, responsive,
# tables, code overflow). Shared by both MDNice output modes. Contains literal
# braces, so it is injected as a value (never re-parsed by f-strings).
NICE_BASE_CSS = """\
html, body { margin: 0; padding: 0; background: #fff; }
body { overflow-wrap: break-word; }
#nice { box-sizing: border-box; min-height: 100vh; margin: 0 auto; max-width: 760px; }
#nice img { max-width: 100%; height: auto; }
#nice pre { overflow-x: auto; }
#nice h1, #nice h2, #nice h3, #nice h4, #nice h5, #nice h6 { word-break: break-word; }
#nice h1 .content, #nice h2 .content, #nice h3 .content, #nice h4 .content, #nice h5 .content, #nice h6 .content { min-width: 0; }
#nice .table-container { overflow-x: auto; -webkit-overflow-scrolling: touch; }
#nice .table-container table { border-collapse: collapse; width: 100%; }
/* Layout themes apply `display:-webkit-box` to <code>; the paired code theme
   forces `display:block; white-space:pre`; these are a non-inline safety net. */
#nice pre.custom { overflow-x: auto; }
#nice pre.custom code { white-space: pre; }
"""


FOOTNOTE_LINK_RE = re.compile(r'<a\s+href="([^"]*)">(.*?)</a>', re.S)
DEFAULT_ACCENT_COLOR = "#1e6bb8"


def _strip_tags(fragment: str) -> str:
    return re.sub(r"<[^>]+>", "", fragment)


def theme_accent_color(theme: dict[str, Any]) -> str:
    """Best-effort accent colour for a theme, used to tint footnote numbers so the
    bottom reference list matches the in-body markers. Prefer the theme's own
    `.footnote-ref` colour (exactly what tints the body superscript), then the
    inline-code colour (`#nice p code`); for stylesheet themes fall back to a link
    colour, then appearance."""
    css = str(theme.get("styleCss") or "")
    if css:
        for pattern in (r"\.footnote-ref\b[^{]*\{([^}]*)\}", r"#nice\s+p\s+code\b[^{]*\{([^}]*)\}"):
            block = re.search(pattern, css)
            if block:
                color = re.search(r"(?<![-\w])color\s*:\s*([^;]+)", block.group(1))
                if color:
                    return color.group(1).strip()
    if str(theme.get("engine")) == "stylesheet":
        try:
            pcss = pack_theme_css(theme)
        except Exception:
            pcss = ""
        block = re.search(r"(?:^|[^.\w-])a\s*(?::link)?\s*\{([^}]*)\}", pcss)
        if block:
            color = re.search(r"(?<![-\w])color\s*:\s*([^;]+)", block.group(1))
            if color:
                return color.group(1).strip()
        if str(theme.get("appearance") or "").lower() == "dark":
            return "#58a6ff"
    return DEFAULT_ACCENT_COLOR


def convert_links_to_footnotes(body_html: str, accent: str = DEFAULT_ACCENT_COLOR) -> str:
    """Turn inline `<a href>` links into footnote references: keep the link text,
    append a superscript [N] marker, and collect the URLs into a reference list
    appended at the end of the article. Mirrors MDNice's footnote mode, which
    preserves URLs that WeChat/Zhihu strip from inline links. `accent` tints the
    [N] numbers so they match the theme. Returns the body unchanged with no links."""
    accent_css = html.escape(accent, quote=True)
    notes: list[tuple[str, str]] = []  # (label, url) in order of appearance

    def repl(match: re.Match[str]) -> str:
        # href/inner come from already-escaped generated HTML; normalize to a single
        # correct escaping (unescape -> escape) so e.g. "&amp;" is not shown literally.
        url = html.escape(html.unescape(match.group(1)))
        inner = match.group(2)
        label = html.escape(html.unescape(clean_text(_strip_tags(inner)))) or url
        notes.append((label, url))
        index = len(notes)
        return (
            f"{inner}"
            f'<sup class="footnote-ref" style="font-size: 75%; line-height: 0; '
            f'vertical-align: super; color: {accent_css};">[{index}]</sup>'
        )

    new_body = FOOTNOTE_LINK_RE.sub(repl, body_html)
    if not notes:
        return body_html

    items = []
    for index, (label, url) in enumerate(notes, start=1):
        # label/url are already HTML-escaped by repl().
        # No class on the number span: a class like `footnote-num` would let some
        # MDNice themes override its colour (to a muted grey), defeating the accent.
        items.append(
            '<p class="footnote-item" style="margin: 4px 0; font-size: 14px; '
            'line-height: 1.7; word-break: break-all; color: #888;">'
            f'<span style="color: {accent_css};">[{index}]</span> '
            f"{label}: {url}</p>"
        )
    footnotes_section = (
        '<section class="footnotes" style="margin-top: 32px;">'
        '<hr style="border: none; border-top: 1px solid #e0e0e0; margin: 0 0 12px;">'
        '<p class="footnotes-title" style="margin: 0 0 8px; font-size: 15px; '
        'font-weight: bold; color: #666;">引用链接</p>'
        + "".join(items)
        + "</section>"
    )
    return new_body + footnotes_section


def article_document(
    title: str,
    body_html: str,
    theme: dict[str, Any],
    code_theme: str | None = None,
    mermaid_theme: str | None = None,
) -> str:
    # Inline the layout CSS (styleCss) together with the per-theme code-highlight
    # CSS (highlightTheme, .hljs-* selectors under #nice). Most highlightTheme
    # rules live outside @media, so inline_theme_article reaches them.
    combined_css = str(theme.get("styleCss") or "")
    highlight_css = str(theme.get("highlightTheme") or "")
    if highlight_css:
        combined_css = f"{combined_css}\n{highlight_css}"
    # Pair this layout theme with a fitting code-syntax theme (overridable). It is
    # appended last so it wins over the layout theme's plain pre/code rules and
    # colours the (otherwise monochrome) .hljs-* token spans.
    code_key, mmd_theme = resolve_theme_styles(theme, code_theme, mermaid_theme)
    combined_css = f"{combined_css}\n{build_code_theme_css(code_key)}"
    # Lift mermaid diagrams out before inlining so the theme inliner never mutates
    # diagram source, then splice them back into the inlined article verbatim.
    tokenized_body, mermaid_blocks = extract_mermaid_blocks(body_html)
    article_html = inline_theme_article(tokenized_body, combined_css)
    for idx, block in enumerate(mermaid_blocks):
        article_html = article_html.replace(f"@@MERMAIDBLOCK{idx}@@", block)
    mermaid_runtime_html = mermaid_runtime(mmd_theme) if mermaid_blocks else ""
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
{mermaid_runtime_html}
<style>
{NICE_BASE_CSS}</style>
</head>
<body>
{article_html}
</body>
</html>"""


def mdnice_stylesheet_document(
    title: str,
    body_html: str,
    theme: dict[str, Any],
    code_theme: str | None = None,
    mermaid_theme: str | None = None,
) -> str:
    """Standalone-stylesheet output for an MDNice theme: keep the `#nice` DOM but
    emit the theme CSS (which is already `#nice`-scoped) in a `<style>` block
    instead of flattening it onto inline `style` attributes. Same theme, smaller
    and cleaner HTML, better for web/blog publishing — but it does NOT survive a
    WeChat/Zhihu paste (use the default inline mode for that)."""
    theme_css = str(theme.get("styleCss") or "")
    highlight_css = str(theme.get("highlightTheme") or "")
    if highlight_css:
        theme_css = f"{theme_css}\n{highlight_css}"
    code_key, mmd_theme = resolve_theme_styles(theme, code_theme, mermaid_theme)
    code_css = build_code_theme_css(code_key)
    mermaid_runtime_html = mermaid_runtime(mmd_theme) if 'data-mermaid="1"' in body_html else ""
    safe_title = html.escape(title)
    name = html.escape(clean_text(str(theme.get("name") or "")))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
{mermaid_runtime_html}
<style>
{NICE_BASE_CSS}</style>
<style>
/* ===== mdnice theme: {name} (standalone stylesheet) ===== */
{theme_css}
</style>
<style>
/* ===== paired code-highlight theme: {html.escape(code_key)} ===== */
{code_css}
</style>
</head>
<body>
<article id="nice">{body_html}</article>
</body>
</html>"""


def stylesheet_document(
    title: str,
    body_html: str,
    theme: dict[str, Any],
    code_theme: str | None = None,
    mermaid_theme: str | None = None,
) -> str:
    """Standalone HTML for a `stylesheet`-engine theme: emit the vendored theme CSS
    verbatim in a <style> block over semantic HTML (the inverse of the MDNice inline
    path). The content is placed in the theme's required wrapper class (e.g.
    `.markdown-body` for GitHub, `.heti`/`.typo` for those themes, or directly in
    <body> for classless themes), and a paired code-highlight theme is appended last."""
    theme_css = pack_theme_css(theme)
    wrapper_class = str(theme.get("wrapperClass") or "").strip()
    prefix = f".{wrapper_class}" if wrapper_class else "body"
    code_key, mmd_theme = resolve_stylesheet_styles(theme, code_theme, mermaid_theme)
    code_css = build_code_theme_css_semantic(code_key, prefix)

    has_mermaid = 'data-mermaid="1"' in body_html
    mermaid_runtime_html = mermaid_runtime(mmd_theme) if has_mermaid else ""
    appearance = str(theme.get("appearance") or "light").lower()
    page_bg = "#0d1117" if appearance == "dark" else "#ffffff"

    if wrapper_class:
        article = f'<article class="{html.escape(wrapper_class, quote=True)}">{body_html}</article>'
    else:
        article = body_html

    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
{mermaid_runtime_html}
<style>
/* base reset (kept minimal so the theme CSS below wins the cascade) */
html, body {{ margin: 0; padding: 0; }}
body {{ background: {page_bg}; overflow-wrap: break-word; }}
img {{ max-width: 100%; height: auto; }}
.mermaid svg {{ max-width: 100%; height: auto; }}
</style>
<style>
/* ===== theme: {html.escape(str(theme.get('name') or theme.get('slug') or ''))} ===== */
{theme_css}
</style>
<style>
/* ===== paired code-highlight theme: {html.escape(code_key)} ===== */
{code_css}
</style>
</head>
<body>
{article}
</body>
</html>"""


def build_theme_document(
    title: str,
    markdown_text: str,
    theme: dict[str, Any],
    code_theme: str | None = None,
    mermaid_theme: str | None = None,
    mode: str = "auto",
    footnotes: bool | None = None,
) -> str:
    """Dispatch a theme to the right engine and output mode.

    mode: "auto" (MDNice -> inline, hub -> stylesheet), "inline" (force inline),
    or "stylesheet" (force standalone <style> document). Every MDNice theme
    supports both inline and stylesheet output; hub themes are stylesheet-only and
    fall back to stylesheet if inline is requested.

    footnotes: None = auto (on for the inline-paste output, off for stylesheet
    documents where links stay clickable), True/False to force."""
    is_stylesheet_output = str(theme.get("engine")) == "stylesheet" or mode == "stylesheet"
    use_footnotes = footnotes if footnotes is not None else not is_stylesheet_output

    if str(theme.get("engine")) == "stylesheet":
        if mode == "inline":
            print(
                f"note: theme {theme.get('slug')!r} is stylesheet-only "
                "(variable/media-driven CSS can't be inlined); rendering as standalone stylesheet",
                file=sys.stderr,
            )
        body = render_markdown(markdown_text, flavor="semantic")
        if use_footnotes:
            body = convert_links_to_footnotes(body, theme_accent_color(theme))
        return stylesheet_document(title, body, theme, code_theme, mermaid_theme)
    # MDNice theme: inline by default; "stylesheet" emits the #nice CSS as a <style> block.
    body = render_markdown(markdown_text, flavor="mdnice")
    if use_footnotes:
        body = convert_links_to_footnotes(body, theme_accent_color(theme))
    if mode == "stylesheet":
        return mdnice_stylesheet_document(title, body, theme, code_theme, mermaid_theme)
    return article_document(title, body, theme, code_theme, mermaid_theme)


def build_preview_page(
    title: str,
    markdown_text: str,
    themes: list[dict[str, Any]],
    code_theme: str | None = None,
    mermaid_theme: str | None = None,
    mode: str = "auto",
    footnotes: bool | None = None,
) -> str:
    buttons: list[str] = []
    panels: list[str] = []
    for index, theme in enumerate(themes):
        theme_name = clean_text(str(theme.get("name") or f"Theme {theme.get('themeId')}"))
        theme_id = str(theme.get("themeId") or theme.get("slug") or "")
        active = index == 0
        button_class = "tab-button is-active" if active else "tab-button"
        panel_class = "preview-panel is-active" if active else "preview-panel"
        buttons.append(
            f'<button class="{button_class}" type="button" role="tab" '
            f'aria-selected="{str(active).lower()}" aria-controls="panel-{index}" '
            f'id="tab-{index}" data-target="panel-{index}">'
            f'<span class="theme-name">{html.escape(theme_name)}</span>'
            f'<span class="theme-id">#{html.escape(theme_id)}</span>'
            "</button>"
        )
        srcdoc = html.escape(
            build_theme_document(title, markdown_text, theme, code_theme, mermaid_theme, mode, footnotes),
            quote=True,
        )
        panels.append(
            f'<section class="{panel_class}" id="panel-{index}" role="tabpanel" '
            f'aria-labelledby="tab-{index}">'
            f'<iframe title="{html.escape(theme_name, quote=True)} preview" srcdoc="{srcdoc}"></iframe>'
            "</section>"
        )

    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title} - MDNice Preview</title>
<style>
:root {{
  color-scheme: light;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #f4f6f8;
  color: #17202a;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-height: 100vh; }}
.app {{ min-height: 100vh; display: grid; grid-template-rows: auto 1fr; }}
.topbar {{
  background: #ffffff;
  border-bottom: 1px solid #d8dee7;
  padding: 12px 16px 10px;
}}
.title {{
  margin: 0 0 10px;
  font-size: 16px;
  line-height: 1.4;
  font-weight: 650;
}}
.tabs {{
  display: flex;
  gap: 8px;
  overflow-x: auto;
  scrollbar-width: thin;
}}
.tab-button {{
  border: 1px solid #cbd5e1;
  background: #f8fafc;
  color: #1f2937;
  min-height: 36px;
  padding: 6px 10px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
  cursor: pointer;
  font-size: 13px;
}}
.tab-button:hover {{ background: #eef2f7; }}
.tab-button.is-active {{
  background: #1f6feb;
  border-color: #1f6feb;
  color: #ffffff;
}}
.theme-name {{ font-weight: 650; }}
.theme-id {{ opacity: 0.78; font-size: 12px; }}
.preview-shell {{ min-height: 0; padding: 12px; }}
.preview-panel {{
  display: none;
  width: 100%;
  height: calc(100vh - 91px);
  border: 1px solid #d8dee7;
  background: #ffffff;
  border-radius: 8px;
  overflow: hidden;
}}
.preview-panel.is-active {{ display: block; }}
iframe {{ width: 100%; height: 100%; border: 0; background: #ffffff; }}
@media (max-width: 640px) {{
  .topbar {{ padding: 10px; }}
  .preview-shell {{ padding: 8px; }}
  .preview-panel {{ height: calc(100vh - 88px); border-radius: 6px; }}
}}
</style>
</head>
<body>
<main class="app">
  <header class="topbar">
    <h1 class="title">{safe_title}</h1>
    <nav class="tabs" role="tablist" aria-label="Theme previews">
      {''.join(buttons)}
    </nav>
  </header>
  <div class="preview-shell">
    {''.join(panels)}
  </div>
</main>
<script>
const tabs = Array.from(document.querySelectorAll(".tab-button"));
const panels = Array.from(document.querySelectorAll(".preview-panel"));
for (const tab of tabs) {{
  tab.addEventListener("click", () => {{
    const target = tab.dataset.target;
    for (const item of tabs) {{
      const active = item === tab;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-selected", String(active));
    }}
    for (const panel of panels) {{
      panel.classList.toggle("is-active", panel.id === target);
    }}
  }});
}}
</script>
</body>
</html>"""


def ensure_theme_styles(args: argparse.Namespace, themes: list[dict[str, Any]], catalog_path: Path) -> None:
    # Stylesheet (hub) themes carry CSS in vendored files, not styleCss; only
    # MDNice inline themes need the styles endpoint.
    missing = [
        theme
        for theme in themes
        if str(theme.get("engine")) != "stylesheet" and not theme.get("styleCss")
    ]
    if not missing:
        return

    token = os.environ.get(args.token_env, "").strip()
    out_id = args.out_id or os.environ.get("MDNICE_OUT_ID", "").strip()
    if not args.refresh_missing_styles:
        names = ", ".join(f"{theme.get('themeId')}:{theme.get('name')}" for theme in missing)
        raise MdniceError(f"missing CSS for selected theme(s): {names}; rerun with --refresh-missing-styles")
    if not token:
        raise MdniceError(f"--refresh-missing-styles requires {args.token_env}")
    if not out_id:
        raise MdniceError("--refresh-missing-styles requires --out-id or MDNICE_OUT_ID")

    for theme in missing:
        theme.update(fetch_theme_style(int(theme["themeId"]), out_id, token, args.strict_tls))
        theme.pop("styleError", None)
        print(f"fetched missing CSS for {theme.get('themeId')} {theme.get('name')}", file=sys.stderr)
        time.sleep(args.delay)

    if args.cache_styles:
        catalog = load_catalog(catalog_path)
        catalog_dir = catalog_dir_for(catalog_path)
        by_id = {theme.get("themeId"): theme for theme in catalog.get("themes", []) if isinstance(theme, dict)}
        for theme in missing:
            original = by_id.get(theme.get("themeId"))
            if original is not None:
                # Persist the fetched CSS as a per-theme file; keep the catalog slim.
                original["styleCss"] = theme.get("styleCss")
                original["styleDataVersion"] = theme.get("styleDataVersion")
                original["styleFetchedAt"] = theme.get("styleFetchedAt")
                original.pop("styleError", None)
                externalize_theme_css(catalog_dir, original)
        catalog["styleCount"] = sum(1 for theme in catalog.get("themes", []) if theme_has_style(theme))
        catalog["fetchedAt"] = utc_now()
        write_catalog(catalog_path, catalog)


def render_command(args: argparse.Namespace) -> None:
    catalog = load_catalog(args.catalog)
    refs = split_theme_refs(args.themes)
    themes = resolve_themes(catalog, refs)
    # Load each MDNice theme's CSS from its per-theme file into memory so the rest
    # of the pipeline can stay unchanged; then check for any still-missing CSS.
    catalog_dir = catalog_dir_for(args.catalog)
    for theme in themes:
        hydrate_theme_css(theme, catalog_dir)
    ensure_theme_styles(args, themes, args.catalog)

    markdown_text = args.markdown.read_text(encoding="utf-8")
    title = args.title or derive_title(markdown_text, args.markdown)
    code_theme = getattr(args, "code_theme", None)
    mermaid_theme = getattr(args, "mermaid_theme", None)
    mode = getattr(args, "mode", "auto")
    footnotes = getattr(args, "footnotes", None)
    if len(themes) == 1 and not args.preview_tabs:
        output_html = build_theme_document(title, markdown_text, themes[0], code_theme, mermaid_theme, mode, footnotes)
        output_label = "publish HTML"
    else:
        output_html = build_preview_page(title, markdown_text, themes, code_theme, mermaid_theme, mode, footnotes)
        output_label = "tabbed preview"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output_html, encoding="utf-8")
    print(f"wrote {output_label}: {args.output}", file=sys.stderr)


def derive_title(markdown_text: str, path: Path) -> str:
    markdown_text = strip_frontmatter(markdown_text)
    for line in markdown_text.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return path.stem


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch-themes", help="refresh the cached MDNice theme catalog")
    fetch.add_argument("--output", type=Path, default=DEFAULT_CATALOG)
    fetch.add_argument("--page-size", type=int, default=100)
    fetch.add_argument("--include-styles", action="store_true")
    fetch.add_argument("--token-env", default="MDNICE_TOKEN")
    fetch.add_argument("--out-id")
    fetch.add_argument("--delay", type=float, default=0.15)
    fetch.add_argument("--strict-tls", action="store_true")
    fetch.set_defaults(func=build_catalog)

    list_cmd = subparsers.add_parser("list-themes", help="list cached themes")
    list_cmd.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    list_cmd.add_argument("--query")
    list_cmd.add_argument("--with-style-only", action="store_true")
    list_cmd.add_argument("--json", action="store_true")
    list_cmd.set_defaults(func=list_themes)

    split = subparsers.add_parser(
        "split-catalog",
        help="migrate an inline-styleCss catalog to one CSS file per theme (slim JSON)",
    )
    split.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    split.set_defaults(func=split_catalog)

    add = subparsers.add_parser(
        "add-theme",
        help="vendor a standalone CSS theme into a pack (e.g. mweb-theme); auto-detects wrapper class and light/dark",
    )
    add.add_argument("--pack", default="theme-hub", help="pack name -> references/<pack>-themes.json + references/<pack>/ (created if new)")
    add.add_argument("--from", dest="from_", help="CSS file path or http(s) URL")
    add.add_argument("--slug", help="unique theme slug within the pack (also the CSS filename)")
    add.add_argument("--name", help="display name (default: slug)")
    add.add_argument("--category", default="default", help="group within the pack, e.g. editorial/dark/minimal")
    add.add_argument("--license", help="SPDX license id, e.g. MIT")
    add.add_argument("--source-url", dest="source_url", help="upstream URL for provenance")
    add.add_argument("--wrapper-class", help="override auto-detect; 'none' for classless/body themes")
    add.add_argument("--appearance", choices=["auto", "light", "dark"], default="auto")
    add.add_argument("--code-theme", choices=sorted(CODE_THEMES.keys()), help="override paired code theme")
    add.add_argument("--mermaid-theme", choices=list(MERMAID_THEMES), help="override paired mermaid theme")
    add.add_argument("--manifest", help="JSON array of theme specs for batch-adding a whole group")
    add.add_argument("--strict-tls", action="store_true")
    add.set_defaults(func=add_theme)

    render = subparsers.add_parser("render", help="render Markdown to themed HTML")
    render.add_argument("markdown", type=Path)
    render.add_argument("--themes", nargs="+", required=True, help="1-5 theme IDs or names, comma-separated or repeated")
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    render.add_argument("--title")
    render.add_argument(
        "--code-theme",
        choices=sorted(CODE_THEMES.keys()),
        help="override the code-syntax theme (default: paired to the layout theme)",
    )
    render.add_argument(
        "--mermaid-theme",
        choices=list(MERMAID_THEMES),
        help="override the mermaid diagram theme (default: paired to the layout theme)",
    )
    render.add_argument(
        "--mode",
        choices=["auto", "inline", "stylesheet"],
        default="auto",
        help="output mode: auto (MDNice->inline, hub->stylesheet); inline (CSS on style attrs, WeChat/Zhihu paste); stylesheet (theme CSS in a <style> block, web/blog)",
    )
    render.add_argument(
        "--footnotes",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="convert inline links to footnotes (default: on for inline paste output, off for stylesheet documents)",
    )
    render.add_argument("--preview-tabs", action="store_true", help="force a tabbed preview even when one theme is selected")
    render.add_argument("--refresh-missing-styles", action="store_true")
    render.add_argument("--cache-styles", action="store_true")
    render.add_argument("--token-env", default="MDNICE_TOKEN")
    render.add_argument("--out-id")
    render.add_argument("--delay", type=float, default=0.15)
    render.add_argument("--strict-tls", action="store_true")
    render.set_defaults(func=render_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except MdniceError as exc:
        parser.exit(2, f"error: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "interrupted\n")


if __name__ == "__main__":
    raise SystemExit(main())
