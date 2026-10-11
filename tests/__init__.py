import os
import sys

# The package under test lives in src/, next to the launcher script that puts
# it on sys.path at run time; tests need the same thing done for them.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
