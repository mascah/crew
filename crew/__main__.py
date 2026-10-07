"""`python -m crew <command>`: run and operate Crew on this Mac."""

import argparse
import json
import secrets
import sys
from pathlib import Path

from crew import config

UI = Path(__file__).resolve().parent.parent / "web" / "dist"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="crew", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (("collector", "run this Mac's collector"),
                       ("service", "run the Mini service on loopback")):
        runner = commands.add_parser(name, help=text)
        runner.add_argument("--standby", action="store_true",
                            help="wait for the owning instance instead of exiting")
    commands.add_parser("openapi", help="print the API schema")
    commands.add_parser("token", help="print a new collector token and its config hash")
    project = commands.add_parser("project", help="list projects or map a key explicitly")
    project.add_argument("map", nargs="*", metavar="PROJECT_ID KEY")
    install = commands.add_parser("install", help="install hooks, the plugin or LaunchAgents")
    install.add_argument("what", choices=["hooks", "hermes", "collector", "service"])
    install.add_argument("--remove", action="store_true")
    install.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "collector":
        from crew.collector import run

        run(standby=args.standby)
    elif args.command in ("service", "openapi", "project"):
        from crew.service import Store, create_app

        cfg = config.load()
        if args.command == "openapi":
            app = create_app(cfg, Store(Path(":memory:"), cfg))
            print(json.dumps(app.openapi(), indent=2, sort_keys=True))
            return
        config.home().mkdir(parents=True, exist_ok=True)
        store = Store(config.home() / "service.db", cfg)
        if args.command == "service":
            import uvicorn

            lock = config.own("service", args.standby)  # noqa: F841 - held while serving
            app = create_app(cfg, store, ui=UI)
            uvicorn.run(app, host="127.0.0.1", port=cfg.port, access_log=False)
        elif len(args.map) == 2:
            store.map_key(args.map[1], args.map[0])
        else:
            for view, keys in store.projects():
                print(f"{view.id}  {view.name}  ({view.detail})")
                for key in keys:
                    print(f"    {key}")
    elif args.command == "token":
        from crew.collector import token_hash

        token = secrets.token_urlsafe(32)
        print(f"token = {token!r}  # collector config, on the reporting Mac")
        print(f"{token_hash(token)!r} = '<machine_id>'  # under [collectors], on the Mini")
    elif args.command == "install":
        from crew import install

        sys.exit(install.main(args.what, remove=args.remove, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
