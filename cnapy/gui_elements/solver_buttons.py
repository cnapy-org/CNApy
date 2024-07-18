from importlib import find_loader as module_exists
from qtpy.QtWidgets import (QButtonGroup, QRadioButton, QVBoxLayout)
from straindesign import select_solver
from straindesign.names import CPLEX, GUROBI, GLPK, SCIP
from typing import Tuple


def get_solver_buttons(appdata) -> Tuple[QVBoxLayout, QButtonGroup]:
    # find available solvers
    avail_solvers = []
    if module_exists('cplex'):
        avail_solvers += [CPLEX]
    if module_exists('gurobipy'):
        avail_solvers += [GUROBI]
    if module_exists('swiglpk'):
        avail_solvers += [GLPK]
    if module_exists('pyscipopt'):
        avail_solvers += [SCIP]

    # Get solver button group
    solver_buttons_layout = QVBoxLayout()
    solver_buttons = {}
    solver_buttons["group"] = QButtonGroup()
    # CPLEX
    solver_buttons[CPLEX] = QRadioButton("IBM CPLEX")
    solver_buttons[CPLEX].setProperty('name', CPLEX)
    if CPLEX not in avail_solvers:
        solver_buttons[CPLEX].setEnabled(False)
        solver_buttons[CPLEX].setToolTip('CPLEX is not set up with your python environment. '+\
            'Install CPLEX and follow the steps of the python setup \n'+\
            r'(https://www.ibm.com/docs/en/icos/22.1.0?topic=cplex-setting-up-python-api)')
    solver_buttons_layout.addWidget(solver_buttons[CPLEX])
    solver_buttons["group"].addButton(solver_buttons[CPLEX])
    # Gurobi
    solver_buttons[GUROBI] = QRadioButton("Gurobi")
    solver_buttons[GUROBI].setProperty('name',GUROBI)
    if GUROBI not in avail_solvers:
        solver_buttons[GUROBI].setEnabled(False)
        solver_buttons[GUROBI].setToolTip('Gurobi is not set up with your python environment. '+\
        'Install Gurobi and follow the steps of the python setup (preferably option 3) \n'+\
        r'(https://support.gurobi.com/hc/en-us/articles/360044290292-How-do-I-install-Gurobi-for-Python-)')
    solver_buttons_layout.addWidget(solver_buttons[GUROBI])
    solver_buttons["group"].addButton(solver_buttons[GUROBI])
    # GLPK
    solver_buttons[GLPK] = QRadioButton("GLPK")
    solver_buttons[GLPK].setProperty('name',GLPK)
    if GLPK not in avail_solvers:
        solver_buttons[GLPK].setEnabled(False)
        solver_buttons[GLPK].setToolTip('GLPK is not set up with your python environment. '+\
        'GLPK should have been installed together with the COBRA toolbox. \n'\
        'Reinstall the COBRA toolbox for your Python environment.')
    solver_buttons_layout.addWidget(solver_buttons[GLPK])
    solver_buttons["group"].addButton(solver_buttons[GLPK])
    # SCIP
    solver_buttons[SCIP] = QRadioButton("SCIP")
    solver_buttons[SCIP].setProperty('name',SCIP)
    if SCIP not in avail_solvers:
        solver_buttons[SCIP].setEnabled(False)
        solver_buttons[SCIP].setToolTip('SCIP is not set up with your python environment. '+\
        'Install SCIP following the steps of the PySCIPOpt manual \n'+\
        r'(https://github.com/scipopt/PySCIPOpt')
    solver_buttons_layout.addWidget(solver_buttons[SCIP])
    solver_buttons["group"].addButton(solver_buttons[SCIP])
    # optlang_enumerator
    solver_buttons['OPTLANG'] = QRadioButton()
    solver_buttons['OPTLANG'].setProperty('name','OPTLANG')
    solver_buttons['OPTLANG'].setToolTip('optlang_enumerator supports calculation of reaction MCS only.\n'+\
        'Reaction knock-ins and setting of intervention costs are possible.\n'+\
        'The solver can be changed via COBRApy settings.')
    solver_buttons_layout.addWidget(solver_buttons['OPTLANG'])
    solver_buttons["group"].addButton(solver_buttons['OPTLANG'])
    # check best available solver
    if avail_solvers:
        # Set cobrapy default solver if available
        solver = select_solver(None, appdata.project.cobra_py_model)
        solver_buttons[solver].setChecked(True)

    return solver_buttons_layout, solver_buttons
