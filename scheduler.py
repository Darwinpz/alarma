import threading
import logging
import pygame
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import models

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(timezone="America/Guayaquil")
_play_lock = threading.Lock()
_mixer_ready = False
_stop_timer = None
_current_channel = None
_sound_cache: dict[str, pygame.mixer.Sound] = {}  # path → Sound ya decodificado en RAM

DAY_MAP = {
    "lunes": "mon",
    "martes": "tue",
    "miercoles": "wed",
    "jueves": "thu",
    "viernes": "fri",
    "sabado": "sat",
    "domingo": "sun",
}

def _init_mixer():
    global _mixer_ready
    try:
        pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
        pygame.mixer.init()
        freq, size, ch = pygame.mixer.get_init()
        logger.info(f"pygame.mixer iniciado — freq={freq}Hz size={size} canales={ch}")
        _mixer_ready = True
    except Exception as e:
        logger.error(f"No se pudo inicializar pygame.mixer: {e}")
        _mixer_ready = False

def _preload_sounds(events):
    """Decodifica todos los audios a PCM en memoria para reproducción sin latencia."""
    global _sound_cache
    import os
    new_cache: dict[str, pygame.mixer.Sound] = {}
    for ev in events:
        path = ev.get("audio_path")
        if not path or not os.path.isfile(path):
            continue
        if path in new_cache:
            continue
        try:
            new_cache[path] = pygame.mixer.Sound(path)
            logger.info(f"Audio precargado en RAM: {ev['name']}")
        except Exception as e:
            logger.warning(f"No se pudo precargar '{ev['name']}': {e}")
    _sound_cache = new_cache

def stop_audio():
    global _stop_timer, _current_channel
    if _stop_timer:
        _stop_timer.cancel()
        _stop_timer = None
    if not _mixer_ready:
        return
    try:
        if _current_channel is not None:
            _current_channel.stop()
            _current_channel = None
        logger.info("Audio detenido")
    except Exception as e:
        logger.error(f"Error deteniendo audio: {e}")

def is_playing():
    if not _mixer_ready or _current_channel is None:
        return False
    try:
        return bool(_current_channel.get_busy())
    except Exception:
        return False

def play_audio(audio_path, volume=1.0, duration=0):
    global _stop_timer, _current_channel

    def _play():
        global _stop_timer, _current_channel
        if not _mixer_ready:
            logger.warning("Mixer no disponible")
            return
        with _play_lock:
            try:
                if _stop_timer:
                    _stop_timer.cancel()
                    _stop_timer = None
                if _current_channel is not None and _current_channel.get_busy():
                    _current_channel.stop()

                # Usar caché si está disponible; si no, cargar y cachear ahora
                sound = _sound_cache.get(audio_path)
                if sound is None:
                    logger.info(f"Audio no estaba en caché, cargando: {audio_path}")
                    sound = pygame.mixer.Sound(audio_path)
                    _sound_cache[audio_path] = sound

                sound.set_volume(float(volume))
                _current_channel = sound.play()

                if duration and duration > 0:
                    _stop_timer = threading.Timer(duration, stop_audio)
                    _stop_timer.daemon = True
                    _stop_timer.start()
                    logger.info(f"Audio iniciado — se detendrá en {duration}s")
                else:
                    logger.info("Audio iniciado")
            except Exception as e:
                logger.error(f"Error reproduciendo audio {audio_path}: {e}")

    threading.Thread(target=_play, daemon=True).start()

def _make_job(event):
    def job():
        logger.info(f"Ejecutando evento: {event['name']}")
        if event.get("audio_path"):
            play_audio(event["audio_path"], event.get("volume", 1.0), event.get("duration", 0))
    return job

def _day_list_to_cron(days_str):
    day_names = [d.strip() for d in days_str.split(",") if d.strip()]
    return ",".join(DAY_MAP[d] for d in day_names if d in DAY_MAP)

def reload_jobs():
    _scheduler.remove_all_jobs()
    events = models.get_all_events()
    if _mixer_ready:
        _preload_sounds(events)  # recarga la caché con todos los eventos (activos e inactivos)
    for ev in events:
        if not ev["active"] or not ev.get("audio_path"):
            continue
        try:
            hour, minute = ev["time"].split(":")
            dow = _day_list_to_cron(ev["days"])
            if not dow:
                continue
            trigger = CronTrigger(hour=int(hour), minute=int(minute), day_of_week=dow)
            _scheduler.add_job(
                _make_job(ev),
                trigger=trigger,
                id=f"event_{ev['id']}",
                name=ev["name"],
                replace_existing=True,
            )
            logger.info(f"Job registrado: {ev['name']} a las {ev['time']} en {dow}")
        except Exception as e:
            logger.error(f"Error registrando job para evento {ev['id']}: {e}")

def get_next_event():
    jobs = _scheduler.get_jobs()
    if not jobs:
        return None
    next_job = min(
        jobs,
        key=lambda j: j.next_run_time or __import__("datetime").datetime.max.replace(
            tzinfo=__import__("datetime").timezone.utc
        ),
    )
    return {
        "name": next_job.name,
        "next_run": next_job.next_run_time.strftime("%H:%M") if next_job.next_run_time else "—",
    }

def start_scheduler():
    _init_mixer()
    reload_jobs()
    _scheduler.start()
    logger.info("Scheduler iniciado")

def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
