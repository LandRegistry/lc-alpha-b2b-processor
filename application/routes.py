from application import app
from flask import Response, request
import logging
import requests
import json


def check_bankreg_health():
    return requests.get(app.config['BANKRUPTCY_DATABASE_API'] + '/health')


def check_automat_health():
    return requests.get(app.config['RULES_ENGINE_URL'] + '/health')


application_dependencies = [
    {
        "name": "bankruptcy-registration",
        "check": check_bankreg_health
    },
    {
        "name": "automation_rules",
        "check": check_automat_health
    }
]


@app.route('/', methods=["GET"])
def index():
    return Response(status=200)


@app.route('/health', methods=['GET'])
def health():
    result = {
        'status': 'OK',
        'dependencies': {}
    }

    status = 200
    for dependency in application_dependencies:
        response = dependency["check"]()
        result['dependencies'][dependency['name']] = str(response.status_code) + ' ' + response.reason
        data = json.loads(response.content.decode('utf-8'))
        for key in data['dependencies']:
            result['dependencies'][key] = data['dependencies'][key]

    return Response(json.dumps(result), status=status, mimetype='application/json')


@app.route('/register', methods=["POST"])
def register():
    if request.headers['Content-Type'] != "application/json":
        return Response(status=415)  # 415 (Unsupported Media Type)

    json_data = request.get_json(force=True)

    url = app.config['RULES_ENGINE_URL'] + '/check_auto'
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, data=json.dumps(json_data), headers=headers)

    if response.status_code == 200:
        data = response.json()
        go_auto = (data['register_auto'])
        if go_auto:
            logging.info('Automatically processing')

            # Convert the data for banks-reg, though in time BR will also change
            json_data['date'] = json_data['application_date']
            json_data['debtor_name'] = json_data['debtor_names'][0]
            json_data['debtor_alternative_name'] = json_data['debtor_names'][1:]
            del json_data['application_date']
            del json_data['debtor_names']

            url = app.config['BANKRUPTCY_DATABASE_API'] + '/registration'
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, data=json.dumps(json_data), headers=headers)

        else:
            # save to work list
            logging.info('Dropping to manual')
            url = app.config['CASEWORK_DATABASE_API'] + '/workitem'
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, data=json.dumps(json_data), headers=headers)
            if response.status_code == 200:
                data = response.json()
                work_id = (data['id'])
                return Response(json.dumps({'id': work_id}), status=response.status_code)

        return Response(response.content, status=response.status_code, mimetype='application/json')
    else:
        logging.error('Received code %d', response.status_code)
        return Response(status=response.status_code)
