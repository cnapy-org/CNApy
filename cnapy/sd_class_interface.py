"""
"""

# IMPORTS SECTION #
# External packages
from dataclasses import dataclass
from enum import Enum
from os import cpu_count
from numpy import array_split, linspace

# import ray
from scipy import sparse
from typing import Any, Callable, Dict, List, Tuple, Union

# from helper import json_write, json_load

# Internal packages
from straindesign.indicatorConstraints import IndicatorConstraints
from straindesign.solver_interface import MILP_LP


# ENUMS SECTION #
class ConstraintSense(Enum):
    """
    Shows the directional sense of a constraint, e.g., the constraint...

    A + 2 B <= 2

    ...has the sense "lower equal" (<=). With (MI)LPs, possible senses are:

    1. Lower equal (<=; LEQ)
    2. Equal (==; EQ)
    3. Greater equal (>=; GEQ)
    """

    LEQ = 1
    """<=; Lower equal"""
    EQ = 2
    """==; Equal"""
    GEQ = 3
    """>=; Greater equal"""


class BinaryValue(Enum):
    """
    Shows the value of a binary variable, i.e. either 1 or 0.
    This is used in defining indicator constraints. It is *not*
    intended to be used within constraints.
    """

    ZERO = 0
    """The integer 0"""
    ONE = 1
    """The integer 1"""


class ObjectiveDirection(Enum):
    """
    Indicates the direction of the LinearProgram's objective, i.e.
    either a minimization (MIN) or maximization (MAX).
    """

    MIN = 0
    """Minimize objective function"""
    MAX = 1
    """Maximize objective function"""


class Solver(Enum):
    """Shows for which solver a LinearProgram shall be constructed."""

    CPLEX = "cplex"
    """The IBM CPLEX (c) solver."""
    GLPK = "glpk"
    """The open-source GNU Linear Programming kit."""
    GUROBI = "gurobi"
    """The Gurobi (c) solver."""
    SCIP = "scip"
    """The open-source Solving Constraint Integer Programs suite."""


class Status(Enum):
    """
    The status of a LinearProgram solution after a solver run.
    It can be either 'OPTIMAL', 'INFEASIBLE', 'UNBOUNDED' or 'TIME_LIMIT'.
    See the member variable's associated description for more about these statuses.
    """

    OPTIMAL = "optimal"
    """Optimal status, i.e. a feasible and optimal solution was found."""
    INFEASIBLE = "infeasible"
    """Infeasible status, i.e. no feasible solution could be found."""
    UNBOUNDED = "unbounded"
    """Unbounded status, i.e. a feasible solution can be found but it is either infinite or -infinite."""
    TIME_LIMIT = "time_limit"
    """Time limit status, i.e., so feasible solution could be found before the user-defined timelimit was hit."""
    UNKNOWN = "unknown"
    """A status from StrainDesign which could not be identified. If this happens, a severe error must have occured."""


# DATACLASS SECTION #
@dataclass
class FloatVariable:
    """A continuous (MI)LP variable which can hold values between -float('inf') and +float('inf')."""

    name: str
    """Identifying name of float variable"""
    lb: float
    """Lower bound of float variable"""
    ub: float
    """"Upper bound of float variable"""


@dataclass
class BinaryVariable:
    """An integer (MI)LP variable which can be either 0 or 1."""

    name: str
    """Identifying name of binary variable"""


@dataclass
class Constraint:
    """A (MI)LP constraint. See the description of the member variables to find out more."""

    name: str
    """Identifying name of constraint"""
    lhs: Dict[str, float]
    """
    Definition
    ===
    Left hand side of constraint in the form of a dictionary where
    the variable names are the keys, and the coefficcients are

    Example
    ===
    E.g., in the constraint '2A+B-C-2D<=0', the left hand side is '2A+B-C-2D'.
    There, the coefficient of variable 'A' is 2, the one of 'B' is 1, the one of
    C is  -1 and the one of D is -2. Hence, the resulting lhs dict is as follows:

    {
        'A': 2,
        'B': 1,
        'C': -1,
        'D': -2,
    }

    The order of variables in this lhs dict has no matter, e.g., 'B' may also appear
    before 'A' in the dict as long as their respective coefficients are also switched.
    """
    rhs: float
    """
    The right hand side of the constraint. E.g., in the constraint '2A+B-C-2D<=2.32',
    the right hand side is 2.32.
    """
    sense: ConstraintSense
    """
    Sense of the constraint, must be lower equal/<= (ConstraintSense.LE),
    equal/== (ConstraintSense.EQ) or greater equal/>= (ConstraintSense.GEQ).
    """


