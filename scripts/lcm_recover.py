import os
import sqlite3, json, sys, time, argparse
import importlib
from pathlib import Path


# Constants
TRUNC_MARKER = '%deterministic truncation%'
# Default plugin location. Overridable via --plugin-dir CLI flag or LCM_PLUGIN_DIR
# env var. Critical: after the Phase 2.5 symlink swap on
# ~/.hermes/plugins/hermes-lcm -> hermes-lcm-phase25/, this script must be told
# to load from the new location, else it tests the OLD escalation.py while the
# gateway runs the NEW one (GLM-5.2 second-opinion 2026-08-25 23:07).
DEFAULT_PLUGIN_DIR = Path('/home/hermes-pi/projects/hermes-lcm')
PLUGIN_DIR = Path(
    os.environ.get('LCM_PLUGIN_DIR', str(DEFAULT_PLUGIN_DIR))
)


def open_db(path):
    c = sqlite3.connect(path, isolation_level=None)  # we use explicit BEGIN
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA busy_timeout=5000')
    return c


def candidates(c, max_source_tokens=None):
    """Select recoverable L3 rows.

    Legacy mode (default): summary token_count <= 600 -- the original narrow
    filter, which matches only 27 rows in the current DB.

    Widened mode (--max-source-tokens N): capacity-fit selection by SOURCE
    token count -- the Phase 3 dry-run population. N=3500 covers the fit
    bucket (<=3000) plus boundary25 (3000..3500] => 144 nodes at the v2
    reclassification boundary.
    """
    q = """
        SELECT node_id, session_id, depth, source_ids, source_token_count,
               created_at, earliest_at, latest_at, expand_hint, length(summary) AS old_len
        FROM summary_nodes
        WHERE summary LIKE ?
          AND source_ids <> '[]'
          AND summary NOT LIKE '[stub-recovery%'
    """
    params = [TRUNC_MARKER]
    if max_source_tokens is not None:
        q += "          AND COALESCE(source_token_count, 0) <= ?\n"
        params.append(max_source_tokens)
    else:
        q += "          AND COALESCE(token_count, 0) <= 600\n"
    return c.execute(q, params).fetchall()


def recover_one(c, row, new_summary, new_token_count):
    node_id = row[0]
    c.execute('BEGIN IMMEDIATE')
    try:
        # Read old summary INSIDE the write lock (Codex v2.1 review): another
        # writer could alter the row between candidate selection and here.
        got = c.execute(
            "SELECT summary FROM summary_nodes WHERE node_id=?", (node_id,)
        ).fetchone()
        if got is None:
            c.execute('ROLLBACK')
            return 0
        old_summary = got[0]
        # Delete old FTS postings.
        c.execute(
            "INSERT INTO nodes_fts(nodes_fts, rowid, summary) "
            "VALUES('delete', ?, ?)",
            (node_id, old_summary),
        )
        # Insert new FTS postings (NOT UPDATE -- that corrupts external-content FTS5).
        c.execute(
            "INSERT INTO nodes_fts(rowid, summary) VALUES(?, ?)",
            (node_id, new_summary),
        )
        # Guarded UPDATE with an EXACT-value idempotency predicate (not LIKE):
        # commits only if the row still carries the exact marker text we read.
        cur = c.execute(
            "UPDATE summary_nodes SET summary=?, token_count=? "
            "WHERE node_id=? AND summary=?",
            (new_summary, new_token_count, node_id, old_summary),
        )
        if cur.rowcount == 0:
            # Do not commit speculative FTS changes if another process won the race.
            c.execute('ROLLBACK')
            return 0
        c.execute('COMMIT')
        return cur.rowcount
    except Exception:
        c.execute('ROLLBACK')
        raise


