from dataclasses import asdict
import hashlib
import json
import cobra
from cobrak.dataclasses import ExtraLinearConstraint, Solver, Model
from cobrak.constants import ALL_OK_KEY, FLUX_SUM_VAR_ID, LNCONC_VAR_PREFIX, OBJECTIVE_VAR_NAME, REAC_ENZ_SEPARATOR, TERMINATION_CONDITION_KEY
from cobrak.io import get_base_id, get_files, json_zip_load, json_zip_write, load_annotated_cobrapy_model_as_cobrak_model, standardize_folder
from cobrak.cobrapy_model_functionality import get_fullsplit_cobra_model
from cobrak.lps import (
    perform_lp_optimization,
    perform_lp_thermodynamic_bottleneck_analysis,
    perform_lp_variability_analysis,
)
from gurobipy import GurobiError
from cplex import CplexError
from cnapy.appdata import Scenario
from pydantic import validate_call, ConfigDict
from optlang.symbolics import Zero
from pyomo.common.errors import ApplicationError

NO_DG0_ERROR_MESSAGE: str = "ERROR: To run a calculation with thermodynamic constraints, your model needs at least one reaction with a ΔG'° (annotation key 'dG0')."
CNAPY_FWD_SUFFIX: str = "_CNAPYFWD"
CNAPY_REV_SUFFIX: str = "_CNAPYREV"
INFEASIBLE_ERROR_MESSAGE: str = ("The problem appears to be infeasible, i.e. the constraints make a solution impossible.\n"\
                                 "If you used measured flux values as scenario, you may want to try 'Analysis->Make scenario feasible'.")

@validate_call(validate_return=True)
def _get_gurobi_error_message(
    exception_message: str
) -> str:
    if "size-limited license" or "Model too large" in exception_message:
        prefix = ("Gurobi Error: This error is likely caused by using the Gurobi Community Edition, which only works for small problems.\n"
        "To solve this problem, use a different solver or install a full version of Gurobi on your system, see https://gurobi.com/unrestricted for the latter.\n"
        "Or, if you have already installed a full Gurobi version on your system, follow the instructions under 'Config->Configure Gurobi full version' "
        "in CNApy's main menu to connect the full Gurobi version to CNApy.\n")
    else:
        prefix = ""
    return f"{prefix}Full text of Gurobi exception was: {exception_message}"


@validate_call(validate_return=True)
def _get_cplex_error_message(
    exception_message: str
) -> str:
    if "1016" or "Community" in exception_message:
        prefix = ("CPLEX Error: This error is likely caused by using the CPLEX Community Edition, which only works for small problems.\n"
            "To solve this problem, use a different solver or install a full version of Gurobi on your system, see http://ibm.biz/error1016 for the latter.\n"
            "Or, if you have already installed a full Gurobi version on your system, follow the instructions under 'Config->Configure CPLEX full version' "
            "in CNApy's main menu to connect the full CPLEX version to CNApy.\n")
    else:
        prefix = ""
    return f"{prefix}Full text of CPLEX exception was: {exception_message}"


@validate_call(validate_return=True)
def _get_application_error_message(
    exception_message: str
) -> str:
    if "scip" in exception_message and "No executable found" in exception_message:
        prefix = (
            "SCIP error: Likely (check with exception message below), you don't have SCIP installed on your system.\n"
            "Try a different solver or install SCIP and make optimizations with it possible by following the instructions under https://scipopt.org/"
        )
    elif "glpk" in exception_message and "No executable found" in exception_message:
        prefix = (
            "GLPK error: Likely (check with exception message below), you don't have GLPK installed on your system.\n"
            "Try a different solver or install GLPK and make optimizations with it possible by following the instructions under https://www.gnu.org/software/glpk/"
        )
    else:
        prefix = ""
    return f"{prefix}Full text of ApplicationError exception was: {exception_message}"


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
def _get_error_message(solution: dict[str, float | None]) -> str:
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
                    return INFEASIBLE_ERROR_MESSAGE
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
    max_prot_pool: float | None=None,
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
        cobrak_model.fwd_suffix = CNAPY_FWD_SUFFIX
        cobrak_model.rev_suffix = CNAPY_REV_SUFFIX
    
    if max_prot_pool:
        cobrak_model.max_prot_pool = max_prot_pool

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
        base_key = get_base_id(var_id, fwd_suffix=CNAPY_FWD_SUFFIX, rev_suffix=CNAPY_REV_SUFFIX, reac_enz_separator=REAC_ENZ_SEPARATOR)
        key = base_key if base_key in original_model.reactions else var_id
        multiplier = -1.0 if var_id.endswith(CNAPY_REV_SUFFIX) else 1.0
        if key not in combined_solution.keys():
            combined_solution[key] = 0.0
        combined_solution[key] += multiplier * solution[var_id]
    return combined_solution


