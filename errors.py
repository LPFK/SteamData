from flask import jsonify


def error_response(error_code: str, message, status: int):
    # all errors go through here
    return jsonify({
        "error":   error_code,
        "message": message,
        "code":    status,
    }), status
