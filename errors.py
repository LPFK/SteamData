from flask import jsonify


def error_response(error_code: str, message, status: int):
    # all errors go through here — no raw strings or ad-hoc dicts in routes
    return jsonify({
        "error":   error_code,
        "message": message,
        "code":    status,
    }), status
