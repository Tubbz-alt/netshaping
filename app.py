import sys
import pathlib
import os

sys.path.append(str(pathlib.Path().absolute()))

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from celery import Celery

def make_celery(app):
    celery = Celery(
        app.import_name,
        backend='redis://localhost:6379',
        broker='redis://localhost:6379'
    )
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery

app = Flask(__name__)
celery = make_celery(app)
celery.conf.beat_schedule = {
    "policy-stats": {
        "task": "app.policy_stats",
        "schedule": 30.0
    }
}
app.config.update(DEBUG=True, SECRET_KEY=b"ACEDEJEADEJE")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database/database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)

from views import *
from datetime import datetime
from net import Connection

@celery.task
def policy_stats():
    try:
        f = open("task.txt", "r")
        if f.read() == 'unlocked': 
            print("— UNLOCKED CONFIRMED. RUNNING.")
            with open("task.txt", "w") as file:
                file.write("locked")
                print("TASK LOCKED")
            check_active_devices()
            interfaces = Interface.query.filter(Interface.policy_id != None).all()
            
            for interface in interfaces:
                device = interface.device
                router = Connection(device.host, username = device.ssh_username, password = device.ssh_password)
                snapshot = router.stats_policy_interface(interface.name)
                if snapshot['success'] == True and ('classes' in snapshot):
                    for class_name, stats in snapshot['classes'].items():
                        interface.policy_stats.append(
                            Stat(
                                created_on=datetime.now(),
                                policy_name=snapshot['output_policy'],
                                class_name=stats['class_name'], 
                                offered_rate = int(stats['offered_rate']), 
                                drop_rate = int(stats['drop_rate'])
                            )
                        )
                    interface.update()
            with open("task.txt", "w") as file:
                file.write("unlocked")
                print("TASK UNLOCKED")
        else:
            print("— LOCKED CONFIRMED. STOPPING.")
    except Exception as e:
        print(e)

def check_active_devices():
    devices = Device.query.all()
    for device in devices:
        connection = Connection(device.host, username=device.ssh_username, password=device.ssh_password)

        if connection.try_connection() == "success":
            device.state = "active"
        else:
            device.state = "inactive"
        device.update()