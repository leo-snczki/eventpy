import os
from flask import Flask, render_template, request, redirect, url_for
from flask_bootstrap import Bootstrap5
from peewee import *

app = Flask(__name__)
bootstrap = Bootstrap5(app)

if __name__ == "__main__":
    app.run(debug=True)