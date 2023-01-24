# IMPORTS SECTION #
# External packages
import cobra

# Internal packages
from cnapy.sd_class_interface import (
    BinaryValue,
    ConstraintSense,
    IndicatorConstraint,
    FloatVariable,
    LinearProgram,
)
from numpy import log
from typing import Any, List, Dict


# CONSTANTS #
STANDARD_R = 8.314e-3  # kJ⋅K⁻1⋅mol⁻1 (standard value is in J⋅K⁻1⋅mol⁻1)
"""Standard gas constant in kJ⋅K⁻1⋅mol⁻1."""
STANDARD_T = 298.15  # K
"""Standard temperature in Kelvin."""


# PUBLIC FUNCTIONS #
def get_steady_state_lp_from_cobra_model(
    cobra_model: cobra.Model, extra_constraints: List[Dict[str, float]] = []
) -> LinearProgram:
    lp = LinearProgram()

    for reaction in cobra_model.reactions:
        reaction: cobra.Reaction = reaction
        reaction_var = FloatVariable(
            name=reaction.id,
            lb=reaction.lower_bound,
            ub=reaction.upper_bound,
        )
        lp.add_existing_float_variable(reaction_var)

    for metabolite in cobra_model.metabolites:
        metabolite: cobra.Metabolite = metabolite
        constraint_name = f"Steady-state of {metabolite.id}"
        constraint_lhs = {
            reaction.id: reaction.metabolites[metabolite]
            for reaction in metabolite.reactions
        }
        lp.add_constraint(
            name=constraint_name,
            lhs=constraint_lhs,
            rhs=0,
            sense=ConstraintSense.EQ,
        )

    extra_constraint_counter = 0
    for extra_constraint in extra_constraints:
        extra_constraint_lhs: Dict[str, float] = {}
        has_lb = False
        has_ub = False
        for key in extra_constraint.keys():
            if key == "lb":
                has_lb = True
                lb = extra_constraint["lb"]
            elif key == "ub":
                has_ub = True
                ub = extra_constraint["ub"]
            else:
                extra_constraint_lhs[key] = extra_constraint[key]

        base_extra_constraint_name = f"Extra_constraint_{extra_constraint_counter}_"

        if has_lb:
            lp.add_constraint(
                name=f"{base_extra_constraint_name}LB",
                lhs=extra_constraint_lhs,
                rhs=lb,
                sense=ConstraintSense.GEQ,
            )

        if has_ub:
            lp.add_constraint(
                name=f"{base_extra_constraint_name}UB",
                lhs=extra_constraint_lhs,
                rhs=ub,
                sense=ConstraintSense.LEQ,
            )
        extra_constraint_counter += 1

    return lp


