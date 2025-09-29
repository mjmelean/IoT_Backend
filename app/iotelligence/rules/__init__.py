# app/iotelligence/rules/__init__.py
from .rule1 import Rule1Extremos
from .rule2 import Rule2Misconfig

# registro disponible
REGISTRY = {
    "extremos": Rule1Extremos(),
    "misconfig": Rule2Misconfig()
}