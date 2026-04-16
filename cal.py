#!/usr/bin/env python3
"""
sync_music.py â€” Script unificado de sincronizaciÃ³n musical
===========================================================

Fuente de verdad: los VTODOs del calendario de tareas (CALENDAR_TASKS).
  Â· SUMMARY   â†’ artist / album
  Â· DTSTART   â†’ purchase_date
  Â· COMPLETED â†’ listened_date  (si ya estÃ¡ en el VTODO, no se consulta Last.fm)

Flujo:
  1. Lee TODOS los VTODOs del calendario de tareas (CALENDAR_TASKS).
  2. Lee VEVENTs del calendario de lanzamientos (CALENDAR_NAME) en el rango --since,
     solo para obtener release_date y detectar Ã¡lbumes sin VTODO.
  3. Para VTODOs sin DUE â†’ asigna DUE = DTSTART + 3 meses.
  4. Para cada VEVENT en rango sin VTODO correspondiente â†’ crea VTODO en CALENDAR_TASKS.
  5. Para cada VTODO (loop principal):
       a. Cruza con VEVENTs para obtener release_date (puede ser None).
       b. Si purchase_date falta y Airsonic estÃ¡ configurado â†’ consulta Airsonic.
       c. Actualiza la DB con (release, purchase, listened) del VTODO.
       d. Si el VTODO ya tiene COMPLETED â†’ saltar paso Last.fm.
       e. Si no tiene listened_date â†’ busca tracklist en MusicBrainz y compara
          contra lastfm_stats.db; si hay escucha, marca VTODO COMPLETED + actualiza DB.

Uso:
    python sync_music.py              # solo hoy (--since 0)
    python sync_music.py --since 7   # Ãºltimos 7 dÃ­as
    python sync_music.py --dry-run   # solo muestra, no escribe nada

Variables en .env (ubicado junto al script o en el directorio raÃ­z):
    RADICALE_URL        â€” ej: http://localhost:5232
    RADICALE_USERNAME   â€” usuario Radicale
    RADICALE_PW         â€” contraseÃ±a Radicale
    RADICALE_CALENDAR   â€” ruta base del usuario en Radicale (ej: /usuario/)
    CALENDAR_NAME       â€” nombre/segmento del calendario de lanzamientos (ej: qwer)
    CALENDAR_TASKS      â€” nombre/segmento del calendario de tareas      (ej: asdf)
    LASTFM_DB           â€” ruta a lastfm_stats.db  (defecto: lastfm_stats.db)
    MUSIC_DB            â€” ruta a music_stats.db   (defecto: music_stats.db)
    STORE_CSV           â€” ruta a albums.csv       (defecto: albums.csv)
    MB_EMAIL            â€” email para User-Agent de MusicBrainz
    AIRSONIC_URL        â€” URL base de Airsonic  (ej: http://localhost:4040)
    AIRSONIC_USER       â€” usuario Airsonic
    AIRSONIC_PASS       â€” contraseÃ±a Airsonic
    AIRSONIC_API_VERSION â€” versiÃ³n API (defecto: 1.15.0)
"""

import argparse
import csv
import os
import re
import sqlite3
import sys
import time

from datetime import datetime, date, timezone, timedelta
from typing import Optional
from xml.etree import ElementTree as ET

import requests
from dotenv import load_dotenv
from icalendar import Calendar, vDatetime, vText

# â”€â”€ Certifi opcional â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    import certifi
    _MB_VERIFY = certifi.where()
except ImportError:
    _MB_VERIFY = True

# â”€â”€ Cargar .env (busca hacia arriba desde el script) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, ".env"))
load_dotenv(os.path.join(_HERE, "..", ".env"))  # tambiÃ©n raÃ­z del proyecto

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  CONFIGURACIÃ“N
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
RADICALE_URL      = os.getenv("RADICALE_URL",      "").rstrip("/")
RADICALE_USER     = os.getenv("RADICALE_USERNAME", "")
RADICALE_PW       = os.getenv("RADICALE_PW",       "")
RADICALE_BASE     = os.getenv("RADICALE_CALENDAR", "/")   # ej: /usuario/
CALENDAR_NAME     = os.getenv("CALENDAR_NAME",     "")    # calendario de lanzamientos
CALENDAR_TASKS    = os.getenv("CALENDAR_TASKS",    "")    # calendario de tareas

LASTFM_DB  = os.getenv("LASTFM_DB",  os.path.join(_HERE, "lastfm_stats.db"))
MUSIC_DB   = os.getenv("MUSIC_DB",   os.path.join(_HERE, "music_stats.db"))
STORE_CSV  = os.getenv("STORE_CSV",  os.path.join(_HERE, "albums.csv"))
MB_EMAIL   = os.getenv("MB_EMAIL",   "user@example.com")

AIRSONIC_URL         = os.getenv("AIRSONIC_URL",         "").rstrip("/")
AIRSONIC_USER        = os.getenv("AIRSONIC_USER",        "")
AIRSONIC_PASS        = os.getenv("AIRSONIC_PASS",        "")
AIRSONIC_API_VERSION = os.getenv("AIRSONIC_API_VERSION", "1.15.0")

MB_BASE       = "https://musicbrainz.org/ws/2/"
MB_UA         = f"SyncMusic/2.0 ({MB_EMAIL})"
MB_RATE_LIMIT = 1.5

# SesiÃ³n MB persistente (reutiliza conexiÃ³n TCP/SSL)
_mb_session = requests.Session()
_mb_session.headers.update({"User-Agent": MB_UA})
_mb_session.verify = _MB_VERIFY


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  HELPERS GENERALES
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _normalize(s: str) -> str:
    import unicodedata
    s = re.sub(r"\s+", " ", s.strip().lower())
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def strip_emojis(s: str) -> str:
    return re.sub(
        r"^[\U00010000-\U0010ffff\u2000-\u2bff\u2600-\u26ff\u2700-\u27bf\s]+"
        r"|[\U00010000-\U0010ffff\u2000-\u2bff\u2600-\u26ff\u2700-\u27bf\s]+$",
        "", s,
    ).strip()