@dataclass
class IndicatorConstraint(Constraint):
    """
    A constraint which is only active if its associated binary variable
    (with the name binary_name) has a certain given value (binary_value).
    E.g., if we want the following constraint...

    A <= 5

    ...to be only active when the value of a binary variable B is 0, i.e.,

    B=0 -> A <= 5,

    then binary_name is 'B' and binary_value is 0. For more about the other
    member variables taken over from the usual Constraint class, see their
    description directly.
    """

    binary_name: str
    """The name of the binary variable which controls this indicator constraint."""
    binary_value: BinaryValue
    """
    The value of the binary_name-defined binary variable at which the given
    constraint must be fulfilled.
    """


@dataclass
class Objective:
    """
    A (MI)LP objective function defined by its vector
    and with a given direction (minimization or maximization).
    """

    vector: Dict[str, float]
    """
    The definition of the constituents of the objective's terms. I.e., if we
    want to optimize...

    2 A + 3 B ...

    then our vector is...

    {"A": 2.0, "B": 3.0}.
    """
    direction: ObjectiveDirection
    """
    The objective's direction, either minimization (ObjectiveDirection.MAX)
    or maximization (ObjectiveDirection.MIN) of the term in the objective's vector.
    """


@dataclass
class Result:
    """Contains all relevant information about the result of an optimization."""

    status: Status
    """Indicated whether or not an optimal solution was found (Status.OPTIMAL) or not (any other Status value)."""
    objective_value: float
    """The result's objective value, already corrected for maximization or minimization."""
    values: Dict[str, float]
    """The single solution variable values as a dict with the variable names as key."""


