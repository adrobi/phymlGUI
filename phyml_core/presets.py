"""Analysis presets: the parameter subset that is saved and re-applied (no Qt).

A preset holds the model and search parameters and the engine. Tool paths and display
options are deliberately outside it, so applying a preset never repoints a program.
"""
import copy

PRESET_KEYS = ('datatype', 'model', 'support_method', 'bootstrap_replicates',
               'freq', 'tstv', 'pinv', 'classes', 'gamma', 'search',
               'optimize', 'parsimony', 'engine')

BUILTIN = {
    'preset_builtin_screen': {
        'datatype': 'nt', 'model': 'HKY85', 'support_method': '-4',
        'bootstrap_replicates': '100', 'freq': 'default', 'tstv': 'e',
        'pinv': '0.0', 'classes': '4', 'gamma': 'e', 'search': 'NNI',
        'optimize': 'tlr', 'parsimony': False, 'engine': 'phyml'},
    'preset_builtin_pub': {
        'datatype': 'nt', 'model': 'GTR', 'support_method': 'bootstrap',
        'bootstrap_replicates': '1000', 'freq': 'default', 'tstv': 'e',
        'pinv': 'e', 'classes': '4', 'gamma': 'e', 'search': 'BEST',
        'optimize': 'tlr', 'parsimony': False, 'engine': 'phyml'},
}


def extract(params: dict) -> dict:
    """The part of params that a preset stores: PRESET_KEYS that params has."""
    return {k: params[k] for k in PRESET_KEYS if k in params}


def apply(preset: dict, params: dict) -> dict:
    """A copy of params with the PRESET_KEYS of preset laid over it (the engine included).
    A preset saved without an engine leaves the current engine alone."""
    out = copy.deepcopy(params)
    out.update({k: preset[k] for k in PRESET_KEYS if k in preset})
    return out
