#!/usr/bin/env python3
"""Bump one plugin's version where other machines read it.

    python tools/bump.py wardrobe 0.6.0 "skirts fold with the thighs."
    python tools/bump.py wardrobe 0.6.0 "Since 0.6.0 skirts fold with the thighs."   # same thing
    python tools/bump.py wardrobe 0.6.0 "..." --dry-run                               # print, write nothing

It changes exactly three things and nothing else in either file:

- `version` in plugins/<plugin>/.claude-plugin/plugin.json;
- that plugin's `version` in .claude-plugin/marketplace.json;
- a "Since <version> ..." sentence appended to that plugin's marketplace `description`.

The files are edited as text, so their line endings, key order and indentation stay as they were, and
each is parsed again afterwards and compared with the original: any difference other than those three
fields refuses and writes nothing. It refuses a version that is not x.y.z, one that is not above the
current one, an unknown plugin, and a description that already has a sentence for that version.

plugin.json's own description is left alone: its Since sentences stopped at 0.5.0-0.14.0, and
marketplace.json is what `/plugin marketplace update` reads.

Goldens: each one records the plugin versions that built it (`plugins` in tests/golden/*.json), and
tools/regress.py never compares that stamp. There is no restamp mechanism, so this does not touch
tests/golden; the next `regress.py --update` of a golden that moved rewrites its stamp.
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MARKETPLACE = Path(".claude-plugin") / "marketplace.json"
VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class Refused(Exception):
    pass


def parse_version(text):
    m = VERSION.match(text or "")
    if not m:
        raise Refused("%r is not a version: want x.y.z, digits only, no leading zeros" % text)
    return tuple(int(g) for g in m.groups())


def sentence_for(version, since):
    since = " ".join(since.split())
    if not since:
        raise Refused("the Since sentence is empty")
    m = re.match(r"^Since (\S+?)[,:]?\s+(.*)$", since)
    if m:
        if m.group(1) != version:
            raise Refused("the sentence says Since %s but the version is %s" % (m.group(1), version))
        since = m.group(2)
    if not since.endswith((".", "!", "?")):
        since += "."
    return "Since %s %s" % (version, since)


def _read(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8")


def _write(path, text):
    with open(path, "wb") as fh:
        fh.write(text.encode("utf-8"))


def _replace_once(text, start, pattern, repl, what):
    """Replace the first match of pattern at or after `start`. Returns the new text."""
    m = re.compile(pattern).search(text, start)
    if not m:
        raise Refused("could not find %s" % what)
    return text[:m.start()] + repl(m) + text[m.end():]


def bump(repo, plugin, version, since, dry_run=False):
    """Returns [(file, what changed)]. Raises Refused and writes nothing on any problem."""
    new = parse_version(version)
    plugin_json = repo / "plugins" / plugin / ".claude-plugin" / "plugin.json"
    market = repo / MARKETPLACE
    if not market.is_file():
        raise Refused("no %s" % market)
    known = [p["name"] for p in json.loads(_read(market))["plugins"]]
    if plugin not in known or not plugin_json.is_file():
        raise Refused("unknown plugin %r (have: %s)" % (plugin, ", ".join(known)))

    pj_text = _read(plugin_json)
    pj = json.loads(pj_text)
    mk_text = _read(market)
    mk = json.loads(mk_text)
    entry = next(p for p in mk["plugins"] if p["name"] == plugin)
    if pj.get("version") != entry.get("version"):
        raise Refused("plugin.json says %s and marketplace.json says %s: settle that by hand first"
                      % (pj.get("version"), entry.get("version")))
    old = parse_version(pj["version"])
    if new <= old:
        raise Refused("%s is not above the current %s" % (version, pj["version"]))
    if re.search(r"\bSince %s\b" % re.escape(version), entry.get("description", "")):
        raise Refused("the marketplace description already has a Since %s sentence" % version)
    sentence = sentence_for(version, since)

    # plugin.json: the one top-level "version".
    pj_new = _replace_once(pj_text, 0, r'("version"\s*:\s*")([^"]*)(")',
                           lambda m: m.group(1) + version + m.group(3), "version in %s" % plugin_json)
    # marketplace.json: from this plugin's "name", its "version" and its "description".
    at = re.search(r'"name"\s*:\s*%s\s*,' % re.escape(json.dumps(plugin)), mk_text)
    if not at:
        raise Refused("could not find %s's entry in %s" % (plugin, market))
    mk_new = _replace_once(mk_text, at.end(), r'("version"\s*:\s*")([^"]*)(")',
                           lambda m: m.group(1) + version + m.group(3), "%s's version" % plugin)
    encoded = json.dumps(" " + sentence, ensure_ascii=False)[1:-1]
    mk_new = _replace_once(mk_new, at.end(), r'("description"\s*:\s*")((?:[^"\\]|\\.)*)(")',
                           lambda m: m.group(1) + m.group(2).rstrip() + encoded + m.group(3),
                           "%s's description" % plugin)

    # Parse both again: exactly the three fields may differ.
    pj_after, mk_after = json.loads(pj_new), json.loads(mk_new)
    want_pj = dict(pj, version=version)
    want_mk = json.loads(mk_text)
    for p in want_mk["plugins"]:
        if p["name"] == plugin:
            p["version"] = version
            p["description"] = p["description"].rstrip() + " " + sentence
    if pj_after != want_pj or mk_after != want_mk:
        raise Refused("the edit changed more than the version and the Since sentence; nothing written")

    if not dry_run:
        _write(plugin_json, pj_new)
        _write(market, mk_new)
    return [(plugin_json.relative_to(repo).as_posix(), "version %s -> %s" % (pj["version"], version)),
            (market.relative_to(repo).as_posix() if market.is_absolute() else str(market),
             "%s version %s -> %s, description + %r" % (plugin, entry["version"], version, sentence))]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plugin")
    ap.add_argument("version", help="x.y.z, above the current one")
    ap.add_argument("since", help='the sentence for the marketplace description, with or without "Since x.y.z"')
    ap.add_argument("--repo", default=str(REPO), help="the checkout to edit (default: this one)")
    ap.add_argument("--dry-run", action="store_true", help="print what would change and write nothing")
    args = ap.parse_args(argv)
    try:
        changes = bump(Path(args.repo).resolve(), args.plugin, args.version, args.since, args.dry_run)
    except Refused as exc:
        print("bump: refused: %s" % exc, file=sys.stderr)
        return 1
    for path, what in changes:
        print("%s%s: %s" % ("(dry run) " if args.dry_run else "", path, what))
    print("goldens: not restamped - tests/golden/*.json record plugin versions under `plugins`, which "
          "regress never compares, and the repo has no restamp mechanism; the next --update of a golden "
          "that moved rewrites its stamp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
