import os
import threading
import webbrowser
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory

import config
import models
import scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["UPLOAD_FOLDER"] = config.UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB

DAYS_ORDER = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
DAYS_LABELS = {
    "lunes": "Lun", "martes": "Mar", "miercoles": "Mié",
    "jueves": "Jue", "viernes": "Vie", "sabado": "Sáb", "domingo": "Dom"
}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS

def _save_audio(file, event_id):
    ext = file.filename.rsplit(".", 1)[1].lower()
    path = os.path.join(config.UPLOAD_FOLDER, f"event_{event_id}.{ext}")
    file.save(path)
    return path

def _delete_audio(path):
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except Exception as e:
            logging.warning(f"No se pudo eliminar el audio {path}: {e}")

def today_day_name():
    names = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    return names[datetime.now().weekday()]

@app.route("/")
def dashboard():
    now = datetime.now()
    today = today_day_name()
    all_events = models.get_all_events()
    today_events = [e for e in all_events if today in e["days"].split(",")]
    next_ev = scheduler.get_next_event()
    return render_template(
        "dashboard.html",
        now=now.strftime("%H:%M:%S"),
        today_label=today.capitalize(),
        today_events=today_events,
        next_event=next_ev,
        days_labels=DAYS_LABELS,
    )

@app.route("/events")
def events():
    all_events = models.get_all_events()
    return render_template("events.html", events=all_events, days_order=DAYS_ORDER, days_labels=DAYS_LABELS)

def _form_ctx(event, is_editing):
    return dict(event=event, is_editing=is_editing, days_order=DAYS_ORDER, days_labels=DAYS_LABELS)

def _parse_form():
    return {
        "name":     request.form.get("name", "").strip(),
        "time":     request.form.get("time", "").strip(),
        "days":     request.form.getlist("days"),
        "active":   1 if request.form.get("active") else 0,
        "volume":   float(request.form.get("volume", 1.0)),
        "duration": int(request.form.get("duration", 30) or 0),
    }

@app.route("/events/new", methods=["GET", "POST"])
def new_event():
    if request.method == "POST":
        f = _parse_form()
        prefill = {**f, "days_list": f["days"], "audio_path": None}

        if not f["name"] or not f["time"] or not f["days"]:
            flash("Nombre, hora y al menos un día son obligatorios.", "danger")
            return render_template("event_form.html", **_form_ctx(prefill, False))

        if models.name_exists(f["name"]):
            flash(f'Ya existe un evento con el nombre "{f["name"]}". Elige un nombre diferente.', "danger")
            return render_template("event_form.html", **_form_ctx(prefill, False))

        conflicts = models.time_day_conflicts(f["time"], f["days"])
        if conflicts:
            detalles = "; ".join(
                f'"{c["name"]}" ({", ".join(c["shared_days"])})' for c in conflicts
            )
            flash(f'Ya hay un evento programado a las {f["time"]} en esos días: {detalles}.', "danger")
            return render_template("event_form.html", **_form_ctx(prefill, False))

        event_id = models.create_event(f["name"], f["time"], f["days"], None, f["active"], f["volume"], f["duration"])
        file = request.files.get("audio")
        if file and file.filename and allowed_file(file.filename):
            audio_path = _save_audio(file, event_id)
            models.set_audio_path(event_id, audio_path)
        scheduler.reload_jobs()
        flash(f'Evento "{f["name"]}" creado correctamente.', "success")
        return redirect(url_for("events"))

    return render_template("event_form.html", **_form_ctx(None, False))

