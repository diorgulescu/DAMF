from flask import render_template, flash, redirect, url_for
from app import app
from app.forms import LoginForm

@app.route('/')
@app.route('/index.html')
@app.route('/index')
def index():
    return render_template("index.html")

@app.route('/devices')
def devices():
    device_list = [
            {
                'owner' : {'username' : 'admin'},
                'name' : 'raspberry-pi-v3-1',
                'state' : 'running',
                'deployed_image' : 'Focused Linux',
                'arch' : 'arm'
                },
            {
                'owner' : {'username' : 'admin'},
                'name' : 'raspberry-pi-v2-server',
                'state' : 'powered off',
                'deployed_image' : 'Raspbian',
                'arch' : 'arm'
                }
            ]
    return render_template("devices.html", devices=device_list)

@app.route('/lab')
def lab_view():
    return "Lab diagram view (dynamically generated)"

@app.route('/dashboard')
def user_dashboard():
    return "A user landing page, displaying relevant info for each and every account"

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        flash("Login requested for user {}, remember_me={}".format(form.username.data,form.remember_me.data))
        return redirect(url_for('index'))
    return render_template("login.html", title="Sign In", form=form) 

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