def _load_summarizer():
    """Load the installed checkout only when --live was explicitly requested.

    The plugin directory is ``hermes-lcm`` (hyphenated), so importlib bypasses
    Python's hyphen restriction, but relative imports inside ``escalation.py``
    (``from . import tokens as _token_module``) require the parent package to be
    registered under a valid identifier. We synthesise a ``hermes_lcm`` alias so
    the relative imports resolve cleanly.
    """
    import importlib.util
    import sys as _sys
    import types as _types

    plugin_dir = str(PLUGIN_DIR)
    parent_dir = str(PLUGIN_DIR.parent)

    if 'hermes_lcm' not in _sys.modules:
        package = _types.ModuleType('hermes_lcm')
        package.__path__ = [plugin_dir]
        _sys.modules['hermes_lcm'] = package

    # The L1/L2 helpers inside ``escalation.py`` import ``agent.auxiliary_client``
    # which lives in the Hermes host checkout, not in hermes-lcm. When the plugin
    # runs inside the gateway the host venv already has ``agent`` on sys.path;
    # standalone recovery scripts have to add it explicitly.
    for candidate in (
        '/home/hermes-pi/hermes-agent',
        '/home/hermes-pi/.hermes/hermes-agent',
        str(Path('/home/hermes-pi/hermes-agent').parent),
    ):
        if Path(candidate, 'agent').is_dir() and candidate not in _sys.path:
            _sys.path.insert(0, candidate)
            break

    if parent_dir not in _sys.path:
        _sys.path.insert(0, parent_dir)

    if 'hermes_lcm.escalation' not in _sys.modules:
        spec = importlib.util.spec_from_file_location(
            'hermes_lcm.escalation',
            str(PLUGIN_DIR / 'escalation.py'),
        )
        module = importlib.util.module_from_spec(spec)
        _sys.modules['hermes_lcm.escalation'] = module
        spec.loader.exec_module(module)
    else:
        module = _sys.modules['hermes_lcm.escalation']

    return module.summarize_with_escalation, module.count_tokens


def _source_messages(c, source_ids, session_id):
    """Return source messages in source_ids order, without SQLite variable limits."""
    if not isinstance(source_ids, list) or not source_ids:
        raise ValueError('source_ids must be a non-empty JSON list')
    if any(not isinstance(source_id, int) for source_id in source_ids):
        raise ValueError('source_ids must contain only integer message IDs')

    found = {}
    for start in range(0, len(source_ids), 500):
        chunk = source_ids[start:start + 500]
        placeholders = ','.join('?' for _ in chunk)
        query = f"""
            SELECT store_id, session_id, role, content, tool_call_id,
                   tool_calls, tool_name, timestamp
            FROM messages
            WHERE store_id IN ({placeholders})
        """
        for message in c.execute(query, chunk):
            found[message[0]] = message

    missing = [source_id for source_id in source_ids if source_id not in found]
    if missing:
        raise ValueError(f'missing source message IDs: {missing[:10]}')
    messages = [found[source_id] for source_id in source_ids]
    wrong_session = [message[0] for message in messages if message[1] != session_id]
    if wrong_session:
        raise CrossSessionSourceError(
            f'source messages belong to another session: {wrong_session[:10]}'
        )
    return messages


class CrossSessionSourceError(ValueError):
    """Raised when a summary node references source_ids from a different session.

    This is a known data-integrity edge case (cross-session bleed) that the
    recovery script cannot fix from source messages alone. The caller should
    record the node_id and skip rather than failing the entire run.
    """


def _serialize_messages(messages):
    """Serialize raw message records into labeled text for the L1/L2 prompts."""
    parts = []
    for _, _, role, content, tool_call_id, tool_calls, tool_name, _ in messages:
        content = content or ''
        if role == 'tool':
            label = f"TOOL RESULT {tool_call_id or tool_name or ''}".rstrip()
        else:
            label = (role or 'unknown').upper()
        part = f'[{label}]: {content}'
        if tool_calls:
            part += f'\n[Tool calls: {tool_calls}]'
        parts.append(part)
    return '\n\n'.join(parts)