@app.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
def edit_event(event_id):
    event = models.get_event(event_id)
    if not event:
        flash("Evento no encontrado.", "danger")
        return redirect(url_for("events"))

    if request.method == "POST":
        f = _parse_form()
        prefill = {**event, **f, "days_list": f["days"]}

        if not f["name"] or not f["time"] or not f["days"]:
            flash("Nombre, hora y al menos un día son obligatorios.", "danger")
            return render_template("event_form.html", **_form_ctx(prefill, True))

        if models.name_exists(f["name"], exclude_id=event_id):
            flash(f'Ya existe otro evento con el nombre "{f["name"]}". Elige un nombre diferente.', "danger")
            return render_template("event_form.html", **_form_ctx(prefill, True))

        conflicts = models.time_day_conflicts(f["time"], f["days"], exclude_id=event_id)
        if conflicts:
            detalles = "; ".join(
                f'"{c["name"]}" ({", ".join(c["shared_days"])})' for c in conflicts
            )
            flash(f'Ya hay un evento programado a las {f["time"]} en esos días: {detalles}.', "danger")
            return render_template("event_form.html", **_form_ctx(prefill, True))

        audio_path = event["audio_path"]
        file = request.files.get("audio")
        if file and file.filename and allowed_file(file.filename):
            _delete_audio(audio_path)
            audio_path = _save_audio(file, event_id)

        models.update_event(event_id, f["name"], f["time"], f["days"], audio_path, f["active"], f["volume"], f["duration"])
        scheduler.reload_jobs()
        flash(f'Evento "{f["name"]}" actualizado.', "success")
        return redirect(url_for("events"))

    event["days_list"] = event["days"].split(",")
    return render_template("event_form.html", **_form_ctx(event, True))

@app.route("/events/<int:event_id>/toggle", methods=["POST"])
def toggle_event(event_id):
    models.toggle_event(event_id)
    scheduler.reload_jobs()
    return redirect(url_for("events"))

@app.route("/events/<int:event_id>/delete", methods=["POST"])
def delete_event(event_id):
    event = models.get_event(event_id)
    if event:
        _delete_audio(event["audio_path"])
        models.delete_event(event_id)
        scheduler.reload_jobs()
        flash(f'Evento "{event["name"]}" eliminado.', "warning")
    return redirect(url_for("events"))

@app.route("/events/<int:event_id>/test", methods=["POST"])
def test_sound(event_id):
    event = models.get_event(event_id)
    if not event or not event.get("audio_path"):
        return jsonify({"ok": False, "msg": "No hay audio configurado para este evento."})
    if not os.path.exists(event["audio_path"]):
        return jsonify({"ok": False, "msg": "El archivo de audio no existe en disco."})
    scheduler.play_audio(event["audio_path"], event.get("volume", 1.0), event.get("duration", 0))
    dur = event.get("duration", 0)
    msg = f"Reproduciendo audio — se detendrá en {dur}s" if dur else "Reproduciendo audio..."
    return jsonify({"ok": True, "msg": msg})

@app.errorhandler(413)
def file_too_large(e):
    flash("El archivo de audio es demasiado grande. El límite es 200 MB.", "danger")
    return redirect(request.referrer or url_for("events"))

@app.route("/stop-alarm", methods=["POST"])
def stop_alarm():
    scheduler.stop_audio()
    return jsonify({"ok": True, "msg": "Alarma detenida."})

@app.route("/api/status")
def api_status():
    now = datetime.now()
    next_ev = scheduler.get_next_event()
    return jsonify({
        "time": now.strftime("%H:%M:%S"),
        "date": now.strftime("%A, %d de %B de %Y"),
        "next_event": next_ev,
        "is_playing": scheduler.is_playing(),
    })

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(config.UPLOAD_FOLDER, filename)

def port_in_use(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((config.HOST, port)) == 0

def open_browser():
    import time
    time.sleep(1.2)
    webbrowser.open(f"http://{config.HOST}:{config.PORT}")

if __name__ == "__main__":
    if port_in_use(config.PORT):
        # Ya hay una instancia corriendo: solo abrir el navegador
        logging.info("La aplicación ya está en ejecución. Abriendo navegador...")
        webbrowser.open(f"http://{config.HOST}:{config.PORT}")
    else:
        models.init_db()
        scheduler.start_scheduler()
        threading.Thread(target=open_browser, daemon=True).start()
        app.run(host=config.HOST, port=config.PORT, debug=False, use_reloader=False)