def create_optmdfpathway_milp(
    cobra_model: cobra.Model,
    dG0_values: Dict[str, Dict[str, float]],
    concentration_values: Dict[str, Dict[str, float]],
    extra_constraints: List[Dict[str, float]] = [],
    ratio_constraints: List[Dict[str, Any]] = [],
    R: float = STANDARD_R,
    T: float = STANDARD_T,
    add_bottleneck_constraints: bool = False,
    minimal_optmdf: float= -float("inf"),
) -> LinearProgram:
    lp = get_steady_state_lp_from_cobra_model(
        cobra_model=cobra_model,
        extra_constraints=extra_constraints,
    )

    # Set metabolite variables
    for metabolite in cobra_model.metabolites:
        metabolite: cobra.Metabolite = metabolite

        if metabolite.id in concentration_values.keys():
            concentration_key = metabolite.id
        else:
            concentration_key = "DEFAULT"

        lower_concentration = log(concentration_values[concentration_key]["min"])
        upper_concentration = log(concentration_values[concentration_key]["max"])

        lp.add_float_variable(
            name=f"x_{metabolite.id}",
            lb=lower_concentration,
            ub=upper_concentration,
        )

    # Set concentration ratio ranges
    ratio_counter = 0
    for ratio_constraint in ratio_constraints:
        # c_i / c_j <= h_max AND c_i / c_j >= h_min
        # <=> x_i - x_j <= ln(h_max) AND x_i - x_j >= ln(h_min)
        # <=> (A) x_i - x_j - ln(h_max) <= 0 AND (B) -x_i + x_j - ln(h_min) <= 0
        c_i_id = ratio_constraint["c_i"]
        c_j_id = ratio_constraint["c_j"]

        ln_h_max = log(ratio_constraint["h_max"])
        ln_h_max_var = FloatVariable(
            name=f"ln_h_max_{ratio_counter}",
            lb=ln_h_max,
            ub=ln_h_max,
        )
        ln_h_min = log(ratio_constraint["h_min"])
        ln_h_min_var = FloatVariable(
            name=f"ln_h_min_{ratio_counter}",
            lb=ln_h_min,
            ub=ln_h_min,
        )

        # (A) x_i - x_j - ln(h_max) <= 0
        lp.add_constraint(
            name=f"max_ratio_constraint_{ratio_counter}",
            lhs={
                c_i_id: 1.0,
                c_j_id: -1.0,
                ln_h_max_var: -1.0,
            },
            sense=ConstraintSense.LEQ,
            rhs=0,
        )
        # (B) -x_i + x_j - ln(h_min) <= 0
        lp.add_constraint(
            name=f"min_ratio_constraint_{ratio_counter}",
            lhs={
                c_i_id: -1.0,
                c_j_id: +1.0,
                ln_h_min_var: -1.0,
            },
            sense=ConstraintSense.LEQ,
            rhs=0,
        )

        ratio_counter += 1

    # Set reaction driving force constraints
    var_B = FloatVariable(
        name=f"var_B",
        lb=-float("inf"),
        ub=float("inf"),
    )
    lp.add_existing_float_variable(var_B)

    if add_bottleneck_constraints:
        bottleneck_z_sum_var_name = "bottleneck_z_sum"
        lp.add_float_variable(
            name=bottleneck_z_sum_var_name,
            lb=-float("inf"),
            ub=float("inf"),
        )
        bottleneck_z_sum_lhs = {
            bottleneck_z_sum_var_name: -1.0
        }

    if minimal_optmdf > -float("inf"):
        lp.add_constraint(
            name="minimal_optmdf",
            lhs={
                "var_B": 1.0,
            },
            sense=ConstraintSense.GEQ,
            rhs=minimal_optmdf,
        )

    for reaction in cobra_model.reactions:
        reaction: cobra.Reaction = reaction

        if reaction.id not in dG0_values.keys():
            continue

        f_varname = f"f_var_{reaction.id}"
        f_var = FloatVariable(
            name=f_varname,
            lb=-float("inf"),
            ub=float("inf"),
        )
        lp.add_existing_float_variable(f_var)

        dG0_value = dG0_values[reaction.id]["dG0"]
        dG0_uncertainty = abs(dG0_values[reaction.id]["uncertainty"])
        dG0_var = FloatVariable(
            name=f"dG0_{reaction.id}",
            lb=dG0_value - dG0_uncertainty,
            ub=dG0_value + dG0_uncertainty,
        )
        lp.add_existing_float_variable(dG0_var)

        # e.g.,
        #     RT * ln(([S]*[T])/([A]²*[B]))
        # <=> RT*ln([S]) + RT*ln([T]) - 2*RT*ln([A]) - RT*ln([B])
        f_expression_lhs: Dict[str, float] = {
            f_varname: -1,
            dG0_var.name: -1,
        }
        for metabolite in reaction.metabolites:
            stoichiometry = reaction.metabolites[metabolite]
            f_expression_lhs[f"x_{metabolite.id}"] = (-1) * stoichiometry * R * T
        lp.add_constraint(
            name=f"f_var_constraint_{reaction.id}",
            lhs=f_expression_lhs,
            sense=ConstraintSense.EQ,
            rhs=0,
        )

        z_varname = f"z_var_{reaction.id}"
        lp.add_binary_variable(name=z_varname)

        """
        ALTERNATIVE BIG M FORMULATION:
        z_zero_constraint_lhs = {
            reaction.id: 1.0,
            z_varname: -M,
        }
        z_zero_constraint_rhs = 0.0
        lp.add_constraint(
            name=f"z_zero_{reaction.id}",
            lhs=z_zero_constraint_lhs,
            sense=ConstraintSense.LEQ,
            rhs=z_zero_constraint_rhs,
        )

        # z_r = 1 -> f_r >= B == f_r - B >= 0
        # In Big M form: f_r + (1-z_i)*M >= B
        # z_one_constraint: pulp.LpConstraint = 0.0
        # z_one_constraint = var_B <= current_f_variable + (1-current_z_variable)*M
        z_one_constraint_lhs = {
            f_varname: 1.0,
            z_varname: -M,
            var_B.name: -1.0,
        }
        z_one_constraint_rhs = -M
        lp.add_constraint(
            name=f"z_one_{reaction.id}",
            lhs=z_one_constraint_lhs,
            sense=ConstraintSense.GEQ,
            rhs=z_one_constraint_rhs,
        )
        """

        indicator_0_lhs = {
            reaction.id: 1,
        }
        indicator_0 = IndicatorConstraint(
            name=f"indicator_0_{reaction.id}",
            lhs=indicator_0_lhs,
            rhs=0,
            sense=ConstraintSense.EQ,
            binary_name=z_varname,
            binary_value=BinaryValue.ZERO,
        )
        lp.add_existing_indicator_constraint(indicator_constraint=indicator_0)


        if add_bottleneck_constraints:
            bottleneck_z_name = f"bottleneck_z_{reaction.id}"
            lp.add_binary_variable(bottleneck_z_name)
            indicator_1_lhs = {
                "var_B": 1,
                bottleneck_z_name: -10_000,
                f_varname: -1,
            }
            bottleneck_z_sum_lhs[bottleneck_z_name] = 1.0
        else:
            indicator_1_lhs = {
                "var_B": 1,
                f_varname: -1,
            }

        indicator_1 = IndicatorConstraint(
            name=f"indicator_1_{reaction.id}",
            lhs=indicator_1_lhs,
            rhs=0,
            sense=ConstraintSense.LEQ,
            binary_name=z_varname,
            binary_value=BinaryValue.ONE,
        )
        lp.add_existing_indicator_constraint(indicator_constraint=indicator_1)

    if add_bottleneck_constraints:
        lp.add_constraint(
            name="bottleneck_z_sum_constraint",
            lhs=bottleneck_z_sum_lhs,
            sense=ConstraintSense.EQ,
            rhs=0,
        )

    return lp