def parse_summary(summary: str) -> tuple[str, str]:
    """'Artist - Album' â†’ (artist, album). Tolera â€”, â€“, -."""
    summary = strip_emojis(summary)
    parts = re.split(r"\s+[-â€“â€”]\s+", summary, maxsplit=1)
    if len(parts) == 2:
        return strip_emojis(parts[0]), strip_emojis(parts[1])
    return summary, ""


def parse_date_value(dt_val) -> Optional[date]:
    if dt_val is None:
        return None
    if hasattr(dt_val, "dt"):
        dt_val = dt_val.dt
    if isinstance(dt_val, datetime):
        return dt_val.date()
    if isinstance(dt_val, date):
        return dt_val
    return None


def days_between(d1: Optional[str], d2: Optional[str]) -> Optional[int]:
    if not d1 or not d2:
        return None
    try:
        return (date.fromisoformat(d2) - date.fromisoformat(d1)).days
    except ValueError:
        return None


def subtract_months(d: date, months: int) -> date:
    """Resta 'months' meses a una fecha, ajustando el dÃ­a si es necesario."""
    month = d.month - months
    year  = d.year
    while month <= 0:
        month += 12
        year  -= 1
    # Clamp day al mÃ¡ximo del mes resultante
    import calendar
    max_day = calendar.monthrange(year, month)[1]
    return d.replace(year=year, month=month, day=min(d.day, max_day))


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  CALDAV â€” HELPERS HTTP RAW
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _cal_url(cal_name: str) -> str:
    """Construye la URL completa del calendario dado su nombre/segmento."""
    base = RADICALE_BASE.rstrip("/")
    return f"{RADICALE_URL}{base}/{cal_name}/"


