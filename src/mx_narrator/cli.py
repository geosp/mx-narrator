"""Entry point and argument parsing. See spec section 10 for the full CLI surface.

    mx-narrator scripts/1jn-1-1-4.es.txt -o out/
    mx-narrator unit 1jn-1-1-4 -o out/ --voice voices/geo.wav
    mx-narrator unit 1jn-1-1-4 --langs es,pt
    mx-narrator scripts/1jn-1-1-4.en.txt --engine kokoro --draft
    mx-narrator scripts/1jn-1-1-4.pt.txt --preview 600 --voice voices/geo.wav
    mx-narrator batch scripts/ -o out/ --gpus 0,1,2,3

There is no explicit "file" subcommand name — a bare script path is the
default mode, so the first positional is inspected before argparse ever
sees it, and a synthetic "file" subcommand is spliced in when it isn't
"unit" or "batch".
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from mx_narrator.batch import RenderJob, RenderResult, plan_jobs, render_job, run_batch
from mx_narrator.detect import LanguageResolutionError, resolve_language
from mx_narrator.engines import DEFAULT_ENGINE, available_engines, get_engine
from mx_narrator.prep.registry import available_languages
from mx_narrator.units import discover_units, output_path

logger = logging.getLogger(__name__)


def _parse_langs(value: str) -> list[str]:
    langs = [x.strip() for x in value.split(",") if x.strip()]
    unknown = [l for l in langs if l not in available_languages()]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown language(s): {', '.join(unknown)}. Supported: {', '.join(available_languages())}"
        )
    return langs


def _parse_gpus(value: str) -> list[int]:
    try:
        return [int(x) for x in value.split(",") if x.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--gpus expects a comma-separated list of integers, got {value!r}") from exc


def _unit_id_from_script(path: Path) -> str:
    parts = path.stem.split(".")
    if len(parts) >= 2 and parts[-1] in available_languages():
        return ".".join(parts[:-1])
    return path.stem


def _common_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--engine", choices=available_engines(), default=DEFAULT_ENGINE, help="Synthesis engine.")
    p.add_argument("--voice", type=Path, default=None, help="Reference sample family (spec section 8).")
    p.add_argument("--speed", type=float, default=0.95, help="Playback speed multiplier.")
    p.add_argument(
        "--expressiveness", type=float, default=0.3, dest="exaggeration",
        help="Chatterbox 'exaggeration'. Default is low — devotional material, not promotional.",
    )
    p.add_argument(
        "--cfg-weight", type=float, default=0.5, dest="cfg_weight",
        help=(
            "Chatterbox pacing control. Higher values read faster/more rushed, "
            "lower values are slower and more deliberate (Chatterbox default: 0.5)."
        ),
    )
    p.add_argument("--seed", type=int, default=0, help="Fixed seed, for reproducible synthesis.")
    p.add_argument("--dry-run", action="store_true", help="Run prep only and print the prepared text.")
    p.add_argument("--format", choices=["mp3", "wav"], default="mp3", dest="audio_format")
    p.add_argument(
        "--draft", action="store_true",
        help="Shorthand for --engine kokoro --format wav, skipping loudness normalization and ID3 tagging.",
    )
    return p


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mx-narrator", description="Local multilingual narration CLI (es/en/pt)")
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = _common_parser()

    file_parser = subparsers.add_parser("file", parents=[common], help="Render a single script file.")
    file_parser.add_argument("script", type=Path)
    file_parser.add_argument("-o", "--out", type=Path, default=Path("out"))
    file_parser.add_argument("--lang", choices=available_languages(), default=None)
    file_parser.add_argument("--preview", type=int, default=None, help="Synthesize only the first N characters.")
    file_parser.add_argument(
        "--title", type=str, default=None,
        help="Override the auto-detected episode title (default: the script's first line).",
    )

    unit_parser = subparsers.add_parser("unit", parents=[common], help="Render every language version of a unit.")
    unit_parser.add_argument("unit_id")
    unit_parser.add_argument("-o", "--out", type=Path, default=Path("out"))
    unit_parser.add_argument("--scripts", type=Path, default=Path("scripts"))
    unit_parser.add_argument("--langs", type=_parse_langs, default=None)
    unit_parser.add_argument(
        "--title", type=str, default=None,
        help="Override the auto-detected episode title (default: the script's first line).",
    )

    batch_parser = subparsers.add_parser("batch", parents=[common], help="Render a whole series across GPUs.")
    batch_parser.add_argument("scripts_dir", type=Path)
    batch_parser.add_argument("-o", "--out", type=Path, default=Path("out"))
    batch_parser.add_argument("--gpus", type=_parse_gpus, default=None)
    batch_parser.add_argument("--langs", type=_parse_langs, default=None)

    return parser


def _apply_draft_shorthand(args: argparse.Namespace) -> None:
    if getattr(args, "draft", False):
        args.engine = "kokoro"
        args.audio_format = "wav"


def _report_result(result: RenderResult) -> int:
    job = result.job
    if not result.ok:
        print(f"error: {job.unit_id}.{job.lang}: {result.message}", file=sys.stderr)
        return 1
    if job.dry_run:
        print(f"--- {job.unit_id}.{job.lang} (dry run) ---")
        print(result.prepared_text)
        return 0
    print(f"wrote {result.message}")
    return 0


def _job_kwargs(args: argparse.Namespace) -> dict:
    return dict(
        engine_name=args.engine,
        voice_family=args.voice,
        speed=args.speed,
        exaggeration=args.exaggeration,
        cfg_weight=args.cfg_weight,
        seed=args.seed,
        audio_format=args.audio_format,
        normalize=not args.draft,
        dry_run=args.dry_run,
        device="cuda",
        title=getattr(args, "title", None),
    )


def _cmd_file(args: argparse.Namespace) -> int:
    if not args.script.exists():
        print(f"error: no such file: {args.script}", file=sys.stderr)
        return 1

    try:
        lang = resolve_language(args.script, lang_flag=args.lang)
    except LanguageResolutionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    unit_id = _unit_id_from_script(args.script)
    out_path = output_path(args.out, unit_id, lang, audio_format=args.audio_format)

    job = RenderJob(
        unit_id=unit_id,
        lang=lang,
        script_path=args.script,
        out_path=out_path,
        preview_chars=args.preview,
        **_job_kwargs(args),
    )
    result = render_job(job)
    return _report_result(result)


def _cmd_unit(args: argparse.Namespace) -> int:
    units = discover_units(args.scripts)
    unit = units.get(args.unit_id)
    if unit is None:
        print(f"error: no scripts found for unit {args.unit_id!r} in {args.scripts}", file=sys.stderr)
        return 1

    jobs, missing = plan_jobs({args.unit_id: unit}, out_dir=args.out, langs=args.langs, **_job_kwargs(args))
    for unit_id, lang in missing:
        print(f"missing: {unit_id}.{lang} — no source script found", file=sys.stderr)

    exit_code = 1 if missing else 0
    engine = None
    for job in jobs:
        if not args.dry_run and engine is None:
            engine = get_engine(job.engine_name)
            engine.load(device="cuda")
        result = render_job(job, engine=engine)
        if _report_result(result) != 0:
            exit_code = 1
    return exit_code


def _detect_gpu_ids() -> list[int]:
    import torch

    count = torch.cuda.device_count()
    if count == 0:
        raise SystemExit("no CUDA GPUs detected — pass --gpus explicitly, or check your driver install")
    return list(range(count))


def _cmd_batch(args: argparse.Namespace) -> int:
    units = discover_units(args.scripts_dir)
    kwargs = _job_kwargs(args)
    kwargs["dry_run"] = False  # batch always renders; use `unit --dry-run` to preview one first
    jobs, missing = plan_jobs(units, out_dir=args.out, langs=args.langs, **kwargs)

    gpu_ids = args.gpus or _detect_gpu_ids()
    logger.info("batch: %d jobs across %d GPU(s): %s", len(jobs), len(gpu_ids), gpu_ids)
    results = run_batch(jobs, gpu_ids=gpu_ids)

    succeeded = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]

    print(f"\n=== batch summary: {len(succeeded)} succeeded, {len(failed)} failed, {len(missing)} missing ===")
    for r in sorted(succeeded, key=lambda r: (r.job.unit_id, r.job.lang)):
        print(f"  OK      {r.job.unit_id}.{r.job.lang} -> {r.message}")
    for r in sorted(failed, key=lambda r: (r.job.unit_id, r.job.lang)):
        print(f"  FAILED  {r.job.unit_id}.{r.job.lang}: {r.message}")
    for unit_id, lang in sorted(missing):
        print(f"  MISSING {unit_id}.{lang}: no source script")

    return 0 if not failed and not missing else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in {"unit", "batch", "-h", "--help"}:
        argv = ["file", *argv]
    elif not argv:
        argv = ["-h"]

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = build_parser()
    args = parser.parse_args(argv)
    _apply_draft_shorthand(args)

    if args.command == "file":
        return _cmd_file(args)
    if args.command == "unit":
        return _cmd_unit(args)
    if args.command == "batch":
        return _cmd_batch(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
