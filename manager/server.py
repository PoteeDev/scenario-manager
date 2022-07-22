from scenario import Score, Round, Settings
from flask import Flask, jsonify, request, make_response
from flask_apscheduler import APScheduler
from functools import wraps
import os
import jwt

app = Flask(__name__)
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()


def scenario_run():
    score = Score()
    round = Round()
    round.run()
    score.update_scoreboard(round.result)


def admin_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        token = None
        # jwt is passed in the request header
        auth_header = request.headers.get("Authorization")
        if auth_header:
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({"details": "Bearer token malformed"}), 401
        # return 401 if token is not passed
        if not token:
            return jsonify({"details": "Token is missing"}), 401

        try:
            # decoding the payload to fetch the stored details
            data = jwt.decode(token, os.getenv("ACCESS_SECRET"), algorithms=["HS256"])
            if data.get("user_id") != "admin":
                return jsonify({"details": "No access"}), 401
        except Exception as e:
            print(e)
            return jsonify({"details": "token is invalid"}), 401
        # returns the current logged in users contex to the routes
        return f(*args, **kwargs)

    return decorator


@app.route("/run")
@admin_required
def run():
    settings = Settings()
    scheduler.add_job(
        id="scenario",
        func=scenario_run,
        trigger="interval",
        seconds=int(settings.period),
    )
    return jsonify({"status": "runned"}), 200


@app.route("/pause")
@admin_required
def pause():
    scheduler.pause_job(id="scenario")
    return jsonify({"status": "paused"}), 200


@app.route("/resume")
@admin_required
def resume():
    scheduler.resume_job(id="scenario")
    return jsonify({"status": "resumed"}), 200


@app.route("/stop")
@admin_required
def stop():
    scheduler.remove_job(id="scenario")
    return jsonify({"status": "stopped"}), 200


app.run(host="0.0.0.0", port=8000)
