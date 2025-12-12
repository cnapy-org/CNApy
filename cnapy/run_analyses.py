import cobra
from cobrak.dataclasses import ExtraLinearConstraint, Solver, Model
from cobrak.constants import ALL_OK_KEY, LNCONC_VAR_PREFIX, TERMINATION_CONDITION_KEY
from cobrak.io import get_base_id, load_annotated_cobrapy_model_as_cobrak_model
from cobrak.cobrapy_model_functionality import get_fullsplit_cobra_model
from cobrak.lps import (
    perform_lp_optimization,
    perform_lp_thermodynamic_bottleneck_analysis,
    perform_lp_variability_analysis,
)
from cnapy.appdata import Scenario
from pydantic import validate_call, ConfigDict
from optlang.symbolics import Zero

NO_DG0_ERROR_MSG: str = "ERROR: To run a calculation with thermodynamic constraints, your model needs at least one reaction with a ΔG'° (annotation key 'dG0')."
CNAPY_FWD_SUFFIX: str = "_CNAPYFWD"
CNAPY_REV_SUFFIX: str = "_CNAPYREV"


@validate_call(config=ConfigDict(arbitrary_types_allowed=True), validate_return=True)
def load_scenario_into_cobrapy_model(
    model: cobra.Model,
    scen_values: Scenario,
) -> None:
    for x in scen_values:
        try:
            y = model.reactions.get_by_id(x)
        except KeyError:
            print("reaction", x, "not found!")
        else:
            y.bounds = scen_values[x]
            y.set_hash_value()

    scen_values.add_scenario_reactions_to_model(model)

    if scen_values.use_scenario_objective:
        model.objective = model.problem.Objective(
            Zero, direction=scen_values.objective_direction
        )
        for reac_id, coeff in scen_values.objective_coefficients.items():
            try:
                reaction: cobra.Reaction = model.reactions.get_by_id(reac_id)
            except KeyError:
                print("reaction", reac_id, "not found!")
            else:
                model.objective.set_linear_coefficients(
                    {
                        reaction.forward_variable: coeff,
                        reaction.reverse_variable: -coeff,
                    }
                )

    for expression, constraint_type, rhs in scen_values.constraints:
        if constraint_type == "=":
            lb = rhs
            ub = rhs
        elif constraint_type == "<=":
            lb = None
            ub = rhs
        elif constraint_type == ">=":
            lb = rhs
            ub = None
        else:
            print("Skipping constraint of unknown type", constraint_type)
            continue
        try:
            reactions = model.reactions.get_by_any(list(expression))
        except KeyError:
            print(
                "Skipping constraint containing a reaction that is not in the model:",
                expression,
            )
            continue
        constr = model.problem.Constraint(Zero, lb=lb, ub=ub)
        model.add_cons_vars(constr)
        for reaction, coeff in zip(reactions, expression.values()):
            constr.set_linear_coefficients(
                {reaction.forward_variable: coeff, reaction.reverse_variable: -coeff}
            )

    reaction_ids = [reaction.id for reaction in model.reactions]
    for annotation in scen_values.annotations:
        if "reaction_id" not in annotation.keys():
            continue
        if annotation["reaction_id"] not in reaction_ids:
            continue
        reaction: cobra.Reaction = model.reactions.get_by_id(annotation["reaction_id"])
        reaction.annotation[annotation["key"]] = annotation["value"]


@validate_call(validate_return=True)
def _get_error_message(solution: dict[str, float]) -> str:
    if not solution[ALL_OK_KEY]:
        if TERMINATION_CONDITION_KEY in solution:
            match solution[TERMINATION_CONDITION_KEY]:
                case 1:
                    return "Solver's time limit hit. Please change solver or problem complexity."
                case 2:
                    return "Solver's iterations limit hit. Please change solver or problem complexity."
                case 7:
                    return "The problem appears to be unbounded, i.e. there is no constraint limiting the objective values."
                case 8:
                    return "The problem appears to be infeasible, i.e. the constraints make a solution impossible."
                case 10:
                    return "Your solver seems to have crashed. Try another solver."
                case 11:
                    return "Your solver seems to have crashed. Try another solver."
                case 15:
                    return "License problem with the solver! Check out CNApy's documentation for more about how to solve it for CPLEX and Gurobi, or try another solver."
                case _:
                    return "The solution process or the solution failed somehow."
        else:
            return (
                "Something went wrong (CNApy could not identify the type of error). The computation could not run. Check your problem's constraints or try a different solver.",
            )

    return ""


