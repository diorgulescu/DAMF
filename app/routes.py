from flask import render_template
from app import app

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/devices')
def devices():
    return render_template("devices.html")

@app.route('/lab')
def lab_view():
    return "Lab diagram view (dynamically generated)"

@app.route('/dashboard')
def user_dashboard():
    return "A user landing page, displaying relevant info for each and every account"

@app.route('/login')
def login():
    return "Login page/form"

@app.route('/administration')
def admin_section():
    return "Admin section"

@app.route('/user')
def user_section():
    return "User account section"

@app.route('/setup')
def first_run():
    return "First run - quick setup wizard"

@app.route('/reports')
def reporting():
    return "Reporting center"
