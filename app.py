from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

DB_USER = 'root'
DB_PASSWORD = 'jaideep'
DB_HOST = 'localhost'
DB_NAME = 'boskopartnersdb'

# Configuring SQLAlchemy connection to MySQL Database.
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Models

class Organization(db.Model):
    __tablename__ = 'organizations'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.Enum('church', 'school', 'other'), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    def __repr__(self):
        return f'<Organization {self.name}>'

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)  # hashed password
    role = db.Column(db.Enum('admin', 'user', 'manager', 'other'), default='user')
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))
    firstname = db.Column(db.String(50))
    lastname = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    organization = db.relationship('Organization', backref=db.backref('users', lazy=True))

    def __repr__(self):
        return f'<User {self.username}>'

# Routes

@app.route('/')
def index():
    return "Hello, welcome to the Flask app!"

# Example route to list users
@app.route('/users', methods=['GET'])
def get_users():
    users = User.query.all()
    users_list = [{
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'organization_id': user.organization_id
    } for user in users]
    return jsonify(users_list)

# Login API Endpoint
@app.route('/api/users/login', methods=['POST'])
def login():
    data = request.get_json()
    identifier = data.get("username")  # Can be username or email
    password = data.get("password")
    
    if not identifier or not password:
        return jsonify({"error": "Username/email and password required"}), 400

    # Check for a user matching either the username or email
    user = User.query.filter((User.username == identifier) | (User.email == identifier)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # NOTE: In production, passwords should be hashed. This is for demonstration only.
    if user.password != password:
        return jsonify({"error": "Invalid credentials"}), 401

    # Signal that the login is successful (redirect to landing page on frontend)
    return jsonify({
        "message": "Login successful",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role
        }
    }), 200


# To initialize the database tables (run once)
@app.cli.command('init-db')
def init_db():
    db.create_all()
    print("Initialized the database.")

if __name__ == '__main__':
    app.run(debug=True)
