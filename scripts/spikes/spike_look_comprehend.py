"""Phase-0 spike: prove the kernel comprehends "look around" -> the LOOK construction.

Authors a minimal LOOK grammar (two variants) against the live graph-memory
kernel (:8001) and comprehends several utterances, printing applied_cxn_ids /
matched / predicate for each. Token read from bonfires-ai-core/.env; never printed.

GO  = at least one variant yields a frame with matched=True and the LOOK
      construct_id in applied_cxn_ids for "look around".
NO-GO = no variant comprehends "look around" to LOOK.
"""

import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8001"
BONFIRE = "6a3e8c71f3326302eee047e4"  # existing mm-world-v1 ObjectId (from the demo)
CORE_ENV = "/home/at0x/Vaults/Bonfires/bonfires-ai-core/.env"


def load_token():
    with open(CORE_ENV) as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("GM_INTERNAL_TOKEN=") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    print("ERROR: GM_INTERNAL_TOKEN not in .env", file=sys.stderr)
    sys.exit(2)


TOKEN = load_token()


def _post(path, body, permission):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Internal-Token": TOKEN,
            "X-Permission": permission,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:600]}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": repr(e)}


def author(profile, constructions):
    return _post(
        f"/v1/bonfires/{BONFIRE}/kernel/author-grammar",
        {"constructions": constructions, "profile": profile},
        "write",
    )


def comprehend(profile, utterance):
    return _post(
        f"/v1/bonfires/{BONFIRE}/kernel/comprehend",
        {"actor_id": "spike-actor", "utterance": utterance, "profile": profile},
        "read",
    )


def report(label, status, body):
    frame = (body or {}).get("frame") if isinstance(body, dict) else None
    if frame:
        print(
            f"  [{label}] HTTP {status} | matched={frame.get('matched')} "
            f"predicate={frame.get('predicate')!r} "
            f"applied_cxn_ids={frame.get('applied_cxn_ids')} "
            f"conf={frame.get('confidence')}"
        )
    else:
        diag = (body or {}).get("diagnostics") if isinstance(body, dict) else None
        print(f"  [{label}] HTTP {status} | frame=None diagnostics={diag} err={(body or {}).get('error')}")


VARIANTS = {
    # V1: verb-only LOOK. Simplest possible; no roles, no connective.
    "spike-look-v1": [
        {
            "construct_id": "mm.look.v1",
            "name": "LOOK",
            "predicate": "look",
            "lemmas": ["look"],
            "roles": [],
            "lexicon": [],
            "form": [{"role": "verb"}],
        }
    ],
    # V2: LOOK + an "around"/"about" particle bound in the lexicon.
    "spike-look-v2": [
        {
            "construct_id": "mm.look.v1",
            "name": "LOOK",
            "predicate": "look",
            "lemmas": ["look"],
            "roles": ["direction"],
            "lexicon": [{"surface": d, "category": "noun-cxn"} for d in ("around", "about", "round")],
            "form": [{"role": "verb"}, {"role": "direction", "connective": " "}],
        }
    ],
}

UTTERANCES = ["look", "look around", "look about", "i look around", "look around the room"]

print(f"=== Phase-0 spike: LOOK comprehension (bonfire {BONFIRE}) ===\n")
for profile, cxns in VARIANTS.items():
    print(f"--- authoring {profile} ({cxns[0]['form']}) ---")
    st, body = author(profile, cxns)
    print(f"  author -> HTTP {st} construct_ids={body.get('construct_ids') if isinstance(body, dict) else body} "
          f"err={(body or {}).get('error') if isinstance(body, dict) else ''}")
    if st != 200:
        print("  (author failed; skipping comprehension for this variant)\n")
        continue
    for utt in UTTERANCES:
        st2, body2 = comprehend(profile, utt)
        report(f"{utt!r}", st2, body2)
    print()
print("=== done ===")
