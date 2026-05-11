from marshmallow import Schema, fields, validate, validates, ValidationError


class RegisterSchema(Schema):
    username = fields.Str(required=True, validate=validate.Length(min=2, max=64))
    email    = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=8, max=200))


class LoginSchema(Schema):
    username = fields.Str(required=True, validate=validate.Length(min=2, max=64))
    password = fields.Str(required=True, validate=validate.Length(min=1, max=200))


class GameQuerySchema(Schema):
    genre      = fields.Str(load_default=None)
    price_tier = fields.Str(load_default=None, validate=validate.OneOf(
        ["free", "budget", "mid", "premium"]
    ))
    is_indie   = fields.Bool(load_default=None)
    year_min   = fields.Int(load_default=None, validate=validate.Range(min=1990, max=2030))
    year_max   = fields.Int(load_default=None, validate=validate.Range(min=1990, max=2030))
    limit      = fields.Int(load_default=50, validate=validate.Range(min=1, max=200))
    offset     = fields.Int(load_default=0, validate=validate.Range(min=0))
