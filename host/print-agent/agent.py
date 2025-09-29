"""Agente de impresión para Zebra ZD888t.

Este script es un esqueleto que ejemplifica cómo consultar la API de picking
para obtener trabajos de impresión y enviarlos al spooler de Windows.
"""

import json
import logging
import time
from pathlib import Path

import requests

try:  # pragma: no cover - dependencia Windows
    import win32print  # type: ignore
except Exception:  # pragma: no cover - entorno no Windows
    win32print = None

CONFIG_PATH = Path(__file__).with_name("config.yaml")
LOGGER = logging.getLogger("print-agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def load_config() -> dict:
    import yaml  # type: ignore

    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def send_raw_to_printer(printer_name: str, raw_data: str) -> None:
    if win32print is None:
        raise RuntimeError("win32print no disponible en este entorno")
    handle = win32print.OpenPrinter(printer_name)
    try:
        job = win32print.StartDocPrinter(handle, 1, ("Picking", None, "RAW"))
        win32print.StartPagePrinter(handle)
        win32print.WritePrinter(handle, raw_data.encode("utf-8"))
        win32print.EndPagePrinter(handle)
        win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)


def run() -> None:
    config = load_config()
    api_base = config["api_base_url"].rstrip("/")
    printer_name = config.get("printer_name", "ZDesigner ZD888t")
    interval = int(config.get("poll_interval_s", 3))

    LOGGER.info("Iniciando agente para %s", printer_name)

    session = requests.Session()
    while True:
        try:
            resp = session.get(f"{api_base}/print/jobs", params={"status": "queued", "limit": 25})
            resp.raise_for_status()
            jobs = resp.json()
            for job in jobs:
                try:
                    LOGGER.info("Imprimiendo trabajo %s", job["id"])
                    send_raw_to_printer(printer_name, job["payload_zpl"])
                    session.post(f"{api_base}/print/jobs/{job['id']}/ack", json={"status": "sent"})
                except Exception as exc:  # pragma: no cover - manejo básico
                    LOGGER.exception("Error imprimiendo %s", job["id"])
                    session.post(
                        f"{api_base}/print/jobs/{job['id']}/ack",
                        json={"status": "error", "error": str(exc)},
                    )
        except Exception:  # pragma: no cover - logging
            LOGGER.exception("Error consultando trabajos")
        time.sleep(interval)


if __name__ == "__main__":  # pragma: no cover
    run()
