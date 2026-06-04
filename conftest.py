"""Raíz del proyecto en sys.path para que los tests importen config/oscilion."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