def fetch_calendar_items(cal_name: str) -> list[dict]:
    """
    Usa REPORT (calendar-query) para obtener todos los Ã­tems de un calendario.
    Devuelve lista de dicts: {href, ical_text}.
    """
    url = _cal_url(cal_name)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">'
        "  <D:prop><D:getetag/><C:calendar-data/></D:prop>"
        "  <C:filter><C:comp-filter name=\"VCALENDAR\"/></C:filter>"
        "</C:calendar-query>"
    )
    headers = {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"}
    r = requests.request(
        "REPORT", url,
        data=body.encode("utf-8"),
        headers=headers,
        auth=(RADICALE_USER, RADICALE_PW),
        timeout=30,
    )
    r.raise_for_status()

    ns = {"D": "DAV:", "C": "urn:ietf:params:xml:ns:caldav"}
    root = ET.fromstring(r.content)
    items = []
    for resp in root.findall(".//D:response", ns):
        href_el  = resp.find("D:href", ns)
        cal_data = resp.find(".//C:calendar-data", ns)
        if href_el is not None and cal_data is not None and cal_data.text:
            items.append({"href": href_el.text, "ical_text": cal_data.text})
    return items


def put_ical(href: str, ical_text: str, cal_name: Optional[str] = None) -> bool:
    """
    PUT un Ã­tem iCal. Devuelve True si OK.

    Radicale a veces devuelve hrefs con el UUID interno del calendario
    (ej: /usuario/a1b2c3-uuid-del-cal/item.ics) en lugar de la ruta
    nombrada (ej: /usuario/mi-calendario/item.ics). Usar esa ruta interna
    en el PUT puede dar 403 aunque el acceso estÃ© permitido sobre la ruta
    nombrada.

    Si se pasa `cal_name`, se reconstruye la URL usando ese nombre de
    calendario mÃ¡s el nombre de fichero del href original, garantizando
    que el PUT vaya a la ruta con permisos.
    """
    if cal_name:
        filename = os.path.basename(href.rstrip("/"))
        href = f"{RADICALE_BASE.rstrip('/')}/{cal_name}/{filename}"

    url = href if href.startswith("http") else RADICALE_URL + href
    headers = {"Content-Type": "text/calendar; charset=utf-8"}
    r = requests.put(
        url,
        data=ical_text.encode("utf-8"),
        headers=headers,
        auth=(RADICALE_USER, RADICALE_PW),
        timeout=30,
    )
    if r.status_code not in (200, 201, 204):
        print(f"    âš ï¸  PUT {href} â†’ HTTP {r.status_code}: {r.text[:120]}")
        return False
    return True


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  PARSEO DE ÃTEMS iCAL
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def parse_events(raw_items: list[dict], since_date: date) -> dict:
    """
    Extrae VEVENTs cuya DTSTART >= since_date.

    Retorna dict keyed por (artist_norm, album_norm):
        {artist, album, release_date (iso), href, uid, ical_text}
    """
    events: dict = {}
    for item in raw_items:
        try:
            cal = Calendar.from_ical(item["ical_text"])
        except Exception as e:
            print(f"  âš ï¸  Error parseando Ã­tem: {e}")
            continue
        for comp in cal.walk():
            if not hasattr(comp, "name") or comp.name != "VEVENT":
                continue
            summary = str(comp.get("SUMMARY", ""))
            if not summary:
                continue
            artist, album = parse_summary(summary)
            if not album:
                continue
            dt_start = parse_date_value(comp.get("DTSTART"))
            if dt_start is None or dt_start < since_date:
                continue
            key = (_normalize(artist), _normalize(album))
            events[key] = {
                "artist":       artist,
                "album":        album,
                "release_date": dt_start.isoformat(),
                "href":         item["href"],
                "uid":          str(comp.get("UID", "")),
                "ical_text":    item["ical_text"],
            }
    return events


def parse_tasks(raw_items: list[dict]) -> dict:
    """
    Extrae VTODOs.

    Retorna dict keyed por (artist_norm, album_norm):
        {artist, album, purchase_date, listened_date, completed, href, uid, ical_text, due}

    Si DTSTART falta pero DUE existe â†’ se registra; el caller aplica el fix de +3 meses.
    """
    tasks: dict = {}
    for item in raw_items:
        try:
            cal = Calendar.from_ical(item["ical_text"])
        except Exception as e:
            print(f"  âš ï¸  Error parseando tarea: {e}")
            continue
        for comp in cal.walk():
            if not hasattr(comp, "name") or comp.name != "VTODO":
                continue
            summary = str(comp.get("SUMMARY", ""))
            if not summary:
                continue
            artist, album = parse_summary(summary)
            if not album:
                continue

            dt_start  = parse_date_value(comp.get("DTSTART"))
            completed = parse_date_value(comp.get("COMPLETED"))
            due       = parse_date_value(comp.get("DUE"))
            status    = str(comp.get("STATUS", "")).upper()

            key = (_normalize(artist), _normalize(album))
            tasks[key] = {
                "artist":        artist,
                "album":         album,
                "purchase_date": (dt_start or due or None) and
                                 (dt_start or due).isoformat(),
                "listened_date": completed.isoformat() if completed else None,
                "completed":     completed is not None or status == "COMPLETED",
                "href":          item["href"],
                "uid":           str(comp.get("UID", "")),
                "ical_text":     item["ical_text"],
                "has_dtstart":   dt_start is not None,
                "due":           due.isoformat() if due else None,
            }
    return tasks


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  REPARACIÃ“N DE FECHAS EN VTODOS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def add_months(d: date, months: int) -> date:
    """Suma 'months' meses a una fecha, ajustando el dÃ­a si es necesario."""
    import calendar
    month = d.month + months
    year  = d.year
    while month > 12:
        month -= 12
        year  += 1
    max_day = calendar.monthrange(year, month)[1]
    return d.replace(year=year, month=month, day=min(d.day, max_day))


def fix_missing_dtstart(tasks: dict, dry_run: bool) -> int:
    """
    Para cada VTODO sin DTSTART pero con DUE, asigna DTSTART = DUE âˆ’ 3 meses
    tanto en Radicale como en el dict local.

    Retorna el nÃºmero de tareas corregidas.
    """
    fixed = 0
    for key, task in tasks.items():
        if task["has_dtstart"] or not task["due"]:
            continue

        due_date  = date.fromisoformat(task["due"])
        new_start = subtract_months(due_date, 3)
        print(f"  ðŸ”§ DTSTART faltante â†’ {task['artist']} â€” {task['album']}")
        print(f"     DUE={task['due']}  â†’  DTSTART calculado: {new_start.isoformat()}")

        if dry_run:
            print("     [DRY RUN] no se escribe")
            fixed += 1
            continue

        try:
            cal = Calendar.from_ical(task["ical_text"])
        except Exception as e:
            print(f"     âš ï¸  Error parseando iCal: {e}")
            continue

        updated_cal = Calendar()
        for k, v in cal.items():
            updated_cal.add(k, v)

        for comp in cal.walk():
            if hasattr(comp, "name") and comp.name == "VTODO":
                comp.add("DTSTART", new_start)
                comp["LAST-MODIFIED"] = vDatetime(datetime.now(tz=timezone.utc))
                updated_cal.add_component(comp)
            elif hasattr(comp, "name") and comp.name != "VCALENDAR":
                updated_cal.add_component(comp)

        ical_text = updated_cal.to_ical().decode("utf-8")
        if put_ical(task["href"], ical_text, cal_name=CALENDAR_TASKS):
            task["has_dtstart"]   = True
            task["purchase_date"] = new_start.isoformat()
            task["ical_text"]     = ical_text
            fixed += 1
            print("     âœ… Actualizado en Radicale")
        else:
            print("     âŒ Error actualizando en Radicale")

    return fixed


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  CREACIÃ“N Y ACTUALIZACIÃ“N DE VTODOS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def fix_missing_due(tasks: dict, dry_run: bool) -> int:
    """
    Para cada VTODO que tiene DTSTART pero carece de DUE, asigna
    DUE = DTSTART + 3 meses, tanto en Radicale como en el dict local.

    Retorna el nÃºmero de tareas corregidas.
    """
    fixed = 0
    for key, task in tasks.items():
        if task["due"] or not task["has_dtstart"] or not task["purchase_date"]:
            continue

        start_date = date.fromisoformat(task["purchase_date"])
        new_due    = add_months(start_date, 3)
        print(f"  ðŸ”§ DUE faltante â†’ {task['artist']} â€” {task['album']}")
        print(f"     DTSTART={task['purchase_date']}  â†’  DUE calculado: {new_due.isoformat()}")

        if dry_run:
            print("     [DRY RUN] no se escribe")
            fixed += 1
            continue

        try:
            cal = Calendar.from_ical(task["ical_text"])
        except Exception as e:
            print(f"     âš ï¸  Error parseando iCal: {e}")
            continue

        updated_cal = Calendar()
        for k, v in cal.items():
            updated_cal.add(k, v)

        for comp in cal.walk():
            if hasattr(comp, "name") and comp.name == "VTODO":
                comp.add("DUE", new_due)
                comp["LAST-MODIFIED"] = vDatetime(datetime.now(tz=timezone.utc))
                updated_cal.add_component(comp)
            elif hasattr(comp, "name") and comp.name != "VCALENDAR":
                updated_cal.add_component(comp)

        ical_text = updated_cal.to_ical().decode("utf-8")
        if put_ical(task["href"], ical_text, cal_name=CALENDAR_TASKS):
            task["due"]      = new_due.isoformat()
            task["ical_text"] = ical_text
            fixed += 1
            print("     âœ… Actualizado en Radicale")
        else:
            print("     âŒ Error actualizando en Radicale")

    return fixed


def update_vtodo_completed(task: dict, listened_date: date) -> bool:
    try:
        cal = Calendar.from_ical(task["ical_text"])
    except Exception as e:
        print(f"    âš ï¸  Error parseando VTODO: {e}")
        return False

    updated_cal = Calendar()
    for k, v in cal.items():
        updated_cal.add(k, v)

    for comp in cal.walk():
        if hasattr(comp, "name") and comp.name == "VTODO":
            comp["STATUS"] = vText("COMPLETED")
            listened_dt = datetime.combine(
                listened_date, datetime.min.time(), tzinfo=timezone.utc)
            if "COMPLETED" not in comp:
                comp.add("COMPLETED", listened_dt)
            else:
                comp["COMPLETED"] = vDatetime(listened_dt)
            comp["LAST-MODIFIED"] = vDatetime(datetime.now(tz=timezone.utc))
            updated_cal.add_component(comp)
        elif hasattr(comp, "name") and comp.name != "VCALENDAR":
            updated_cal.add_component(comp)

    return put_ical(task["href"], updated_cal.to_ical().decode("utf-8"), cal_name=CALENDAR_TASKS)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  CSV
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def load_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _csv_key(row: dict) -> tuple:
    artist = row.get("artist", row.get("artista", ""))
    album  = row.get("album",  row.get("Ã¡lbum", ""))
    return (_normalize(artist), _normalize(album))


def append_to_csv(path: str, artist: str, album: str, purchase_date: str):
    """AÃ±ade al CSV si el Ã¡lbum no existe. Crea cabecera si el fichero es nuevo."""
    existing = load_csv(path)
    key = (_normalize(artist), _normalize(album))
    if any(_csv_key(r) == key for r in existing):
        return
    file_exists = os.path.exists(path) and os.path.getsize(path) > 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["artist", "album", "purchase_date"])
        writer.writerow([artist, album, purchase_date])
    print(f"    ðŸ“‹ CSV: aÃ±adido {artist} â€” {album} ({purchase_date})")


