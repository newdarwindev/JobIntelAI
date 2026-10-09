"""Serve a configured, explicitly migrated application without implicit database DDL."""

import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["dev", "demo"], default="dev")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    from jobintel.api import create_app

    uvicorn.run(create_app(demo=args.mode == "demo"), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