# MAIN CLASS SECTION #
class LinearProgram:
    """
    Main class of StrainDesign's class interface.

    It contains the full description of a (mixed-integer) linear program, i.e., its variables, constraints
    and objective.

    # Variables

    Variables are separated as continuous *float* variables (which can take up continuous values, e.g. -1.2 or 3.0) and
    *binary* variables (which can be only either 0 or 1). Float variables are of the class FloatVariable, binary variables
    of BinaryVariable.

    Variables must have a unique name (i.e., no two variables must
    have the same name) and can be included in the LinearProgram as an already existing FloatVariable or BinaryVariable
    instance through add_existing_float_variable() or add_existing_binary_variable, or as newly described variable
    with add_float_variable() or add_binary_variable().

    # Constraints

    Constraints can be of the form 'Expression <= Number' (e.g., 2 A + B <= -1), 'Expression == Number' (e.g., A + B = 1)
    or 'Expression >= Number' (e.g., A + 2 B >= 4).

    They are separated as 'normal' constraints or 'indicator' constraints.
    Both can be defined using FloatVariable and BinaryVariable instance names for their left-hand side and a float for their
    right-hand side. The difference is that an indicator constraint is only active (i.e., it only plays a role) if and only
    if a selected binary value is one of 0 or 1. E.g., the indicator constraint T=0 → A <= 1 means that A must be smaller than
    1 only and only if the binary variable T is zero. The binary value must be an instance of
    BinaryValue.

    Normal constraints are of the class Constraint, indicator constraints of IndicatorConstraint.

    Constraints can be added as already created constraints through add_existing_constraint()
    or add_existing_indicator_constraint() or, wihh all Constraint or IndicatorConstraint member
    variables as parameters, add_constraint() or add_indicator_constraint().

    # Objective

    The objective indicates which linear expression shall be maximized or minimized. In
    a LinearProgram instance, objective are instances of Objective.

    Objectives for linear expressions need a "vector", i.e. a dictionary which
    describes the linear expression and a direction from ObjectiveDirection,
    i.e. whether the linear expression is to be maximized or minimized.
    Linear expression objectives for a LinearProgram can be set through
    set_objective() or set_existing_objective().

    There is also an additional function for the maximization or minimization
    of a single variable called set_single_variable_objective().

    # Solving a LinearProgram

    After all variables, constraints and the objective are set, the LinearProgram
    can be solved. Before this can be one, a LinearProgram solver object must be
    created through the function construct_solver_object(). This function needsd
    an instance of Solver as parameter. StrainDesigncurrently supports the open-source
    solvers GLPK and SCIP (of which only the latter supports indicator constraints
    so that they are automatically converted into numerically more unstable Big-M
    formulations) as well as the commercial solvers IBM CPLEX and Gurobi.

    After this solver object is constructed, one can either run_slim_solve() (which
    only returns the objective value) or run_solve() which results a full Result
    instance. Additionally, with CPLEX, one can also run_populate() for many
    alternative solutions.
    """

    def __init__(self) -> None:
        self.float_variables: Dict[str, FloatVariable] = {}
        self.binary_variables: Dict[str, BinaryVariable] = {}
        self.constraints: Dict[str, Constraint] = {}
        self.indicator_constraints: Dict[str, IndicatorConstraint] = {}
        self.timelimit: int = 30
        self.ineq_names: List[str] = []
        self.active_variables: List[str] = []
        self.objective: Objective = Objective(
            vector={},
            direction=ObjectiveDirection.MAX,
        )

    def _get_objective_vector(self) -> List[float]:
        objective_vector = [0.0 for _ in range(self.num_variables)]
        if self.objective.direction == ObjectiveDirection.MAX:
            multiplier = -1
        else:
            multiplier = 1
        for var_name, coeff in self.objective.vector.items():
            objective_vector[self.active_variables.index(var_name)] = multiplier * coeff
        return objective_vector

    def add_binary_variable(self, name: str) -> None:
        new_variable = BinaryVariable(
            name=name,
        )
        self.binary_variables[name] = new_variable

    def add_constraint(
        self,
        name: str,
        lhs: Dict[str, float],
        sense: ConstraintSense,
        rhs: float,
    ) -> None:
        constraint = Constraint(
            name=name,
            lhs=lhs,
            rhs=rhs,
            sense=sense,
        )
        self.add_existing_constraint(constraint)

    def add_existing_binary_variable(self, variable: BinaryVariable) -> None:
        self.binary_variables[variable.name] = variable

    def add_existing_constraint(self, constraint: Constraint) -> None:
        self.constraints[constraint.name] = constraint

    def add_existing_float_variable(self, variable: FloatVariable) -> None:
        self.float_variables[variable.name] = variable

    def add_existing_indicator_constraint(
        self, indicator_constraint: IndicatorConstraint
    ) -> None:
        self.indicator_constraints[indicator_constraint.name] = indicator_constraint

    def add_float_variable(self, name: str, lb: float, ub: float) -> None:
        new_variable = FloatVariable(
            name=name,
            lb=lb,
            ub=ub,
        )
        self.float_variables[name] = new_variable

    def add_indicator_constraint(
        self,
        name: str,
        lhs: Dict[str, float],
        rhs: float,
        sense: ConstraintSense,
        binary_name: str,
        binary_value: BinaryValue,
    ) -> None:
        self.indicator_constraints[name] = IndicatorConstraint(
            name=name,
            lhs=lhs,
            rhs=rhs,
            sense=sense,
            binary_name=binary_name,
            binary_value=binary_value,
        )

    def add_lhs_bound_variable(self, var_name: str, lhs: Dict[str, float]) -> None:
        self.add_float_variable(name=var_name, lb=-float("inf"), ub=float("inf"))
        lhs[var_name] = -1
        self.add_constraint(
            name=f"Bound var {var_name} to rest of this LHS",
            lhs=lhs,
            rhs=0,
            sense=ConstraintSense.EQ,
        )

    def add_linear_function_approximation(
        self,
        existing_x_var: str,
        new_y_var: str,
        function_to_approximate: Callable[[float], float],
        function_derivative: Callable[[float], float],
        min_x: float,
        max_x: float,
        max_relative_error: float,
        is_minimum_for_y: bool,
    ) -> None:
        current_num_sections = 2
        is_above_error = True
        while is_above_error:
            section_xs = linspace(min_x, max_x, current_num_sections)
            step_size = section_xs[1] - section_xs[0]
            is_above_error = False
            linear_approximations: List[Tuple[float, float]] = []
            current_section_x = 0
            for section_x in section_xs:
                function_y = function_to_approximate(section_x)
                derivative_y = function_derivative(section_x)
                m_value = derivative_y
                b_value = function_y - derivative_y * section_x

                if current_section_x == 0:
                    left_x = section_x
                else:
                    left_x = section_x - step_size / 2
                if current_section_x == (len(section_xs) - 1):
                    right_x = section_x
                else:
                    right_x = section_x + step_size / 2

                for test_x in (left_x, right_x):
                    try:
                        function_y = function_to_approximate(test_x)
                    except ValueError:
                        continue
                    approximation_y = m_value * test_x + b_value
                    error_absolute = function_y - approximation_y
                    error_relative = abs(error_absolute / function_y)
                    if error_relative > max_relative_error:
                        is_above_error = True
                        break

                if is_above_error:
                    current_num_sections += 1
                    break

                linear_approximations.append((m_value, b_value))
                current_section_x += 1

        self.add_float_variable(
            name=new_y_var,
            lb=-float("inf"),
            ub=float("inf"),
        )
        current_approx = 0
        for linear_approximation in linear_approximations:
            m_value = linear_approximation[0]
            b_value = linear_approximation[1]
            if is_minimum_for_y:
                #     y_variable >= m_value * x_variable + b_value
                # <=> -y_variable + m_value * x_variable <= -b_value
                multiplier = 1
            else:
                #     y_variable <= m_value * x_variable + b_value
                # <=> y_variable - m_value * x_variable <= b_value
                multiplier = -1
            self.add_constraint(
                name=f"Function approximation no. {current_approx} through "
                f"{new_y_var} from {existing_x_var}",
                lhs={
                    new_y_var: -multiplier,
                    existing_x_var: m_value * multiplier,
                },
                rhs=-multiplier * b_value,
                sense=ConstraintSense.EQ,
            )
            current_approx += 1

    def replace_ineq_constraint_in_solver_object(
        self, ineq_name: str, lhs: Dict[str, float], sense: ConstraintSense, rhs: float
    ) -> None:
        index = self.ineq_names.index(ineq_name)
        constraint = self.constraints[ineq_name]
        if sense == ConstraintSense.GEQ:
            multiplier = -1.0
        else:
            multiplier = 1.0
        a_ineq = [0.0 for _ in range(self.num_variables)]
        for var_name, coeff in lhs.items():
            column = self.active_variables.index(var_name)
            a_ineq[column] = coeff * multiplier

        b_ineq = rhs
        self._milp_lp.set_ineq_constraint(
            idx=index,
            a_ineq=a_ineq,
            b_ineq=b_ineq,
        )

    def construct_solver_object(
        self,
        big_m_value: Union[None, float, int] = None,
        skip_checks: bool = True,
        timelimit: Union[int, None] = None,
        solver: Solver = Solver.GLPK,
    ) -> None:
        # Pre-creation of data structures which will be used in the following steps
        self.active_variables = []
        eq_names: List[str] = []
        self.ineq_names = []
        num_equalities = 0
        num_inequalities = 0
        get_var_names = lambda constraint_dict: [
            var_name for var_name in constraint_dict.keys()
        ]
        for constraint in self.constraints.values():
            self.active_variables += get_var_names(constraint.lhs)
            if constraint.sense == ConstraintSense.EQ:
                num_equalities += 1
                eq_names.append(constraint.name)
            else:
                num_inequalities += 1
                self.ineq_names.append(constraint.name)
        for indicator_constraint in self.indicator_constraints.values():
            self.active_variables += get_var_names(indicator_constraint.lhs)
            self.active_variables += [indicator_constraint.binary_name]
        self.active_variables = list(set(self.active_variables))
        num_variables = len(self.active_variables)
        self.num_variables = num_variables

        # Build A and b
        num_matrix_columns = num_variables
        A_ineq = sparse.lil_matrix((num_inequalities, num_matrix_columns))
        b_ineq: List[float] = [0.0 for _ in range(num_inequalities)]
        ineq_index = 0
        for ineq_name in self.ineq_names:
            constraint = self.constraints[ineq_name]
            row = self.ineq_names.index(constraint.name)
            if constraint.sense == ConstraintSense.GEQ:
                multiplier = -1.0
            else:
                multiplier = 1.0
            for var_name, coeff in constraint.lhs.items():
                column = self.active_variables.index(var_name)
                A_ineq[row, column] = coeff * multiplier
            b_ineq[ineq_index] = self.constraints[ineq_name].rhs * multiplier
            ineq_index += 1
        A_ineq = sparse.csr_matrix(A_ineq)

        A_eq = sparse.lil_matrix((num_equalities, num_matrix_columns))
        for eq_name in eq_names:
            constraint = self.constraints[eq_name]
            row = eq_names.index(constraint.name)
            for var_name, coeff in constraint.lhs.items():
                column = self.active_variables.index(var_name)
                A_eq[row, column] = coeff
        A_eq = sparse.csr_matrix(A_eq)
        b_eq: List[float] = [self.constraints[eq_name].rhs for eq_name in eq_names]

        # Build LB and UB vectors
        num_bounded_variables = len(self.active_variables)
        lower_bounds: List[float] = [0.0 for _ in range(num_bounded_variables)]
        upper_bounds: List[float] = [0.0 for _ in range(num_bounded_variables)]
        variable_types: str = ""
        var_index = 0
        for var_name in self.active_variables:
            if var_name in self.binary_variables.keys():
                lb = 0.0
                ub = 1.0
                variable_types += "B"
            else:
                float_var = self.float_variables[var_name]
                lb = float_var.lb
                ub = float_var.ub
                variable_types += "C"
            lower_bounds[var_index] = lb
            upper_bounds[var_index] = ub
            var_index += 1

        # Build objective vector
        objective_vector: List[float] = self._get_objective_vector()

        # Create indicator constraints
        binv: List[int] = []  # Binary variable indices
        # Set coeffs of indicators; num_rows = number of indicator constraints,
        # num_columns = number of variables
        A_indic = sparse.lil_matrix(
            (len(self.indicator_constraints), num_matrix_columns)
        )
        b_indic: List[float] = [
            0.0 for _ in range(len(self.indicator_constraints.values()))
        ]  # RHS of indicators
        sense = ""
        # Indicval which binary value activates indicator constraint
        indicval: List[int] = [
            0 for _ in range(len(self.indicator_constraints.values()))
        ]
        indic_index = 0
        for indicator_constraint in self.indicator_constraints.values():
            binary_name = indicator_constraint.binary_name
            binv.append(self.active_variables.index(binary_name))

            for var_name, coeff in indicator_constraint.lhs.items():
                A_indic[indic_index, self.active_variables.index(var_name)] = coeff

            b_indic[indic_index] = indicator_constraint.rhs

            if sense == ConstraintSense.EQ:
                sense += "E"
            else:
                sense += "L"

            if indicator_constraint.binary_value == BinaryValue.ZERO:
                indicval[indic_index] = 0
            else:
                indicval[indic_index] = 1

            indic_index += 1
        A_indic = sparse.csr_matrix(A_indic)

        if len(indicval) > 0:
            indicator_constraints = IndicatorConstraints(
                binv=binv,
                A=A_indic,
                b=b_indic,
                sense=sense,
                indicval=indicval,
            )
        else:
            indicator_constraints = None

        # Generate StrainDesign object
        self._milp_lp = MILP_LP(
            c=objective_vector,
            A_ineq=A_ineq,
            b_ineq=b_ineq,
            A_eq=A_eq,
            b_eq=b_eq,
            lb=lower_bounds,
            ub=upper_bounds,
            vtype=variable_types,
            indic_constr=indicator_constraints,
            M=big_m_value,
            solver=solver.value,
            skip_checks=skip_checks,
            tlim=timelimit,
        )

    def delete_binary_variable(self, name: str) -> None:
        del self.binary_variables[name]

    def delete_float_variable(self, name: str) -> None:
        del self.float_variables[name]

    def delete_constraint(self, name: str) -> None:
        del self.constraints[name]

    def run_populate(self, num: int) -> Tuple[List[List[float]], List[float], float]:
        solvecs, optvals, optstatuses = self._milp_lp.populate(num)
        return solvecs, optvals, optstatuses

    def run_slim_solve(self) -> float:
        optval = self._milp_lp.slim_solve()
        return self._set_optval_according_to_sense(optval)

    def _get_status_enum(self, status: str) -> Status:
        if status == "optimal":
            return Status.OPTIMAL
        elif status == "unbounded":
            return Status.UNBOUNDED
        elif status == "time_limit":
            return Status.TIME_LIMIT
        elif status == "infeasible":
            return Status.INFEASIBLE
        else:
            return Status.UNKNOWN

    def run_solve(self) -> Result:
        solvec, optval, optstatus = self._milp_lp.solve()
        resultdict: Dict[str, float] = {}
        i = 0
        for active_variable in self.active_variables:
            resultdict[active_variable] = solvec[i]
            i += 1
        optstatus_str = str(optstatus)
        return Result(
            status=self._get_status_enum(optstatus_str),
            objective_value=self._set_optval_according_to_sense(optval),
            values=resultdict,
        )

    def _set_optval_according_to_sense(self, optval: float) -> float:
        if self.objective.direction == ObjectiveDirection.MAX:
            return -optval
        else:
            return optval

    def set_existing_objective(self, objective: Objective, warmstart=False) -> None:
        self.objective = objective
        if warmstart:
            self._milp_lp.set_objective(self._get_objective_vector())

    def set_objective(
        self,
        vector: Dict[str, float],
        direction: ObjectiveDirection,
        warmstart=False,
    ) -> None:
        self.objective = Objective(
            vector=vector,
            direction=direction,
        )
        if warmstart:
            self._milp_lp.set_objective(self._get_objective_vector())

    def set_single_variable_objective(
        self, var_name: str, direction: ObjectiveDirection, warmstart=False
    ) -> None:
        self.objective = Objective(
            vector={var_name: 1},
            direction=direction,
        )
        if warmstart:
            self._milp_lp.set_objective(self._get_objective_vector())

    def get_all_variable_names(self) -> List[str]:
        return list(self.float_variables.keys()) + list(self.binary_variables.keys())

    def get_all_constraint_name(self) -> List[str]:
        return list(self.constraints.keys()) + list(self.indicator_constraints.keys())

    # def run_variability_analysis(
    #     self, varnames: List[str] = []
    # ) -> List[Tuple[str, float, float]]:
    #     if varnames == []:
    #         varnames = self.active_variables
    #     del self._milp_lp
    #     num_cpus = cpu_count()
    #     if num_cpus is None:
    #         num_cpus = 1
    #     num_processes = min(len(varnames), num_cpus)
    #     varname_chunks = [
    #         [str(y) for y in x] for x in array_split(varnames, num_processes)
    #     ]
    #     futures = [
    #         variability_calc.remote(self, varname_chunk)
    #         for varname_chunk in varname_chunks
    #     ]
    #     results = ray.get(futures)
    #     return results