def _local_summarize(text, source_tokens, token_budget, depth):
    """Direct local llama-server summarizer (bypasses Hermes auxiliary).

    The Hermes auxiliary client routes through OpenRouter; when OpenRouter
    is credit-exhausted (HTTP 402), this fallback talks to the local Qwen2.5
    server on :8080 directly via the openai-compatible API. Lower fidelity but
    produces a real summary that lifts the L3 truncation marker without
    depending on paid auxiliary capacity.

    Qwen2.5-0.5B has a 4096-token context. Truncate the input to leave headroom
    for the summary output, and retry with smaller input if the server returns
    a context-size error.

    v2.1 (2026-08-26): the retry ladder is now DENSITY-AWARE. Measured on this
    host (scripts/v21_margin_probe.py): prose ~189 tok/1k chars, code ~249,
    worst-case hex/base64 blobs ~899 — i.e. chars/4 undercounts dense text up
    to 2.2x and a fixed 12000-char head cut can blow past n_ctx 3x over. The
    first rung now picks its char budget from a cheap script-density scan of
    the actual text (worst-case assumption), so rung 1 fits n_ctx even for
    blob-dense sources; later rungs shrink as before.
    """
    from openai import OpenAI
    client = OpenAI(base_url='http://127.0.0.1:8080/v1', api_key='not-needed')

    # The local Qwen2.5-0.5B context is 4096 tokens. Cap input at 3000 to leave
    # ~1000 tokens of headroom for the output summary.
    max_input_tokens = 3000

    def _density_safe_chars(t):
        """Chars budget keeping worst-case density <= 3000 server tokens."""
        if not t:
            return 3600
        non_ascii = sum(1 for ch in t[:8000] if ord(ch) > 127)
        ratio = non_ascii / min(len(t), 8000)
        if ratio >= 0.5:
            divisor = 1.5
        elif ratio >= 0.2:
            divisor = 2.5
        else:
            # ASCII density scan: token-dense blobs (hex/base64 dumps, ~0.85
            # tok/char) have essentially no whitespace; prose and code keep
            # >8%. Measured on this host via /tokenize (v2.1 follow-up,
            # 2026-08-26): hex 2550c->2229t, b64 2550c->1896t, prose
            # 9900c->1730t, code 9900c->2383t — all within budget+overhead.
            sample = t[:8000]
            ws_ratio = sum(1 for ch in sample if ch.isspace()) / len(sample)
            divisor = 3.3 if ws_ratio >= 0.08 else 0.85   # worst-case blob floor
        return int(max_input_tokens * divisor)

    first_rung = _density_safe_chars(text)
    # Strictly decreasing rungs (Codex v2.1 review): dedupe + shrink only.
    seen = set()
    rungs = []
    for rc in (first_rung, min(first_rung - 1, 2000), 1000, 500):
        rc = max(200, rc)
        if rc not in seen:
            seen.add(rc)
            rungs.append(rc)
    for max_input_chars in rungs:
        truncated = text[:max_input_chars] if len(text) > max_input_chars else text
        target_tokens = min(token_budget, 400)  # local model is 0.5B; cap output
        prompt = (
            "Summarize the following conversation into a compact, factual summary. "
            "Preserve user intent, decisions, and key facts. Be terse.\n\n"
            f"--- BEGIN CONVERSATION ({len(truncated)} chars) ---\n{truncated}\n--- END CONVERSATION ---\n\n"
            f"Summary (target ~{target_tokens} tokens):"
        )
        try:
            response = client.chat.completions.create(
                model='Qwen2.5-0.5B-Instruct-Q4_K_M.gguf',
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=target_tokens,
                temperature=0.2,
                timeout=120,
            )
            content = (response.choices[0].message.content or '').strip()
            if content:
                return content
        except Exception as e:
            err = str(e)
            if 'context size' in err or 'tokens)' in err:
                print(
                    f'[local] context overflow at {max_input_chars} chars; retrying smaller',
                    file=sys.stderr,
                )
                continue
            raise
    return None