@validate_call(config=ConfigDict(arbitrary_types_allowed=True), validate_return=True)
def _get_cobrak_model(
    cobrapy_model: cobra.Model,
    scen_values: Scenario,
    min_default_conc: float = 1e-6,
    max_default_conc: float = 0.1,
) -> Model:
    extra_linear_constraints: list[ExtraLinearConstraint] = []
    for constraint in scen_values.constraints:
        # e.g., [({'EDD': 1.0}, '>=', 1.0)]
        extra_linear_constraint = ExtraLinearConstraint(
            stoichiometries={key: value for key, value in constraint[0].items()},
        )

        direction = constraint[1]
        rhs = constraint[2]
        if direction == ">=":
            extra_linear_constraint.lower_value = rhs
        elif direction == "<=":
            extra_linear_constraint.upper_value = rhs
        else:  # == "="
            extra_linear_constraint.lower_value = rhs
            extra_linear_constraint.upper_value = rhs

        extra_linear_constraints.append(extra_linear_constraint)

    with cobrapy_model as model:
        load_scenario_into_cobrapy_model(model, scen_values)
        cobrak_model = load_annotated_cobrapy_model_as_cobrak_model(
            get_fullsplit_cobra_model(
                model,
                fwd_suffix=CNAPY_FWD_SUFFIX,
                rev_suffix=CNAPY_REV_SUFFIX,
                add_cobrak_sbml_annotation=True,
                cobrak_default_min_conc=min_default_conc,
                cobrak_default_max_conc=max_default_conc,
                cobrak_extra_linear_constraints=extra_linear_constraints,
                cobrak_kinetic_ignored_metabolites=[],
                cobrak_no_extra_versions=True,
                reac_lb_ub_cap=1_000.0,
            ),
            deactivate_mw_warning=True,
        )

    return cobrak_model


@validate_call(validate_return=True)
def _no_dG0(cobrak_model: Model) -> bool:
    return all(
        cobrak_model.reactions[reac_id].dG0 is None
        for reac_id in cobrak_model.reactions
    )


@validate_call(config=ConfigDict(arbitrary_types_allowed=True), validate_return=True)
def _get_combined_opt_solution(
    original_model: cobra.Model, solution: dict[str, float]
) -> dict[str, float]:
    # Combine FWD and REV flux solutions
    combined_solution: dict[str, float] = {}
    for var_id in solution.keys():
        if var_id.endswith(CNAPY_FWD_SUFFIX):
            base_key = var_id.replace(CNAPY_FWD_SUFFIX, "")
            key = base_key if base_key in original_model.reactions else var_id
            multiplier = 1.0
        elif var_id.endswith(CNAPY_REV_SUFFIX):
            base_key = var_id.replace(CNAPY_REV_SUFFIX, "")
            key = base_key if base_key in original_model.reactions else var_id
            multiplier = -1.0
        else:
            key = var_id
            multiplier = 1.0
        if key not in combined_solution.keys():
            combined_solution[key] = 0.0
        combined_solution[key] += multiplier * solution[var_id]
    return combined_solution


