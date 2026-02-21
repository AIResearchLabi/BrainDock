"""Entry point: python -m BrainDock.dashboard [--output-dir DIR] [--port PORT] [--no-log]"""

from .runner import PipelineRunner
from .server import parse_args, run_server

if __name__ == "__main__":
    args = parse_args()
    runner = PipelineRunner(output_dir=args.output_dir)
    run_server(
        output_dir=args.output_dir,
        port=args.port,
        runner=runner,
        verbose=not args.no_log,
    )
