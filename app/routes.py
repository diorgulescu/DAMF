"""Flask routes bridged to the DAMF core engine (`DAMFWebApp`)."""

from flask import Response, flash, redirect, render_template, request, url_for
from app import app
from app.forms import LoginForm
from damf.web import DAMFWebApp

_damf_web = DAMFWebApp()


def _bridge_to_damf():
    status, content_type, body = _damf_web.handle_request(
        request.method,
        request.full_path if request.query_string else request.path,
        request.get_data(),
    )
    return Response(body, status=status, content_type=content_type)


@app.route('/')
@app.route('/index.html')
@app.route('/index')
@app.route('/devices')
@app.route('/lab')
@app.route('/dashboard')
@app.route('/administration')
@app.route('/user')
@app.route('/setup')
@app.route('/reports')
def ui_routes():
    return _bridge_to_damf()


@app.route('/api/v1/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def api_v1_routes(subpath):
    return _bridge_to_damf()


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        flash("Login requested for user {}, remember_me={}".format(form.username.data, form.remember_me.data))
        return redirect(url_for('ui_routes'))
    return render_template("login.html", title="Sign In", form=form)