@validate_call(config=ConfigDict(arbitrary_types_allowed=True), validate_return=True)
def _get_combined_var_solution(
    original_cobrapy_model: cobra.Model,
    cobrak_model: Model,
    variability_dict: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    combined_solution: dict[str, list[tuple[float, float]]] = {}

    for reac_id in cobrak_model.reactions:
        if reac_id not in variability_dict:
            continue
        temp_base_id = get_base_id(
            reac_id,
            cobrak_model.fwd_suffix,
            cobrak_model.rev_suffix,
            cobrak_model.reac_enz_separator,
        )
        base_id = (
            temp_base_id
            if temp_base_id in original_cobrapy_model.reactions
            else reac_id
        )

        multiplier = -1 if reac_id.endswith(cobrak_model.rev_suffix) else 1
        min_flux = variability_dict[reac_id][0]
        max_flux = variability_dict[reac_id][1]

        if base_id not in combined_solution:
            combined_solution[base_id] = [0.0, 0.0]

        combined_solution[base_id][0] += multiplier * min_flux
        combined_solution[base_id][1] += multiplier * max_flux

    for met_id in cobrak_model.metabolites:
        met_var_id = f"{LNCONC_VAR_PREFIX}{met_id}"
        if met_var_id in variability_dict:
            combined_solution[met_id][0] = variability_dict[met_var_id][0]
            combined_solution[met_id][1] = variability_dict[met_var_id][1]

    return combined_solution


@validate_call(config=ConfigDict(arbitrary_types_allowed=True), validate_return=True)
def run_lp_optimization(
    cobrapy_model: cobra.Model,
    scen_values: Scenario,
    solver_name: str,
    with_enzyme_constraints: bool = False,
    with_thermodynamic_constraints: bool = False,
    objective_overwrite: dict[str, float] = {},
    direction_overwrite: float = +1,
    min_mdf: float = -float("inf"),
    min_default_conc: float = 1e-6,
    max_default_conc: float = 0.1,
) -> tuple[str, dict[str, float]]:
    if not objective_overwrite:
        objective = {}
        for (
            reaction,
            coefficient,
        ) in cobra.util.solver.linear_reaction_coefficients(cobrapy_model).items():
            if reaction.reversibility:
                objective[reaction.id + CNAPY_FWD_SUFFIX] = coefficient
                objective[reaction.id + CNAPY_REV_SUFFIX] = -coefficient
            else:
                objective[reaction.id] = coefficient
        direction = +1
    else:
        objective = objective_overwrite
        direction = direction_overwrite

    cobrak_model = _get_cobrak_model(
        cobrapy_model=cobrapy_model,
        scen_values=scen_values,
        min_default_conc=min_default_conc,
        max_default_conc=max_default_conc,
    )

    if with_thermodynamic_constraints and _no_dG0(cobrak_model):
        return (
            NO_DG0_ERROR_MSG,
            {},
        )

    lp_opt_solution = perform_lp_optimization(
        cobrak_model=cobrak_model,
        objective_target=objective,
        objective_sense=direction,
        with_enzyme_constraints=with_enzyme_constraints,
        with_thermodynamic_constraints=with_thermodynamic_constraints,
        with_loop_constraints=False,
        min_mdf=min_mdf,
        solver=Solver(name=solver_name),
        verbose=False,
    )

    return (
        _get_error_message(lp_opt_solution),
        _get_combined_opt_solution(cobrapy_model, lp_opt_solution),
    )


@validate_call(config=ConfigDict(arbitrary_types_allowed=True), validate_return=True)
def run_lp_bottleneck_analysis(
    cobrapy_model: cobra.Model,
    scen_values: Scenario,
    solver_name: str,
    with_enzyme_constraints: bool = False,
    min_mdf: float = -float("inf"),
    min_default_conc: float = 1e-6,
    max_default_conc: float = 0.1,
) -> tuple[str, list[str]]:
    cobrak_model = _get_cobrak_model(
        cobrapy_model=cobrapy_model,
        scen_values=scen_values,
        min_default_conc=min_default_conc,
        max_default_conc=max_default_conc,
    )

    if _no_dG0(cobrak_model):
        return (
            NO_DG0_ERROR_MSG,
            [],
        )

    bottlenecks = perform_lp_thermodynamic_bottleneck_analysis(
        cobrak_model=cobrak_model,
        with_enzyme_constraints=with_enzyme_constraints,
        min_mdf=min_mdf,
        solver=Solver(name=solver_name),
    )

    return ("", bottlenecks)


@validate_call(config=ConfigDict(arbitrary_types_allowed=True), validate_return=True)
def run_lp_variability_analysis(
    cobrapy_model: cobra.Model,
    scen_values: Scenario,
    solver_name: str,
    with_enzyme_constraints: bool = False,
    with_thermodynamic_constraints: bool = False,
    calculate_reacs: bool = True,
    calculate_concs: bool = False,
    min_mdf: float = -float("inf"),
    min_default_conc: float = 1e-6,
    max_default_conc: float = 0.1,
) -> dict[str, tuple[float, float]]:
    cobrak_model = _get_cobrak_model(
        cobrapy_model=cobrapy_model,
        scen_values=scen_values,
        min_default_conc=min_default_conc,
        max_default_conc=max_default_conc,
    )

    if with_thermodynamic_constraints and _no_dG0(cobrak_model):
        return (
            "ERROR: To run a calculation with thermodynamic constraints, your model needs "
            "at least one reaction with a ΔG'° (annotation key 'dG0').",
            {},
        )

    return _get_combined_var_solution(
        cobrapy_model,
        cobrak_model,
        perform_lp_variability_analysis(
            cobrak_model=cobrak_model,
            with_enzyme_constraints=with_enzyme_constraints,
            with_thermodynamic_constraints=with_thermodynamic_constraints,
            solver=Solver(name=solver_name),
            min_mdf=min_mdf,
            calculate_reacs=calculate_reacs,
            calculate_concs=calculate_concs,
            calculate_rest=False,
        ),
    )
