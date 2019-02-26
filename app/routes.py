from flask import render_template
from app import app

@app.route('/')
def index():
    return "Index test"

@app.route('/devices')
def devices():
    return "Device listing"

@app.route('/lab')
def lab_view():
    return "Lab diagram view (dynamically generated)"

@app.route('/dashboard')
def user_dashboard():
    return "A user landing page, displaying relevant info for each and every account"

@app.route('/login'):
    return "Login page/form"

@app.route('/administration')
    return "Admin section"

@app.route('/user')
    return "User account section"

@app.route('/setup')
    return "First run - quick setup wizard"