@validate_call(config=ConfigDict(arbitrary_types_allowed=True), validate_return=True)
def _get_combined_var_solution(
    original_cobrapy_model: cobra.Model,
    cobrak_model: Model, # Assuming this is your cobrak.core.model.Model class
    variability_dict: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    # Use a dict for combining the intermediate results
    var_solution: dict[str, tuple[float, float]] = {}

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

        min_flux_split = variability_dict[reac_id][0]
        max_flux_split = variability_dict[reac_id][1]

        # Initialize the combined solution for the base reaction if not present
        if base_id not in var_solution:
            # Initialize with (0.0, 0.0). This represents the starting point for 
            # calculating the range: min(R_fwd) - max(R_rev) and max(R_fwd) - min(R_rev)
            var_solution[base_id] = (0.0, 0.0) 

        current_min, current_max = var_solution[base_id]

        # Apply the correct combination logic based on the split reaction type
        if reac_id.endswith(cobrak_model.fwd_suffix):
            # The net MIN flux is based on min(R_fwd)
            new_min = min(current_min, min_flux_split)
            # The net MAX flux is based on max(R_fwd)
            new_max = max(current_max, max_flux_split)
            var_solution[base_id] = (new_min, new_max)
        elif reac_id.endswith(cobrak_model.rev_suffix):
            # To get the net MIN flux (a - d), subtract max(R_rev)
            new_min = current_min - max_flux_split 
            # To get the net MAX flux (b - c), subtract min(R_rev)
            new_max = current_max - min_flux_split 
            var_solution[base_id] = (new_min, new_max)
        else:
             # Handle non-split irreversible reactions directly
             var_solution[base_id] = variability_dict[reac_id]

    # Handle metabolite variables
    for met_id in cobrak_model.metabolites:
        met_var_id = f"{LNCONC_VAR_PREFIX}{met_id}"
        if met_var_id in variability_dict:
            var_solution[met_id] = variability_dict[met_var_id]

    return var_solution

@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
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
    parsimonious: bool = False,
    max_prot_pool: float | None = None,
) -> tuple[str, dict[str, float | None]]:
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
        max_prot_pool=max_prot_pool,
    )

    if with_thermodynamic_constraints and _no_dG0(cobrak_model):
        return (
            NO_DG0_ERROR_MESSAGE,
            {},
        )

    try:
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
            with_flux_sum_var=parsimonious,
        )
    except GurobiError as e:
        return (
            _get_gurobi_error_message(str(e)),
            {},
        )
    except CplexError as e:
        return (
            _get_cplex_error_message(str(e)),
            {},
        )
    except RuntimeError:
        return (
            INFEASIBLE_ERROR_MESSAGE,
            {},
        )
    except ApplicationError as e:
        return (
            _get_application_error_message(str(e)),
            {},
        )
    if any(val is None for val in lp_opt_solution.values()):
        return (
            INFEASIBLE_ERROR_MESSAGE,
            {},
        )

    if parsimonious and lp_opt_solution[ALL_OK_KEY]:
        with cobrak_model as min_flux_sum_model:
            min_flux_sum_model.extra_linear_constraints.append(
                ExtraLinearConstraint(
                    stoichiometries=objective,
                    lower_value=lp_opt_solution[OBJECTIVE_VAR_NAME] - 1e-8,
                    upper_value=lp_opt_solution[OBJECTIVE_VAR_NAME] + 1e-8,
                )
            )
            lp_opt_solution = perform_lp_optimization(
                cobrak_model=min_flux_sum_model,
                objective_target=FLUX_SUM_VAR_ID,
                objective_sense=-1,
                with_enzyme_constraints=with_enzyme_constraints,
                with_thermodynamic_constraints=with_thermodynamic_constraints,
                with_loop_constraints=False,
                min_mdf=min_mdf,
                solver=Solver(name=solver_name),
                verbose=False,
                with_flux_sum_var=True,
            )
    return (
        _get_error_message(lp_opt_solution),
        _get_combined_opt_solution(cobrapy_model, lp_opt_solution) if lp_opt_solution[ALL_OK_KEY] else {},
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
    max_prot_pool: float | None = None,
) -> tuple[str, list[str], dict[str, float]]:
    cobrak_model = _get_cobrak_model(
        cobrapy_model=cobrapy_model,
        scen_values=scen_values,
        min_default_conc=min_default_conc,
        max_default_conc=max_default_conc,
        max_prot_pool=max_prot_pool,
    )

    if _no_dG0(cobrak_model):
        return (
            NO_DG0_ERROR_MESSAGE,
            [],
            {},
        )
    
    try:
        bottlenecks, bottleneck_solution = perform_lp_thermodynamic_bottleneck_analysis(
            cobrak_model=cobrak_model,
            with_enzyme_constraints=with_enzyme_constraints,
            min_mdf=min_mdf,
            solver=Solver(name=solver_name),
        )
    except GurobiError as e:
        return (
            _get_gurobi_error_message(str(e)),
            [],
            {},
        )
    except CplexError as e:
        return (
            _get_cplex_error_message(str(e)),
            [],
            {},
        )
    except RuntimeError:
        return (
            INFEASIBLE_ERROR_MESSAGE,
            [],
            {},
        )
    except ApplicationError as e:
        return (
            _get_application_error_message(str(e)),
            {},
        )
    if any(val is None for val in bottleneck_solution.values()):
        return (
            INFEASIBLE_ERROR_MESSAGE,
            [],
            {},
        )

    bottleneck_base_ids = [
        get_base_id(
            reac_id,
            fwd_suffix=CNAPY_FWD_SUFFIX,
            rev_suffix=CNAPY_REV_SUFFIX,
            reac_enz_separator=REAC_ENZ_SEPARATOR
        )
        for reac_id in bottlenecks
    ]
    return (
        _get_error_message(bottleneck_solution),
        [(bottleneck_base_ids[i] if bottleneck_base_ids[i] in cobrapy_model.reactions else bottlenecks[i]) for i in range(len(bottlenecks))],
        bottleneck_solution,
    )

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
    use_results_cache: bool=False,
    results_cache_dir: str="",
    max_prot_pool: float | None=None,
) -> tuple[str, dict[str, tuple[float | None, float | None]]]:
    cobrak_model = _get_cobrak_model(
        cobrapy_model=cobrapy_model,
        scen_values=scen_values,
        min_default_conc=min_default_conc,
        max_default_conc=max_default_conc,
        max_prot_pool=max_prot_pool,
    )

    if with_thermodynamic_constraints and _no_dG0(cobrak_model):
        return (
            "ERROR: To run a calculation with thermodynamic constraints, your model needs "
            "at least one reaction with a ΔG'° (annotation key 'dG0').",
            {},
        )
    
    var_result: dict[str, tuple[float, float]] = {}
    if use_results_cache:
        results_cache_dir = standardize_folder(results_cache_dir)
        data_dict = asdict(cobrak_model)
        data_str = json.dumps(data_dict, sort_keys=True)
        data_bytes = data_str.encode('utf-8')
        full_hash = hashlib.md5(data_bytes).hexdigest()
        cache_basename = f"fvacache_{with_thermodynamic_constraints}_{with_enzyme_constraints}_{full_hash}"
        if f"{cache_basename}.zip" in get_files(results_cache_dir):
            var_result = json_zip_load(cache_basename)
    if not var_result:
        try:
            var_result = perform_lp_variability_analysis(
                cobrak_model=cobrak_model,
                with_enzyme_constraints=with_enzyme_constraints,
                with_thermodynamic_constraints=with_thermodynamic_constraints,
                solver=Solver(name=solver_name),
                min_mdf=min_mdf,
                calculate_reacs=calculate_reacs,
                calculate_concs=calculate_concs,
                calculate_rest=False,
            )
            if use_results_cache:
                json_zip_write(f"{results_cache_dir}{cache_basename}", var_result)
        except GurobiError as e:
            return (
                _get_gurobi_error_message(str(e)),
                {},
            )
        except CplexError as e:
            return (
                _get_cplex_error_message(str(e)),
                {},
            )
        except (RuntimeError, ValueError):
            return (
                INFEASIBLE_ERROR_MESSAGE,
                {},
            )
        except ApplicationError as e:
            return (
                _get_application_error_message(str(e)),
                {},
            )
    for val in var_result.values():
        if len(val) > 1:
            if val[0] is None or val[1] is None:
                return (
                INFEASIBLE_ERROR_MESSAGE,
                {},
            )

    return (
        "",
        _get_combined_var_solution(
            cobrapy_model,
            cobrak_model,
            var_result,
        )
    )