def live_summary(c, row):
    source_ids = json.loads(row[3])
    messages = _source_messages(c, source_ids, row[1])
    text = _serialize_messages(messages)
    summarize_with_escalation, count_tokens = _load_summarizer()
    source_tokens = row[4] or count_tokens(text)
    token_budget = min(12000, max(2000, int(source_tokens * 0.20)))
    try:
        summary, _level = summarize_with_escalation(
            text=text,
            source_tokens=source_tokens,
            token_budget=token_budget,
            depth=row[2],
        )
    except Exception as e:
        print(f'[live_summary] auxiliary failed: {type(e).__name__}: {e}; falling back to local', file=sys.stderr)
        summary = None
    if not summary:
        try:
            summary = _local_summarize(text, source_tokens, token_budget, row[2])
        except Exception as e:
            print(f'[live_summary] local fallback also failed: {type(e).__name__}: {e}', file=sys.stderr)
            summary = None
    return summary, count_tokens(summary or '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='/tmp/lcm_recovery_test.db')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--limit', type=int, default=0,
                    help='process at most N rows (0 = all)')
    ap.add_argument('--live', action='store_true',
                    help='call the plugin summarizer; otherwise write deterministic stubs')
    ap.add_argument('--local-only', action='store_true',
                    help='skip the Hermes auxiliary client and use the local '
                         'Qwen2.5 0.5B llama-server on 127.0.0.1:8080 directly. '
                         'Use this when OpenRouter is credit-exhausted.')
    ap.add_argument('--stub', action='store_true',
                    help='write a deterministic stub summary (no LLM call). '
                         'Clears the L3 truncation marker so the row is no '
                         'longer counted as recoverable, but does NOT claim '
                         'to be a real LLM summary. Use this when the full '
                         'LLM recovery is not feasible (e.g. paid auxiliary '
                         'is down and local models lack context headroom).')
    ap.add_argument('--confirm-live', action='store_true',
                    help='explicit confirmation that --live writes to the LIVE DB. '
                         'Without this flag, --live is rejected when --db is '
                         '~/.hermes/lcm.db. Combine with --backup to satisfy the '
                         'precondition.')
    ap.add_argument('--backup', default=None,
                    help='path to a backup of the live DB created in this session. '
                         'Required when running --live/--stub against '
                         '~/.hermes/lcm.db without --dry-run.')
    ap.add_argument('--plugin-dir', default=None,
                    help='path to the hermes-lcm checkout to load escalation.py from. '
                         'Overrides LCM_PLUGIN_DIR env var. MUST point at the same '
                         'plugin the gateway is currently using (i.e. follow the '
                         '~/.hermes/plugins/hermes-lcm symlink), else this script '
                         'tests DIFFERENT code than the running gateway.')
    ap.add_argument('--max-source-tokens', type=int, default=None,
                    help='widen candidate selection to nodes whose SOURCE '
                         'token_count <= N (the capacity-fit Phase 3 dry-run '
                         'population; 3500 => fit+boundary25 ~= 144 nodes). '
                         'Omit to keep the legacy summary-token <=600 filter.')
    ap.add_argument('--stratify', type=int, default=0,
                    help='downsample the widened candidate list to N nodes spread '
                         'evenly across the source-token range. Requires '
                         '--max-source-tokens.')
    args = ap.parse_args()

    # Resolve --plugin-dir: CLI flag > env var > default
    if args.plugin_dir:
        global PLUGIN_DIR
        PLUGIN_DIR = Path(args.plugin_dir)
    elif 'LCM_PLUGIN_DIR' in os.environ:
        PLUGIN_DIR = Path(os.environ['LCM_PLUGIN_DIR'])

    if args.limit < 0:
        ap.error('--limit must be zero or greater')

    # Safety gates (ADR-2026-08-25-10, extended per Codex v2.1 review):
    # --live, --stub AND --local-only are write-side actions that overwrite
    # real L3 rows. Refuse them on the live DB unless the operator has typed
    # --confirm-live AND provided a backup path.
    LIVE_DB = Path.home() / '.hermes' / 'lcm.db'
    is_live_db = Path(args.db).resolve() == LIVE_DB.resolve()
    write_modes = [m for m in (args.live, args.stub, args.local_only) if m]
    if len(write_modes) > 1:
        ap.error('Pass at most one of --live / --stub / --local-only.')
    if is_live_db and not args.dry_run and write_modes:
        if not args.confirm_live:
            ap.error(
                'Refusing --live/--stub/--local-only against the live DB '
                'without --confirm-live. Pass --confirm-live to acknowledge '
                'the write, and --backup <path> to point at a backup taken '
                'in this session.'
            )
        if not args.backup or not Path(args.backup).is_file():
            ap.error(
                'Refusing --live/--stub/--local-only against the live DB '
                'without a verified backup. Take an online-consistent '
                'snapshot first: '
                'sqlite3 ~/.hermes/lcm.db ".backup \'<path>\'" '
                '(a plain cp of a WAL database can be torn). Then pass '
                '--backup <path>. The backup is quick_check-verified below.'
            )
        # Verify the backup is a real, intact lcm.db snapshot (audit R2:
        # Path.is_file() alone accepted garbage files or the live DB itself).
        import sqlite3 as _sq
        try:
            _bconn = _sq.connect(f'file:{Path(args.backup).resolve()}?mode=ro', uri=True)
            try:
                if _bconn.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('quick_check failed')
                if _bconn.execute('SELECT count(*) FROM summary_nodes').fetchone()[0] < 1:
                    raise ValueError('backup contains no summary_nodes rows')
            finally:
                _bconn.close()
        except Exception as _e:
            ap.error(
                f'--backup {args.backup} is not a valid lcm.db snapshot: '
                f'{type(_e).__name__}: {_e}. Re-create it with '
                "'sqlite3 ~/.hermes/lcm.db \".backup <path>\"' and retry."
            )

    started = time.time()
    c = open_db(args.db)
    rows = candidates(c, max_source_tokens=args.max_source_tokens)
    if args.stratify:
        if args.max_source_tokens is None:
            ap.error('--stratify requires --max-source-tokens')
        if args.stratify < len(rows):
            # Even spread across the list (which is ordered by node_id, a proxy
            # for creation time) => covers the whole token range without
            # clustering on old or new nodes.
            step = len(rows) / args.stratify
            rows = [rows[int(i * step)] for i in range(args.stratify)]
    if args.limit:
        rows = rows[:args.limit]

    stats = {
        'considered': len(rows),
        'updated': 0,
        'skipped_idempotent': 0,
        'skipped_cross_session': 0,
        'cross_session_node_ids': [],
        'failed': [],
        'node_ids': [row[0] for row in rows],
    }

    for row in rows:
        try:
            if args.stub:
                # Deterministic stub: explicitly NOT a real summary. Marker
                # '[stub]' makes downstream audits trivially distinguishable.
                source_ids = json.loads(row[3])
                new_summary = (
                    f"[stub-recovery placeholder for node_id={row[0]}, session={row[1]}, "
                    f"source_ids={len(source_ids)} msgs] deterministic truncation marker "
                    f"lifted without LLM call. Original source preserved in source_ids."
                )
                new_token_count = len(new_summary.split())
            elif args.local_only:
                text = _serialize_messages(_source_messages(c, json.loads(row[3]), row[1]))
                summarize_with_escalation, count_tokens = _load_summarizer()
                source_tokens = row[4] or count_tokens(text)
                token_budget = min(12000, max(2000, int(source_tokens * 0.20)))
                new_summary = _local_summarize(text, source_tokens, token_budget, row[2])
                new_token_count = count_tokens(new_summary or '')
            elif args.live:
                new_summary, new_token_count = live_summary(c, row)
            else:
                # Deterministic stub: validate FTS plumbing without an LLM dependency.
                new_summary = (
                    f"[recovered from source_ids={row[3][:60]}] "
                    f"stub summary for node_id={row[0]}"
                )
                new_token_count = len(new_summary.split())
            if not new_summary:
                # Never count or write an empty summary (e.g. local retry
                # ladder exhausted): record as failure instead.
                stats['failed'].append((row[0], 'EmptySummary',
                                        'summarizer produced no content'))
                continue
            if args.dry_run:
                stats['updated'] += 1  # would have written
                continue
            n = recover_one(c, row, new_summary, new_token_count)
            if n == 1:
                stats['updated'] += 1
            else:
                stats['skipped_idempotent'] += 1
        except CrossSessionSourceError as e:
            # Data-integrity edge case: this summary node's source_ids belong to
            # a different session. Cannot recover from source messages; log and
            # skip rather than failing the entire run.
            stats['skipped_cross_session'] += 1
            stats['cross_session_node_ids'].append(row[0])
        except Exception as e:
            stats['failed'].append((row[0], type(e).__name__, str(e)[:120]))

    # Belt-and-suspenders rebuild.
    if not args.dry_run and stats['updated'] > 0:
        try:
            c.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('rebuild')")
        except Exception as e:
            stats['failed'].append(('rebuild', type(e).__name__, str(e)[:120]))

    if args.dry_run:
        stats['integrity_check'] = 'not run (dry-run)'
    else:
        try:
            c.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('integrity-check')")
            stats['integrity_check'] = 'passed'
        except Exception as e:
            stats['integrity_check'] = 'failed'
            stats['failed'].append(('integrity-check', type(e).__name__, str(e)[:120]))

    stats['duration_seconds'] = round(time.time() - started, 2)
    print(json.dumps(stats, indent=2))
    # Non-zero exit when anything failed (Codex v2.1 review): automation must
    # not treat a partial failure as success.
    c.close()
    sys.exit(1 if stats['failed'] else 0)


if __name__ == '__main__':
    main()
