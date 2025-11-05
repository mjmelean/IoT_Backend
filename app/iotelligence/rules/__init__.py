from .rule1 import Rule1Extremos
from .rule2 import Rule2Misconfig
from .rule3 import Rule3LearnSchedule
from .rule4 import Rule4OfflineWatchdog     
from .rule5 import Rule5Weather

# Registro de todas las reglas disponibles
REGISTRY = {
    "extremos": Rule1Extremos(),
    "misconfig": Rule2Misconfig(),
    "learn": Rule3LearnSchedule(),
    "offline": Rule4OfflineWatchdog(),      
    "weather": Rule5Weather(),
}