"""AI/ML strategies home.

See README.md in this folder for the plugin contract. Every model subclasses
:class:`~app.strategies.ml.base_ml.MLStrategy` and registers itself via
``@register_strategy`` so the engine can load it alongside rule-based
templates.
"""
