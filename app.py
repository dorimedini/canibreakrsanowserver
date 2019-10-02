from flask import Flask
from Q import Q
app = Flask(__name__)


@app.route('/')
def index():
    return Q.test_quantum_run_response()


@app.route('/greet')
def say_hello():
    return 'Hello from Server'