# @ray.remote
# def variability_calc(
#     lp_object: LinearProgram, varnames: List[str]
# ) -> List[Tuple[str, float, float]]:
#     ray.init(log_to_driver=False)
#     lp_object.construct_solver_object(solver=Solver.CPLEX)
#     result = []
#     for varname in varnames:
#         lp_object.set_single_variable_objective(
#             varname, direction=ObjectiveDirection.MIN, warmstart=True
#         )
#         min_value = lp_object.run_slim_solve()
#         lp_object.set_single_variable_objective(
#             varname, direction=ObjectiveDirection.MAX, warmstart=True
#         )
#         max_value = lp_object.run_slim_solve()
#         result.append((varname, min_value, max_value))
#     return result


"""
# R1: -> A
# R2: 4 A -> B
# R3: B ->
# ...and a test indicator constraint
testlp = LinearProgram()

var_R1 = FloatVariable("R1", 0, 12)
var_R2 = FloatVariable("R2", 0, 100)
var_R3 = FloatVariable("R3", 2, 2)

testlp.add_existing_float_variable(var_R1)
testlp.add_existing_float_variable(var_R2)
testlp.add_existing_float_variable(var_R3)

testlp.add_binary_variable("B1")
indicator = IndicatorConstraint(
    name="Indicator 1",
    lhs={"R1": -1},
    rhs=0,
    sense=ConstraintSense.LEQ,
    binary_name="B1",
    binary_value=BinaryValue.ZERO,
)
testlp.add_existing_indicator_constraint(indicator)

testlp.add_constraint(
    name="Steady-state of A",
    lhs={"R1": 1, "R2": -4},
    rhs=0,
    sense=ConstraintSense.EQ,
)
testlp.add_constraint(
    name="Steady-state of B",
    lhs={"R2": 1, "R3": -1},
    rhs=0,
    sense=ConstraintSense.EQ,
)
testlp.objective = Objective(
    vector={"B1": 1},
    direction=ObjectiveDirection.MIN,
)
testlp.construct_solver_object(solver=Solver.CPLEX)
print(testlp.run_slim_solve())
new_obj = Objective(
    vector={"B1": 1},
    direction=ObjectiveDirection.MAX,
)
testlp.set_existing_objective(new_obj, warmstart=True)
# print(testlp.run_slim_solve())
# testlp.run_variability_analysis()

cobra_model = cobra.io.read_sbml_model("ECC2.xml")
print("COBRApy:", cobra_model.objective, cobra_model.slim_optimize())
lp = get_steady_state_lp_from_cobra_model(cobra_model=cobra_model)
lp.objective = Objective(
    vector={"Ec_biomass_iJO1366_core_53p95M": 1.0},
    direction=ObjectiveDirection.MAX,
)
lp.construct_solver_object(solver=Solver.CPLEX)
solve_result = lp.run_solve()
json_write("x.json", solve_result.values)
print("Result with Class Interface:", lp.run_slim_solve())

variable_names = list(solve_result.values.keys())
lp.run_variability_analysis(variable_names)


input("X")
cobra_model = cobra.io.read_sbml_model("astheriscToymodelDouble_irreversible.xml")
cobra_model.reactions.get_by_id("EXCHG_strain1_B_c_to_B_FWD").upper_bound = float("inf")
cobra_model.reactions.get_by_id("EXCHG_strain2_B_c_to_B_REV").upper_bound = float("inf")

dG0_values = json_load("dG0_astheriscToymodelDouble.json")
for key in [x for x in dG0_values.keys()]:
    dG0_values[key + "_FWD"] = dG0_values[key]
    dG0_values[key + "_REV"] = dG0_values[key]

concentration_values = {
    "DEFAULT": {
        "min": 1.0,
        "max": 10.0,
    },
    "P_exchg": {
        "min": 5.0,
        "max": 10.0,
    },
}
extra_constraints = [
    {
        "EX_C_P_exchg_FWD": 1.0,
        "ub": 1.0,
        "lb": 1.0,
    }
]
optmdf = create_optmdfpathway_milp(
    cobra_model=cobra_model,
    dG0_values=dG0_values,
    concentration_values=concentration_values,
    extra_constraints=extra_constraints,
)
optmdf.objective = Objective(
    vector={"var_B": 1.0},
    direction=ObjectiveDirection.MAX,
)
optmdf.construct_solver_object(solver=Solver.CPLEX)
solve_result = optmdf.run_solve()
json_write("x.json", solve_result.values)
print("OPTMDF", optmdf.run_slim_solve())
optmdf.set_single_variable_objective(
    "x_P_exchg", direction=ObjectiveDirection.MAX, warmstart=True
)
print("x_P_exchg", exp(optmdf.run_slim_solve()))
optmdf.set_single_variable_objective(
    "x_P_exchg", direction=ObjectiveDirection.MIN, warmstart=True
)
print("x_P_exchg", exp(optmdf.run_slim_solve()))
print("x_P_exchg", exp(optmdf.run_slim_solve()))
solve_result = optmdf.run_solve()
json_write("x2.json", solve_result.values)
"""
