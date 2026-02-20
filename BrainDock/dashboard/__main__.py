"""Entry point: python -m BrainDock.dashboard [--output-dir DIR] [--port PORT]"""

from .server import parse_args, run_server

if __name__ == "__main__":
    args = parse_args()
    run_server(output_dir=args.output_dir, port=args.port)