def reclassify_csv_manual(csv_path: str,
                          manual_keys: set[tuple],
                          dry_run: bool):
    """
    Lee albums.csv y, para las entradas cuya clave (artist_norm, album_norm)
    estÃ© en manual_keys, cambia su type de 'vevent' a 'manual'.
    No aÃ±ade ni elimina filas, solo actualiza el campo type.
    """
    if not os.path.exists(csv_path):
        print(f"  âš ï¸  {csv_path} no existe")
        return

    rows = load_csv(csv_path)
    changed = 0
    for row in rows:
        row.setdefault("type", "vevent")
        if _csv_key(row) in manual_keys and row["type"] != "manual":
            row["type"] = "manual"
            changed += 1
            print(f"  veventâ†’manual: {row.get('artist')} â€” {row.get('album')}")

    print(f"\n  Entradas reclasificadas: {changed} | Total en CSV: {len(rows)}")

    if dry_run:
        print("  [DRY RUN] no se escribe")
        return

    sample = rows[0] if rows else {}
    fieldnames = [k for k in sample if k != "type"] + ["type"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  âœ… {csv_path} actualizado")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  AIRSONIC
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def search_airsonic(artist: str, album: str) -> Optional[date]:
    """
    Busca el Ã¡lbum en Airsonic y devuelve la fecha en que fue aÃ±adido a la
    biblioteca (campo `created`), o None si no se encuentra o Airsonic no
    estÃ¡ configurado.

    La fecha `created` equivale a cuÃ¡ndo el disco estuvo disponible en la
    biblioteca local, lo que usamos como aproximaciÃ³n de la fecha de compra.
    """
    if not AIRSONIC_URL or not AIRSONIC_USER:
        return None

    params = {
        "u": AIRSONIC_USER,
        "p": AIRSONIC_PASS,
        "v": AIRSONIC_API_VERSION,
        "c": "sync_music",
        "f": "json",
        "query": album,
        "albumCount": 50,
        "albumOffset": 0,
        "artistCount": 0,
        "songCount": 0,
    }

    try:
        r = requests.get(
            f"{AIRSONIC_URL}/rest/search3",
            params=params,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"    âš ï¸  Airsonic: error de conexiÃ³n â€” {e}")
        return None

    if data.get("subsonic-response", {}).get("status") != "ok":
        print(f"    âš ï¸  Airsonic: respuesta no OK â€” {data}")
        return None

    albums = (
        data.get("subsonic-response", {})
            .get("searchResult3", {})
            .get("album", [])
    )
    if not albums:
        return None

    artist_n = _normalize(artist)
    album_n  = _normalize(album)

    best_date: Optional[date] = None

    for found in albums:
        found_artist = _normalize(found.get("artist", ""))
        found_name   = _normalize(found.get("name",   ""))

        # Coincidencia exacta o el Ã¡lbum estÃ¡ contenido en el nombre encontrado
        artist_match = found_artist == artist_n
        album_match  = found_name == album_n or album_n in found_name

        if not (artist_match and album_match):
            continue

        created_raw = found.get("created", "")
        if not created_raw:
            return date.today()   # encontrado pero sin fecha â†’ usar hoy

        try:
            # Airsonic devuelve ISO 8601: "2024-03-15T00:00:00" o "2024-03-15"
            created_date = datetime.fromisoformat(created_raw.rstrip("Z")).date()
        except ValueError:
            created_date = date.today()

        # Si hay varias coincidencias nos quedamos con la mÃ¡s antigua
        if best_date is None or created_date < best_date:
            best_date = created_date

    return best_date


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  MUSICBRAINZ
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_mb_last_call: float = 0.0
_LUCENE_SPECIAL = re.compile(r'([\+\-\!\(\)\{\}\[\]\^"~\*\?:\\\/])')


def _mb_escape(s: str) -> str:
    return _LUCENE_SPECIAL.sub(r"\\\1", s)


def mb_get(endpoint: str, params: dict, _attempt: int = 0) -> Optional[dict]:
    global _mb_last_call, _mb_session

    MAX_RETRIES = 5
    elapsed = time.time() - _mb_last_call
    if elapsed < MB_RATE_LIMIT:
        time.sleep(MB_RATE_LIMIT - elapsed)

    try:
        r = _mb_session.get(
            MB_BASE + endpoint,
            params={**params, "fmt": "json"},
            timeout=60,
        )
    except (requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.SSLError,
            requests.exceptions.ChunkedEncodingError) as exc:
        _mb_last_call = time.time()
        if _attempt >= MAX_RETRIES:
            print(f"\n    âš ï¸  MB: error de red tras {MAX_RETRIES} reintentos ({exc.__class__.__name__})")
            return None
        wait = 5 * (2 ** _attempt)
        print(f"\n    MB: reintento {_attempt+1}/{MAX_RETRIES} en {wait}s...", end="", flush=True)
        if isinstance(exc, requests.exceptions.SSLError):
            _mb_session.close()
            _mb_session = requests.Session()
            _mb_session.headers.update({"User-Agent": MB_UA})
            _mb_session.verify = _MB_VERIFY
        time.sleep(wait)
        return mb_get(endpoint, params, _attempt=_attempt + 1)

    _mb_last_call = time.time()

    if r.status_code == 400:
        print(f"\n    âš ï¸  MB: HTTP 400 â€” query invÃ¡lida, se omite")
        return None
    if r.status_code == 404:
        return None
    if r.status_code in (429, 503):
        wait = max(int(r.headers.get("Retry-After", 10 * (2 ** _attempt))), 10)
        if _attempt >= MAX_RETRIES:
            print(f"\n    âš ï¸  MB: HTTP {r.status_code} persistente, se omite")
            return None
        print(f"\n    MB: rate-limit {r.status_code}, esperando {wait}s...", end="", flush=True)
        time.sleep(wait)
        return mb_get(endpoint, params, _attempt=_attempt + 1)
    if r.status_code in (500, 502, 504):
        wait = 5 * (2 ** _attempt)
        if _attempt >= MAX_RETRIES:
            print(f"\n    âš ï¸  MB: HTTP {r.status_code} persistente, se omite")
            return None
        print(f"\n    MB: error {r.status_code}, reintento {_attempt+1} en {wait}s...", end="", flush=True)
        time.sleep(wait)
        return mb_get(endpoint, params, _attempt=_attempt + 1)

    r.raise_for_status()
    return r.json()


def get_tracklist(artist: str, album: str) -> list[str]:
    """Retorna lista de tÃ­tulos normalizados de las pistas del Ã¡lbum, o []."""
    a_q = _mb_escape(artist)
    b_q = _mb_escape(album)

    data = mb_get("release", {"query": f'artist:"{a_q}" AND release:"{b_q}"', "limit": 3})
    if not data or not data.get("releases"):
        data = mb_get("release", {"query": f'release:"{b_q}" AND artist:"{a_q}"', "limit": 5})

    if not data or not data.get("releases"):
        print(f"    â„¹ï¸  MusicBrainz: no encontrado '{artist} â€” {album}'")
        return []

    releases = data["releases"]
    best = next((r for r in releases if str(r.get("score", 0)) == "100"), releases[0])
    mbid = best.get("id")
    if not mbid:
        return []

    detail = mb_get(f"release/{mbid}", {"inc": "recordings"})
    if not detail:
        return []

    tracks = []
    for medium in detail.get("media", []):
        for track in medium.get("tracks", []):
            title = track.get("title") or (track.get("recording") or {}).get("title", "")
            if title:
                tracks.append(_normalize(title))

    print(f"    ðŸŽµ MusicBrainz: {len(tracks)} pistas para '{artist} â€” {album}'")
    return tracks


def get_release_date_from_mb(artist: str, album: str) -> Optional[str]:
    """
    Busca la fecha de lanzamiento en MusicBrainz.
    Retorna fecha ISO (YYYY-MM-DD) o None si no la encuentra.
    Fechas parciales (YYYY o YYYY-MM) se completan con -01.
    """
    a_q = _mb_escape(artist)
    b_q = _mb_escape(album)

    data = mb_get("release", {"query": f'artist:"{a_q}" AND release:"{b_q}"', "limit": 5})
    if not data or not data.get("releases"):
        data = mb_get("release", {"query": f'release:"{b_q}" AND artist:"{a_q}"', "limit": 5})

    if not data or not data.get("releases"):
        return None

    releases = data["releases"]
    best = next((r for r in releases if str(r.get("score", 0)) == "100"), releases[0])

    raw = best.get("date", "").strip()
    if not raw:
        return None

    parts = raw.split("-")
    if len(parts) == 1:
        return f"{parts[0]}-01-01"
    if len(parts) == 2:
        return f"{parts[0]}-{parts[1]}-01"
    return raw


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  LASTFM DB
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def find_first_listen(lastfm_conn: sqlite3.Connection,
                      artist: str, tracks: list[str],
                      min_date: Optional[date] = None) -> Optional[date]:
    if not tracks:
        return None

    artist_key = _normalize(artist)
    row = lastfm_conn.execute(
        "SELECT artist_id FROM artists WHERE name_normalized = ?", (artist_key,)
    ).fetchone()
    if not row:
        row = lastfm_conn.execute(
            "SELECT artist_id FROM artists WHERE name_normalized LIKE ?",
            (f"%{artist_key}%",)
        ).fetchone()
    if not row:
        print(f"    â„¹ï¸  Last.fm DB: '{artist}' no encontrado")
        return None

    artist_id = row[0]
    placeholders = ",".join("?" * len(tracks))
    result = lastfm_conn.execute(
        f"SELECT MIN(ts), MIN(ts_iso) FROM scrobbles "
        f"WHERE artist_id = ? AND track_normalized IN ({placeholders})",
        [artist_id, *tracks],
    ).fetchone()

    if result and result[0]:
        try:
            return datetime.fromisoformat(result[1]).date()
        except Exception:
            return datetime.fromtimestamp(result[0], tz=timezone.utc).date()

    # BÃºsqueda fuzzy por la primera palabra significativa de cada pista
    earliest: Optional[date] = None
    for track in tracks[:10]:
        words = [w for w in track.split() if len(w) > 3]
        if not words:
            continue
        res = lastfm_conn.execute(
            "SELECT MIN(ts), MIN(ts_iso) FROM scrobbles "
            "WHERE artist_id = ? AND track_normalized LIKE ?",
            (artist_id, f"%{words[0]}%"),
        ).fetchone()
        if res and res[0]:
            try:
                d = datetime.fromisoformat(res[1]).date()
            except Exception:
                d = datetime.fromtimestamp(res[0], tz=timezone.utc).date()
            if earliest is None or d < earliest:
                earliest = d


    if result and result[0]:
        try:
            found = datetime.fromisoformat(result[1]).date()
        except Exception:
            found = datetime.fromtimestamp(result[0], tz=timezone.utc).date()
        if min_date and found < min_date:
            print(f"    âš ï¸  Scrobble ignorado ({found}) anterior al lanzamiento ({min_date})")
            return None          # â† descarta falso positivo
        return found

    if min_date and earliest and earliest < min_date:
        print(f"    âš ï¸  Scrobble fuzzy ignorado ({earliest}) anterior al lanzamiento ({min_date})")
        return None
    return earliest


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  MUSIC_STATS DB
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

SCHEMA = """
CREATE TABLE IF NOT EXISTS artists (
    artist_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    name_normalized TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS genres (
    genre_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    name_normalized TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS artist_genres (
    artist_id   INTEGER NOT NULL REFERENCES artists(artist_id),
    genre_id    INTEGER NOT NULL REFERENCES genres(genre_id),
    PRIMARY KEY (artist_id, genre_id)
);

CREATE TABLE IF NOT EXISTS albums (
    album_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_id                 INTEGER NOT NULL REFERENCES artists(artist_id),
    genre_id                  INTEGER REFERENCES genres(genre_id),
    name                      TEXT NOT NULL,
    name_normalized           TEXT NOT NULL,
    release_date              TEXT,
    purchase_date             TEXT,
    listened_date             TEXT,
    days_release_to_purchase  INTEGER,
    days_purchase_to_listened INTEGER,
    UNIQUE(artist_id, name_normalized)
);
"""


def init_db(conn: sqlite3.Connection):
    conn.executescript(SCHEMA)
    conn.commit()


def _sanitize_chain(release_date:  Optional[str],
                    purchase_date: Optional[str],
                    listened_date: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Garantiza que la cadena release â‰¤ purchase â‰¤ listened.
    Cualquier fecha que sea anterior a release_date se descarta (se deja None).
    Esto evita que reediciones/remasters con fecha reciente sobreescriban
    fechas de compra o escucha que son legÃ­timamente anteriores al re-lanzamiento.
    """
    ref = release_date  # ancla: todo lo que venga antes, fuera

    def after_or_none(d: Optional[str]) -> Optional[str]:
        if not d or not ref:
            return d
        try:
            return d if date.fromisoformat(d) >= date.fromisoformat(ref) else None
        except ValueError:
            return d

    clean_purchase = after_or_none(purchase_date)
    clean_listened = after_or_none(listened_date)
    return release_date, clean_purchase, clean_listened


def upsert_album(conn: sqlite3.Connection,
                 artist: str, album: str,
                 release_date:  Optional[str],
                 purchase_date: Optional[str],
                 listened_date: Optional[str]):
    """Inserta o actualiza el Ã¡lbum en music_stats.db."""
    release_date, purchase_date, listened_date = _sanitize_chain(
        release_date, purchase_date, listened_date
    )
    if purchase_date is None and listened_date is None and release_date is None:
        return  # nada Ãºtil que guardar

    artist_key = _normalize(artist)
    album_key  = _normalize(album)

    row = conn.execute(
        "SELECT artist_id FROM artists WHERE name_normalized = ?", (artist_key,)
    ).fetchone()
    if row:
        artist_id = row[0]
    else:
        artist_id = conn.execute(
            "INSERT INTO artists (name, name_normalized) VALUES (?, ?)",
            (artist, artist_key)
        ).lastrowid

    existing = conn.execute(
        """SELECT album_id, release_date, purchase_date, listened_date
           FROM albums WHERE artist_id = ? AND name_normalized = ?""",
        (artist_id, album_key)
    ).fetchone()

    if existing is None:
        conn.execute(
            """INSERT INTO albums
               (artist_id, name, name_normalized,
                release_date, purchase_date, listened_date,
                days_release_to_purchase, days_purchase_to_listened)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                artist_id, album, album_key,
                release_date, purchase_date, listened_date,
                days_between(release_date, purchase_date),
                days_between(purchase_date, listened_date),
            )
        )
    else:
        al_id, old_rel, old_pur, old_lis = existing
        new_rel = release_date  or old_rel
        new_pur = purchase_date or old_pur
        new_lis = listened_date or old_lis
        if (new_rel, new_pur, new_lis) != (old_rel, old_pur, old_lis):
            conn.execute(
                """UPDATE albums SET
                   release_date              = ?,
                   purchase_date             = ?,
                   listened_date             = ?,
                   days_release_to_purchase  = ?,
                   days_purchase_to_listened = ?
                   WHERE album_id = ?""",
                (
                    new_rel, new_pur, new_lis,
                    days_between(new_rel, new_pur),
                    days_between(new_pur, new_lis),
                    al_id,
                )
            )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  MAIN
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def main():
    parser = argparse.ArgumentParser(
        description="Sincroniza lanzamientos del calendario con tareas, "
                    "Last.fm y la base de datos. "
                    "Fuente de verdad: VTODOs del calendario de tareas."
    )
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument(
        "--since", type=int, metavar="DÃAS",
        help="Procesar VTODOs de los Ãºltimos N dÃ­as"
    )
    date_group.add_argument(
        "--all-data", action="store_true",
        help="Procesar todos los VTODOs sin lÃ­mite de fecha"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Solo muestra quÃ© harÃ­a, sin escribir nada"
    )
    parser.add_argument(
        "--manual-tasks", action="store_true",
        help="Detecta VTODOs sin VEVENT (compras manuales) y los aÃ±ade al albums.csv con type=manual"
    )
    args = parser.parse_args()

    if args.all_data:
        since_date = date.min
        since_label = "todos los datos"
    elif args.since:
        since_date = date.today() - timedelta(days=args.since)
        since_label = f"Ãºltimos {args.since} dÃ­as (desde {since_date.isoformat()})"
    else:
        since_date = date.today()
        since_label = f"solo hoy ({since_date.isoformat()})"

    print(f"ðŸŽµ sync_music.py â€” {since_label}"
          f"{' [DRY RUN]' if args.dry_run else ''}")
    print("=" * 60)

    # Validaciones
    missing = [v for v in ("RADICALE_URL", "RADICALE_USERNAME", "CALENDAR_NAME", "CALENDAR_TASKS")
               if not os.getenv(v)]
    if missing:
        print(f"âŒ Variables de entorno faltantes en .env: {', '.join(missing)}")
        sys.exit(1)

    # â”€â”€ 1. Descargar calendarios â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\nðŸ“‹ Leyendo calendario de tareas ({CALENDAR_TASKS})...")
    try:
        raw_tasks = fetch_calendar_items(CALENDAR_TASKS)
        print(f"   {len(raw_tasks)} Ã­tems descargados")
    except Exception as e:
        print(f"  âŒ Error CalDAV (tareas): {e}")
        sys.exit(1)

    print(f"\nðŸ“… Leyendo calendario de lanzamientos ({CALENDAR_NAME})...")
    try:
        raw_events = fetch_calendar_items(CALENDAR_NAME)
        print(f"   {len(raw_events)} Ã­tems descargados")
    except Exception as e:
        print(f"  âŒ Error CalDAV (eventos): {e}")
        sys.exit(1)

    # â”€â”€ 2. Parsear â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print("\nðŸ” Clasificando VEVENTs y VTODOs...")
    # VEVENTs: todos (sin filtro de fecha) para poder cruzar release_date con
    # cualquier VTODO, no solo los del rango --since.
    events_all = parse_events(raw_events, date.min)   # sin filtro de fecha
    tasks = parse_tasks(raw_tasks)
    print(f"   VEVENTs total:      {len(events_all)}")
    print(f"   VTODOs total:       {len(tasks)}")

    # â”€â”€ 3. Reparar VTODOs sin DUE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print("\nðŸ”§ Comprobando VTODOs sin DUE...")
    fixed_due = fix_missing_due(tasks, dry_run=args.dry_run)
    if fixed_due:
        print(f"   {fixed_due} VTODO(s) corregidos (DUE = DTSTART + 3 meses)")
    else:
        print("   Sin VTODOs que reparar")

    # â”€â”€ 4. Abrir DBs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    stats = {"listened_updated": 0, "already_ok": 0,
             "no_listen": 0, "airsonic_found": 0, "db_updated": 0}
    lastfm_conn: Optional[sqlite3.Connection] = None
    if os.path.exists(LASTFM_DB):
        lastfm_conn = sqlite3.connect(LASTFM_DB)
        lastfm_conn.execute("PRAGMA journal_mode=WAL")
        print(f"\nðŸ’¾ Last.fm DB: {LASTFM_DB}")
    else:
        print(f"\nâš ï¸  Last.fm DB no encontrada en {LASTFM_DB!r} â€” se omitirÃ¡ fecha de escucha")

    music_conn = sqlite3.connect(MUSIC_DB)
    music_conn.execute("PRAGMA foreign_keys=ON")
    music_conn.execute("PRAGMA journal_mode=WAL")
    init_db(music_conn)

    # â”€â”€ 6. Loop principal: un VTODO a la vez â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\nâš™ï¸  Procesando {len(tasks)} VTODO(s) como fuente de verdad...")
    for key, task in tasks.items():
        artist        = task["artist"]
        album         = task["album"]
        # Fechas directamente del VTODO (fuente de verdad)
        purchase_date = task.get("purchase_date")   # DTSTART del VTODO
        listened_date = task.get("listened_date")   # COMPLETED del VTODO
        is_completed  = task.get("completed", False)

        # Filtrar por rango de fechas (purchase_date como referencia)
        if purchase_date and since_date != date.min:
            try:
                if date.fromisoformat(purchase_date) < since_date:
                    continue
            except ValueError:
                pass

        # release_date: del VEVENT cruzado por nombre (puede ser None)
        ev           = events_all.get(key)
        release_date = ev["release_date"] if ev else None

        if release_date is None:
            print(f"\n  ðŸŽ¸ {artist} â€” {album}  (sin VEVENT, buscando en MusicBrainz...)")
            release_date = get_release_date_from_mb(artist, album)
            if release_date:
                print(f"    ðŸ“… MusicBrainz: lanzamiento el {release_date}")
            else:
                print(f"    â“ No encontrado en MusicBrainz")
                user_input = input(
                    f"    Fecha de lanzamiento para '{artist} â€” {album}'"
                    f" (YYYY-MM-DD, vacÃ­o para omitir): "
                ).strip()
                release_date = user_input or None

        print(f"\n  ðŸŽ¸ {artist} â€” {album}"
              f"  (release={release_date or '?'}"
              f"  purchase={purchase_date or '?'}"
              f"  listened={listened_date or '?'})")

        # â”€â”€ 6a. CSV: registrar si no existe â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if purchase_date and not args.dry_run:
            append_to_csv(STORE_CSV, artist, album, purchase_date)

        # â”€â”€ 6b. Fecha de compra desde Airsonic (solo si DTSTART falta) â”€â”€â”€â”€â”€â”€â”€
        if not purchase_date and AIRSONIC_URL:
            print(f"    ðŸ” Sin DTSTART/purchase â†’ consultando Airsonic...")
            airsonic_date = search_airsonic(artist, album)
            if airsonic_date:
                print(f"    ðŸ›’ Airsonic: aÃ±adido el {airsonic_date.isoformat()}")
                if not args.dry_run and task.get("ical_text"):
                    try:
                        cal = Calendar.from_ical(task["ical_text"])
                        updated_cal = Calendar()
                        for k, v in cal.items():
                            updated_cal.add(k, v)
                        for comp in cal.walk():
                            if hasattr(comp, "name") and comp.name == "VTODO":
                                comp["DTSTART"] = vDatetime(
                                    datetime.combine(airsonic_date,
                                                     datetime.min.time(),
                                                     tzinfo=timezone.utc)
                                )
                                comp["LAST-MODIFIED"] = vDatetime(
                                    datetime.now(tz=timezone.utc))
                                updated_cal.add_component(comp)
                            elif hasattr(comp, "name") and comp.name != "VCALENDAR":
                                updated_cal.add_component(comp)
                        new_ical = updated_cal.to_ical().decode("utf-8")
                        if put_ical(task["href"], new_ical, cal_name=CALENDAR_TASKS):
                            task["ical_text"]     = new_ical
                            task["purchase_date"] = airsonic_date.isoformat()
                            task["has_dtstart"]   = True
                            purchase_date         = airsonic_date.isoformat()
                            print(f"    âœ… VTODO DTSTART actualizado con fecha Airsonic")
                    except Exception as e:
                        print(f"    âš ï¸  Error actualizando VTODO con fecha Airsonic: {e}")
                    append_to_csv(STORE_CSV, artist, album, airsonic_date.isoformat())
                elif args.dry_run:
                    print(f"    [DRY RUN] pondrÃ­a DTSTART={airsonic_date.isoformat()} en VTODO")
                    purchase_date = airsonic_date.isoformat()
                stats["airsonic_found"] += 1
            else:
                print(f"    â„¹ï¸  No encontrado en Airsonic")

        # â”€â”€ 6c. Actualizar DB con lo que tenemos del VTODO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        upsert_album(music_conn, artist, album,
                     release_date, purchase_date, listened_date)
        music_conn.commit()
        stats["db_updated"] += 1

        # â”€â”€ 6d. Si el VTODO ya estÃ¡ completado â†’ no consultar Last.fm â”€â”€â”€â”€â”€â”€â”€â”€
        if is_completed:
            print(f"    âœ”ï¸  Ya completado: {listened_date}")
            stats["already_ok"] += 1
            continue

        # â”€â”€ 6e. Buscar primera escucha en Last.fm â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if lastfm_conn is None:
            stats["no_listen"] += 1
            continue

        tracks = get_tracklist(artist, album)
        if not tracks:
            stats["no_listen"] += 1
            continue

        min_date = date.fromisoformat(release_date) if release_date else None
        first_listen = find_first_listen(lastfm_conn, artist, tracks, min_date=min_date)

        if first_listen is None:
            print(f"    â„¹ï¸  Sin escuchas en Last.fm todavÃ­a")
            stats["no_listen"] += 1
            continue

        print(f"    ðŸŽ§ Primera escucha: {first_listen.isoformat()}")

        if not args.dry_run and task.get("ical_text"):
            ok = update_vtodo_completed(task, first_listen)
            if ok:
                print(f"    âœ… VTODO marcado COMPLETED")
                stats["listened_updated"] += 1
                upsert_album(music_conn, artist, album,
                             release_date, purchase_date, first_listen.isoformat())
                music_conn.commit()
        elif args.dry_run:
            print(f"    [DRY RUN] pondrÃ­a COMPLETED={first_listen.isoformat()}")
            stats["listened_updated"] += 1

    # â”€â”€ 7. Reclasificar entradas manuales en el CSV â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if args.manual_tasks:
        manual_keys = {key for key in tasks if key not in events_all}
        print(f"\nðŸ“‹ --manual-tasks: {len(manual_keys)} VTODO(s) sin VEVENT")
        reclassify_csv_manual(STORE_CSV, manual_keys, dry_run=args.dry_run)

    # â”€â”€ 8. Resumen â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print("\n" + "=" * 60)
    print("ðŸ“Š Resumen:")
    print(f"   VTODOs procesados:         {stats['db_updated']}")
    print(f"   Fechas de escucha nuevas:  {stats['listened_updated']}")
    print(f"   Ya completados:            {stats['already_ok']}")
    print(f"   Sin escucha en Last.fm:    {stats['no_listen']}")
    print(f"   Fecha compra de Airsonic:  {stats['airsonic_found']}")
    print(f"   DUE reparados:             {fixed_due}")

    if lastfm_conn:
        lastfm_conn.close()
    music_conn.close()
    print("\nâœ… Â¡Hecho!")


if __name__ == "__main__":
    main()
