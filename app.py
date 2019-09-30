from flask import Flask, Response
from Q import Q
app = Flask(__name__)


@app.route('/')
def index():
    return Response(Q.generate_test_quantum_run_response())


@app.route('/greet')
def say_hello():
    return 'Hello from Server'
