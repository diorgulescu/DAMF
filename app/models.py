from app import db

class Device(db.Model):
    name = db.Column(db.String(64), primary_key=True, index=True, unique=True)
    owner = db.Column(db.String(64), index=True)
    state = db.Column(db.String(32), index=True)
    deployed_image = db.Column(db.String(128), index=True)
    arch = db.Column(db.String(32), index=True)

    def __repr__(self):
        return '<Device {0}-{1}'.format(self.name, self.arch)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(128), index=True, unique=True)
    password_hash = db.Column(db.String(128))

    def __repr__(self):
        return '<User {}'.format(self.username)
