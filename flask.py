from flask import Flask

app = Flask(__name__)
@app.route('/')
def hello():
    return 'hello world'


if name ==‘main’:
    app.run(debug=True,host=‘0.0.0.0’,port=5000)
